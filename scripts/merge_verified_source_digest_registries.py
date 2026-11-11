#!/usr/bin/env python3
"""Verify and merge signed archive digest registries without provider access."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evidence_receipt_signing import SCHEMA_V2, ReceiptSignatureError, sign_receipt
from app.evidence_receipt_trust import (
    ReceiptTrustError, parse_trusted_key_regions, verify_receipt_with_trusted_clients,
)


class RegistryMergeError(ValueError):
    pass


def _read(path: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RegistryMergeError(f"registry_unreadable:{Path(path).name}") from None
    if not isinstance(value, dict):
        raise RegistryMergeError(f"registry_not_object:{Path(path).name}")
    return value


def _validate_registry(value: dict, clients: dict) -> tuple[set[str], dict[str, dict]]:
    if value.get("schema") != SCHEMA_V2 or value.get("schema_version") != 1:
        raise RegistryMergeError("registry_schema_invalid")
    try:
        verify_receipt_with_trusted_clients(
            receipt=value, trusted_kms_clients=clients,
        )
    except ReceiptTrustError:
        raise RegistryMergeError("registry_signature_or_trust_invalid") from None
    digests = value.get("verified_source_evidence_sha256")
    receipts = value.get("verified_archive_receipts")
    if not isinstance(digests, list) or not isinstance(receipts, list) or not receipts:
        raise RegistryMergeError("registry_content_invalid")
    for digest in digests:
        if (not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            raise RegistryMergeError("registry_digest_invalid")
    indexed = {}
    for receipt in receipts:
        if (not isinstance(receipt, dict)
                or receipt.get("archive_receipt_signature_verified") is not True
                or not isinstance(receipt.get("receipt_sha256"), str)
                or len(receipt["receipt_sha256"]) != 64
                or not isinstance(receipt.get("receipt_signing_key_arn"), str)
                or not receipt["receipt_signing_key_arn"].startswith("arn:aws:kms:")
                or not isinstance(receipt.get("run_id"), str) or not receipt["run_id"]):
            raise RegistryMergeError("registry_receipt_attestation_invalid")
        key = receipt["receipt_sha256"]
        normalized = {
            "archive_receipt_signature_verified": True,
            "receipt_sha256": key,
            "receipt_signing_key_arn": receipt["receipt_signing_key_arn"],
            "run_id": receipt["run_id"],
        }
        if key in indexed and indexed[key] != normalized:
            raise RegistryMergeError("conflicting_receipt_attestation")
        indexed[key] = normalized
    return set(digests), indexed


def merge_registries(*, input_paths: list[str], output_path: str,
                     trusted_kms_clients: dict, signing_key_arn: str) -> dict:
    if not isinstance(input_paths, list) or not input_paths:
        raise RegistryMergeError("registry_inputs_required")
    if signing_key_arn not in trusted_kms_clients:
        raise RegistryMergeError("registry_signing_key_not_trusted")
    digests: set[str] = set()
    receipts: dict[str, dict] = {}
    for path in input_paths:
        source_digests, source_receipts = _validate_registry(_read(path), trusted_kms_clients)
        digests.update(source_digests)
        for receipt_sha, attestation in source_receipts.items():
            if receipt_sha in receipts and receipts[receipt_sha] != attestation:
                raise RegistryMergeError("conflicting_receipt_attestation")
            receipts[receipt_sha] = attestation
    if not digests or not receipts:
        raise RegistryMergeError("merged_registry_empty")
    unsigned = {
        "schema": SCHEMA_V2,
        "schema_version": 1,
        "verified_source_evidence_sha256": sorted(digests),
        "verified_archive_receipts": sorted(
            receipts.values(), key=lambda item: (item["run_id"], item["receipt_sha256"]),
        ),
    }
    try:
        signed = sign_receipt(
            kms_client=trusted_kms_clients[signing_key_arn],
            key_arn=signing_key_arn, receipt=unsigned,
        )
    except ReceiptSignatureError:
        raise RegistryMergeError("merged_registry_signing_failed") from None
    destination = Path(output_path)
    if destination.is_symlink():
        raise RegistryMergeError("output_symlink_rejected")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not destination.is_file():
        raise RegistryMergeError("output_not_regular_file")
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(signed, stream, sort_keys=True, indent=2, ensure_ascii=False)
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
    return {
        "valid": True, "input_registry_count": len(input_paths),
        "verified_source_digest_count": len(digests),
        "verified_archive_receipt_count": len(receipts),
        "signing_key_arn": signing_key_arn,
        "output": str(destination),
        "provider_requests": 0, "database_writes": 0,
        "prediction_publications": 0, "telegram_deliveries": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("registries", nargs="+")
    args = parser.parse_args()
    try:
        registry_json = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON")
        legacy_key = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_KEY_ARN")
        legacy_region = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_REGION")
        regions = parse_trusted_key_regions(
            registry_json=registry_json, legacy_key_arn=legacy_key,
            legacy_region=legacy_region,
        )
        import boto3
        clients = {
            arn: boto3.client("kms", region_name=region)
            for arn, region in regions.items()
        }
        signer = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_KEY_ARN")
        if not signer:
            raise RegistryMergeError("registry_signing_key_missing")
        result = merge_registries(
            input_paths=args.registries, output_path=args.output,
            trusted_kms_clients=clients, signing_key_arn=signer,
        )
        print("VERIFIED_DIGEST_REGISTRY_MERGE: PASS; " + json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, ReceiptTrustError) as exc:
        print(f"VERIFIED_DIGEST_REGISTRY_MERGE: FAIL ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
