#!/usr/bin/env python3
"""Local evidence certification runner for walk-forward, odds and prospective evidence.\n\nIt verifies the digest-registry signature against the out-of-band KMS key allowlist.

This command evaluates evidence only. It never requests provider data, writes
Neon, executes bets, publishes predictions or sends Telegram messages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.market_release_certification import (
    CertificationError, evaluate_market_release_certification,
)
from app.prospective_value_selection_ledger import (
    ProspectiveValueLedgerError, export_settled_certification_rows,
)
from app.evidence_receipt_trust import (
    ReceiptTrustError, parse_trusted_key_regions,
    verify_receipt_with_trusted_clients,
)
from app.walk_forward_certification_adapter import (
    WalkForwardCertificationAdapterError, build_market_certification_evidence,
)


class CertificationRunnerError(RuntimeError):
    pass


def _read_object(path: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise CertificationRunnerError(f"input_unreadable:{Path(path).name}") from None
    if not isinstance(value, dict):
        raise CertificationRunnerError(f"input_not_object:{Path(path).name}")
    return value


def _verified_digest_registry(value: dict, trusted_kms_clients: dict) -> list[str]:
    if value.get("schema") != "veltrix-evidence-archive-receipt-v2" or value.get("schema_version") != 1:
        raise CertificationRunnerError("verified_digest_registry_schema_invalid")
    digests = value.get("verified_source_evidence_sha256")
    receipts = value.get("verified_archive_receipts")
    if not isinstance(digests, list) or not digests or not isinstance(receipts, list) or not receipts:
        raise CertificationRunnerError("verified_digest_registry_content_invalid")
    for digest in digests:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise CertificationRunnerError("verified_digest_registry_digest_invalid")
    try:
        verified_key_arn = verify_receipt_with_trusted_clients(
            receipt=value, trusted_kms_clients=trusted_kms_clients,
        )
    except ReceiptTrustError:
        raise CertificationRunnerError("verified_digest_registry_signature_invalid") from None
    for receipt in receipts:
        if (not isinstance(receipt, dict)
                or receipt.get("archive_receipt_signature_verified") is not True
                or not isinstance(receipt.get("receipt_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", receipt["receipt_sha256"])
                or not isinstance(receipt.get("receipt_signing_key_arn"), str)
                or not receipt.get("receipt_signing_key_arn")
                or not isinstance(receipt.get("run_id"), str)
                or not receipt.get("run_id")
                or receipt.get("receipt_signing_key_arn") != verified_key_arn):
            raise CertificationRunnerError("verified_archive_receipt_attestation_invalid")
    return digests


def _atomic_write(path: str, value: dict) -> None:
    destination = Path(path)
    if destination.is_symlink():
        raise CertificationRunnerError("output_symlink_rejected")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not destination.is_file():
        raise CertificationRunnerError("output_not_regular_file")
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, destination)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def evaluate(*, walk_forward_path: str, odds_ledger_path: str,
             prospective_ledger_path: str, verified_digests_path: str,
             benchmark_bookmaker: str, evaluated_at: str,
             output_path: str, trusted_kms_clients: dict) -> dict:
    walk_forward = _read_object(walk_forward_path)
    odds_ledger = _read_object(odds_ledger_path)
    prospective_ledger = _read_object(prospective_ledger_path)
    verified_registry = _read_object(verified_digests_path)
    verified_digests = _verified_digest_registry(verified_registry, trusted_kms_clients)
    try:
        prospective = export_settled_certification_rows(
            ledger=prospective_ledger, evaluated_at=evaluated_at,
        )
        joined = build_market_certification_evidence(
            walk_forward_report=walk_forward,
            odds_ledger=odds_ledger,
            prospective_selections=prospective["prospective"],
            benchmark_bookmaker=benchmark_bookmaker,
        )
        report = evaluate_market_release_certification(
            evidence=joined["evidence"],
            evaluated_at=evaluated_at,
            verified_source_evidence_sha256=verified_digests,
        )
    except (CertificationError, ProspectiveValueLedgerError,
            WalkForwardCertificationAdapterError) as exc:
        raise CertificationRunnerError(str(exc)) from None
    report["input_bindings"] = {
        "walk_forward_report_sha256": joined["walk_forward_report_sha256"],
        "odds_ledger_observation_count": joined["odds_ledger_observation_count"],
        "benchmark_bookmaker": benchmark_bookmaker,
        "prospective_settled_selection_count": prospective["settled_selection_count"],
        "verified_digest_registry_sha256": hashlib.sha256(
            json.dumps(verified_registry, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest(),
    }
    report["side_effects"] = {
        "provider_requests": 0, "database_writes": 0,
        "real_money_orders": 0, "prediction_publications": 0,
        "telegram_deliveries": 0, "schedules_activated": 0,
    }
    _atomic_write(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--walk-forward-report", required=True)
    parser.add_argument("--odds-ledger", required=True)
    parser.add_argument("--prospective-ledger", required=True)
    parser.add_argument("--verified-digests", required=True)
    parser.add_argument("--benchmark-bookmaker", required=True)
    parser.add_argument("--evaluated-at", required=True)
    parser.add_argument("--output", default="market-release-certification.json")
    args = parser.parse_args()
    try:
        registry_json = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON")
        legacy_key_arn = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_KEY_ARN")
        legacy_region = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_REGION")
        trusted_regions = parse_trusted_key_regions(
            registry_json=registry_json, legacy_key_arn=legacy_key_arn,
            legacy_region=legacy_region,
        )
        import boto3
        trusted_kms_clients = {
            key_arn: boto3.client("kms", region_name=region)
            for key_arn, region in trusted_regions.items()
        }
        report = evaluate(
            walk_forward_path=args.walk_forward_report,
            odds_ledger_path=args.odds_ledger,
            prospective_ledger_path=args.prospective_ledger,
            verified_digests_path=args.verified_digests,
            benchmark_bookmaker=args.benchmark_bookmaker,
            evaluated_at=args.evaluated_at,
            output_path=args.output,
            trusted_kms_clients=trusted_kms_clients,
        )
        print(
            "MARKET_RELEASE_CERTIFICATION: PASS; "
            f"thresholds_met={report['value_betting_thresholds_met']}; "
            f"value_betting_authorized={report['value_betting_authorized']}; "
            f"publication_authorized={report['publication_authorized']}; "
            f"output={args.output}"
        )
        return 0
    except (OSError, ValueError, TypeError, CertificationRunnerError, ReceiptTrustError) as exc:
        print(f"MARKET_RELEASE_CERTIFICATION: FAIL ({type(exc).__name__}: {str(exc)[:180]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
