#!/usr/bin/env python3
"""Restore and cryptographically verify a private Veltrix evidence archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.encrypted_source_evidence import decrypt_and_verify_source_evidence
from app.provider_acquisition_artifact import validate_fivedollar_history_batch_report
from app.evidence_receipt_signing import (
    SCHEMA_V2, ReceiptSignatureError, sign_receipt, verify_receipt_signature,
)
from app.evidence_receipt_trust import (
    ReceiptTrustError, parse_trusted_key_regions,
    verify_receipt_with_trusted_clients,
)

_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
_REQUIRED_OBJECTS = {"report", "evidence", "manifest"}


class EvidenceRestoreError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_endpoint_url(endpoint: str | None) -> str:
    parsed = urlparse(endpoint or "")
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise EvidenceRestoreError("archive_endpoint_must_be_https_without_embedded_credentials")
    return endpoint


def write_verified_digest_registry(result: dict, output_path: str | Path,
                                   kms_client: Any) -> dict:
    if (not isinstance(result, dict)
            or result.get("archive_receipt_signature_verified") is not True
            or not isinstance(result.get("receipt_sha256"), str)
            or not isinstance(result.get("receipt_signing_key_arn"), str)
            or not isinstance(result.get("run_id"), str)
            or not isinstance(result.get("verified_source_evidence_sha256"), list)):
        raise EvidenceRestoreError("verified_digest_registry_source_invalid")
    raw_digests = result["verified_source_evidence_sha256"]
    if any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
           for digest in raw_digests):
        raise EvidenceRestoreError("verified_digest_registry_digest_invalid")
    if (not re.fullmatch(r"[0-9a-f]{64}", result["receipt_sha256"])
            or not result["receipt_signing_key_arn"].startswith("arn:aws:kms:")
            or ":key/" not in result["receipt_signing_key_arn"]):
        raise EvidenceRestoreError("verified_digest_registry_receipt_identity_invalid")
    registry = {
        "schema": SCHEMA_V2,
        "schema_version": 1,
        "verified_source_evidence_sha256": sorted(set(raw_digests)),
        "verified_archive_receipts": [{
            "archive_receipt_signature_verified": True,
            "receipt_sha256": result["receipt_sha256"],
            "receipt_signing_key_arn": result["receipt_signing_key_arn"],
            "run_id": result["run_id"],
        }],
    }
    try:
        registry = sign_receipt(
            kms_client=kms_client,
            key_arn=result["receipt_signing_key_arn"],
            receipt=registry,
        )
    except ReceiptSignatureError:
        raise EvidenceRestoreError("verified_digest_registry_signing_failed") from None
    destination = Path(output_path)
    if destination.is_symlink():
        raise EvidenceRestoreError("verified_digest_registry_symlink_rejected")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not destination.is_file():
        raise EvidenceRestoreError("verified_digest_registry_destination_invalid")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(registry, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return registry


def restore_evidence(*, client: Any, kms_client: Any, trusted_signing_key_arn: str, bucket: str, receipt_key: str,
                     encryption_key: str, output_dir: str | Path,
                     trusted_kms_clients: dict[str, Any] | None = None) -> dict:
    if not isinstance(receipt_key, str) or not receipt_key or ".." in Path(receipt_key).parts:
        raise EvidenceRestoreError("restore_receipt_key_invalid")
    try:
        receipt_bytes = client.get_object(Bucket=bucket, Key=receipt_key)["Body"].read()
        receipt = json.loads(receipt_bytes)
    except Exception:
        raise EvidenceRestoreError("restore_receipt_unreadable") from None
    try:
        if trusted_kms_clients is not None:
            verify_receipt_with_trusted_clients(
                receipt=receipt, trusted_kms_clients=trusted_kms_clients,
            )
        else:
            verify_receipt_signature(
                kms_client=kms_client, trusted_key_arn=trusted_signing_key_arn,
                receipt=receipt,
            )
    except (ReceiptSignatureError, ReceiptTrustError):
        raise EvidenceRestoreError("restore_receipt_signature_invalid") from None
    if (not isinstance(receipt, dict)
            or receipt.get("schema") != SCHEMA_V2
            or receipt.get("provider") != "fivedollar"
            or receipt.get("bucket") != bucket
            or receipt.get("receipt_key") != receipt_key
            or receipt.get("readback_verified") is not True
            or receipt.get("raw_payloads") != "encrypted_only"):
        raise EvidenceRestoreError("restore_receipt_invalid")
    run_id = receipt.get("run_id")
    if not isinstance(run_id, str) or not _SAFE.fullmatch(run_id):
        raise EvidenceRestoreError("restore_run_id_invalid")
    if not receipt_key.endswith(f"/receipts/{run_id}.json"):
        raise EvidenceRestoreError("restore_receipt_run_binding_invalid")

    objects = receipt.get("objects")
    if not isinstance(objects, list) or {item.get("kind") for item in objects if isinstance(item, dict)} != _REQUIRED_OBJECTS:
        raise EvidenceRestoreError("restore_object_inventory_invalid")
    archive_prefix = receipt_key.rsplit("/receipts/", 1)[0]
    expected_keys = {
        "report": f"{archive_prefix}/reports/{run_id}.json",
        "evidence": f"{archive_prefix}/encrypted/{run_id}.enc",
        "manifest": f"{archive_prefix}/manifests/{run_id}.json",
    }
    restored: dict[str, bytes] = {}
    for item in objects:
        if not isinstance(item, dict):
            raise EvidenceRestoreError("restore_object_entry_invalid")
        kind, key, digest, size = item.get("kind"), item.get("key"), item.get("sha256"), item.get("bytes")
        if (kind not in _REQUIRED_OBJECTS or kind in restored
                or not isinstance(key, str) or key != expected_keys.get(kind)
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or isinstance(size, bool) or not isinstance(size, int) or size < 0):
            raise EvidenceRestoreError("restore_object_metadata_invalid")
        try:
            body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        except Exception:
            raise EvidenceRestoreError(f"restore_object_missing:{kind}") from None
        if len(body) != size or _sha(body) != digest:
            raise EvidenceRestoreError(f"restore_object_digest_mismatch:{kind}")
        restored[kind] = body

    try:
        report = json.loads(restored["report"])
        manifest = json.loads(restored["manifest"])
    except (TypeError, ValueError):
        raise EvidenceRestoreError("restore_report_or_manifest_invalid") from None
    integrity = validate_fivedollar_history_batch_report(report, require_acceptance=False)
    if (integrity.get("report_sha256") != receipt.get("report_sha256")
            or report.get("run_id") != run_id
            or manifest.get("run_id") != run_id
            or manifest.get("report_sha256") != receipt.get("report_sha256")
            or manifest.get("evidence_count") != receipt.get("evidence_count")
            or manifest.get("ciphertext_sha256") != _sha(restored["evidence"])
            or manifest.get("evidence_count") != integrity.get("input_count")):
        raise EvidenceRestoreError("restore_report_manifest_binding_invalid")
    evidence = decrypt_and_verify_source_evidence(
        restored["evidence"], report=report, manifest=manifest, key=encryption_key
    )
    if len(evidence) != integrity["input_count"]:
        raise EvidenceRestoreError("restore_evidence_coverage_incomplete")

    # Publish the complete restore as one directory rename. Staging is created
    # beside the destination so the rename stays on one filesystem. Existing
    # destinations are never merged or overwritten.
    destination = Path(output_dir)
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise EvidenceRestoreError("restore_destination_already_exists")
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.restore-", dir=parent))
    filenames = {
        "report": "fivedollar_history_batch.json",
        "evidence": "fivedollar_source_evidence.enc",
        "manifest": "fivedollar_source_evidence.enc.manifest.json",
    }
    try:
        for kind, filename in filenames.items():
            (staging / filename).write_bytes(restored[kind])
        # Recheck immediately before publication; never intentionally replace
        # an existing restore directory.
        if destination.exists() or destination.is_symlink():
            raise EvidenceRestoreError("restore_destination_already_exists")
        os.rename(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    paths = {kind: str(destination / filename) for kind, filename in filenames.items()}
    verified_digests = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        for field in ("payload_sha256", "normalized_record_sha256"):
            digest = item.get(field)
            if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
                verified_digests.add(digest)
    signature = receipt.get("signature", {})
    return {
        "valid": True, "archive_receipt_signature_verified": True,
        "receipt_sha256": _sha(receipt_bytes),
        "receipt_signing_key_arn": signature.get("key_arn") if isinstance(signature, dict) else None,
        "run_id": run_id, "report_sha256": integrity["report_sha256"],
        "accepted_count": integrity["accepted_count"],
        "quarantined_count": integrity["quarantined_count"],
        "evidence_count": len(evidence),
        "verified_source_evidence_sha256": sorted(verified_digests),
        "paths": paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", default="restored-fivedollar-evidence")
    parser.add_argument("--verified-digests-output", default=None,
                        help="Optional atomic JSON export of signature-verified source digests")
    args = parser.parse_args()
    try:
        if not _SAFE.fullmatch(args.run_id):
            raise EvidenceRestoreError("restore_run_id_invalid")
        endpoint = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_ENDPOINT_URL")
        endpoint = _validate_endpoint_url(endpoint)
        bucket = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_BUCKET")
        access = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_ACCESS_KEY_ID")
        secret = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_SECRET_ACCESS_KEY")
        encryption_key = os.getenv("VELTRIX_RAW_EVIDENCE_ENCRYPTION_KEY")
        region = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_REGION", "auto")
        prefix = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_PREFIX", "veltrix-football/evidence/v2").strip("/")
        signing_key_arn = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_KEY_ARN")
        kms_region = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_REGION")
        registry_json = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON")
        if not all((endpoint, bucket, access, secret, encryption_key)):
            raise EvidenceRestoreError("private_evidence_restore_configuration_missing")
        try:
            trusted_regions = parse_trusted_key_regions(
                registry_json=registry_json,
                legacy_key_arn=signing_key_arn,
                legacy_region=kms_region,
            )
        except ReceiptTrustError:
            raise EvidenceRestoreError("private_evidence_kms_trust_configuration_invalid") from None
        import boto3
        client = boto3.client(
            "s3", endpoint_url=endpoint, region_name=region,
            aws_access_key_id=access, aws_secret_access_key=secret,
        )
        trusted_kms_clients = {
            key_arn: boto3.client("kms", region_name=key_region)
            for key_arn, key_region in trusted_regions.items()
        }
        result = restore_evidence(
            client=client, kms_client=None, trusted_signing_key_arn=signing_key_arn or "",
            trusted_kms_clients=trusted_kms_clients, bucket=bucket,
            receipt_key=f"{prefix}/receipts/{args.run_id}.json",
            encryption_key=encryption_key, output_dir=args.output_dir,
        )
        if args.verified_digests_output:
            signing_key_arn = result["receipt_signing_key_arn"]
            registry = write_verified_digest_registry(
                result, args.verified_digests_output,
                trusted_kms_clients[signing_key_arn],
            )
            result["verified_digest_registry_path"] = str(args.verified_digests_output)
            result["verified_digest_registry_count"] = len(registry["verified_source_evidence_sha256"])
        print("PRIVATE_EVIDENCE_RESTORE: PASS; " + json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, EvidenceRestoreError) as exc:
        print(f"PRIVATE_EVIDENCE_RESTORE: FAIL ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
