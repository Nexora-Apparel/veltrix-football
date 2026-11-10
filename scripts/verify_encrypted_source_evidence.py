#!/usr/bin/env python3
"""Verify a sanitized acquisition report against its encrypted raw-evidence sidecar."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.encrypted_source_evidence import decrypt_and_verify_source_evidence
from app.provider_acquisition_artifact import validate_fivedollar_history_batch_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="fivedollar_history_batch.json")
    parser.add_argument("--evidence", default="fivedollar_source_evidence.enc")
    parser.add_argument("--manifest", default="fivedollar_source_evidence.enc.manifest.json")
    args = parser.parse_args()
    try:
        key = os.getenv("VELTRIX_RAW_EVIDENCE_ENCRYPTION_KEY")
        if not key:
            raise ValueError("raw_evidence_encryption_key_missing")
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        integrity = validate_fivedollar_history_batch_report(report, require_acceptance=False)
        evidence = decrypt_and_verify_source_evidence(
            Path(args.evidence).read_bytes(), report=report, manifest=manifest, key=key
        )
        if len(evidence) != integrity["input_count"]:
            raise ValueError("encrypted_evidence_accepted_count_mismatch")
        print(
            "ENCRYPTED_EVIDENCE_VERIFICATION: PASS; "
            f"report_sha256={integrity['report_sha256']}; "
            f"accepted={integrity['accepted_count']}; "
            f"total_evidence={len(evidence)}; raw_payloads=encrypted_only"
        )
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"ENCRYPTED_EVIDENCE_VERIFICATION: FAIL ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
