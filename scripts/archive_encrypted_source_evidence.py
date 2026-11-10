#!/usr/bin/env python3
"""Upload verified Veltrix evidence to a private S3-compatible archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.provider_acquisition_artifact import validate_fivedollar_history_batch_report

_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


class EvidenceArchiveError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _head_exists(client: Any, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        response = getattr(exc, "response", {})
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = response.get("Error", {}).get("Code")
        if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def archive_evidence(*, client: Any, bucket: str, prefix: str,
                     report_path: str | Path, evidence_path: str | Path,
                     manifest_path: str | Path,
                     receipt_output_path: str | Path = "fivedollar_evidence_archive_receipt.json") -> dict:
    report_bytes = Path(report_path).read_bytes()
    evidence_bytes = Path(evidence_path).read_bytes()
    manifest_bytes = Path(manifest_path).read_bytes()
    report = json.loads(report_bytes)
    manifest = json.loads(manifest_bytes)
    integrity = validate_fivedollar_history_batch_report(report, require_acceptance=False)
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not _SAFE.fullmatch(run_id):
        raise EvidenceArchiveError("archive_run_id_invalid")
    if manifest.get("report_sha256") != integrity.get("report_sha256"):
        raise EvidenceArchiveError("archive_report_digest_mismatch")
    if manifest.get("ciphertext_sha256") != _sha(evidence_bytes):
        raise EvidenceArchiveError("archive_ciphertext_digest_mismatch")
    if manifest.get("evidence_count") != integrity.get("input_count"):
        raise EvidenceArchiveError("archive_evidence_count_mismatch")
    if not bucket or not isinstance(bucket, str):
        raise EvidenceArchiveError("archive_bucket_missing")

    root = prefix.strip("/")
    base = f"{root}/" if root else ""
    objects = [
        ("report", f"{base}reports/{run_id}.json", report_bytes, "application/json"),
        ("evidence", f"{base}encrypted/{run_id}.enc", evidence_bytes, "application/octet-stream"),
        ("manifest", f"{base}manifests/{run_id}.json", manifest_bytes, "application/json"),
    ]
    receipt_objects = []
    for label, key, body, content_type in objects:
        expected_digest = _sha(body)
        if _head_exists(client, bucket, key):
            # Idempotent retry: accept an existing immutable object only when
            # its downloaded bytes are exactly the bytes for this run.
            downloaded = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            if _sha(downloaded) != expected_digest:
                raise EvidenceArchiveError(f"archive_existing_object_digest_conflict:{label}")
        else:
            client.put_object(
                Bucket=bucket, Key=key, Body=body, ContentType=content_type,
                Metadata={"sha256": expected_digest, "run-id": run_id},
            )
            downloaded = client.get_object(Bucket=bucket, Key=key)["Body"].read()
            if _sha(downloaded) != expected_digest:
                raise EvidenceArchiveError(f"archive_readback_digest_mismatch:{label}")
        head = client.head_object(Bucket=bucket, Key=key)
        receipt_objects.append({
            "kind": label,
            "key": key,
            "sha256": expected_digest,
            "bytes": len(body),
            "version_id": head.get("VersionId"),
        })

    receipt = {
        "schema": "veltrix-evidence-archive-receipt-v1",
        "provider": "fivedollar",
        "run_id": run_id,
        "report_sha256": integrity["report_sha256"],
        "evidence_count": integrity["input_count"],
        "archived_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "bucket": bucket,
        "objects": receipt_objects,
        "readback_verified": True,
        "raw_payloads": "encrypted_only",
    }
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
    receipt_key = f"{base}receipts/{run_id}.json"
    if _head_exists(client, bucket, receipt_key):
        # A prior attempt may have completed the commit marker but failed
        # before writing its local receipt. Reuse it only after validating
        # its run/report/object bindings and its own read-back digest.
        downloaded_receipt = client.get_object(Bucket=bucket, Key=receipt_key)["Body"].read()
        try:
            archived_receipt = json.loads(downloaded_receipt)
        except (TypeError, ValueError):
            raise EvidenceArchiveError("archive_existing_receipt_invalid") from None
        if (archived_receipt.get("schema") != "veltrix-evidence-archive-receipt-v1"
                or archived_receipt.get("run_id") != run_id
                or archived_receipt.get("report_sha256") != integrity["report_sha256"]
                or archived_receipt.get("objects") != receipt_objects
                or archived_receipt.get("readback_verified") is not True):
            raise EvidenceArchiveError("archive_existing_receipt_binding_conflict")
        receipt = archived_receipt
        receipt_bytes = downloaded_receipt
    else:
        client.put_object(
            Bucket=bucket, Key=receipt_key, Body=receipt_bytes,
            ContentType="application/json",
            Metadata={"sha256": _sha(receipt_bytes), "run-id": run_id},
        )
        downloaded_receipt = client.get_object(Bucket=bucket, Key=receipt_key)["Body"].read()
        if _sha(downloaded_receipt) != _sha(receipt_bytes):
            raise EvidenceArchiveError("archive_receipt_readback_failed")
    receipt["receipt_key"] = receipt_key
    receipt["receipt_sha256"] = _sha(receipt_bytes)
    Path(receipt_output_path).write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="fivedollar_history_batch.json")
    parser.add_argument("--evidence", default="fivedollar_source_evidence.enc")
    parser.add_argument("--manifest", default="fivedollar_source_evidence.enc.manifest.json")
    args = parser.parse_args()
    try:
        endpoint = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_ENDPOINT_URL")
        bucket = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_BUCKET")
        access = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_ACCESS_KEY_ID")
        secret = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_SECRET_ACCESS_KEY")
        region = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_REGION", "auto")
        prefix = os.getenv("VELTRIX_EVIDENCE_ARCHIVE_PREFIX", "veltrix-football/evidence/v1")
        if not all((endpoint, bucket, access, secret)):
            raise EvidenceArchiveError("private_evidence_archive_configuration_missing")
        import boto3
        client = boto3.client(
            "s3", endpoint_url=endpoint, region_name=region,
            aws_access_key_id=access, aws_secret_access_key=secret,
        )
        receipt = archive_evidence(
            client=client, bucket=bucket, prefix=prefix,
            report_path=args.report, evidence_path=args.evidence,
            manifest_path=args.manifest,
        )
        print(
            "PRIVATE_EVIDENCE_ARCHIVE: PASS; "
            f"run_id={receipt['run_id']}; objects={len(receipt['objects'])}; "
            f"readback_verified={receipt['readback_verified']}; "
            f"receipt={receipt['receipt_key']}"
        )
        return 0
    except Exception as exc:
        print(f"PRIVATE_EVIDENCE_ARCHIVE: FAIL ({type(exc).__name__}: {str(exc)[:180]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
