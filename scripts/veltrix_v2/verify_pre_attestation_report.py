#!/usr/bin/env python3
"""Verify report-bound statistical, provider-rights and source evidence before signing.

This command deliberately does not claim that an attestation already exists.
It validates every release condition other than the Sigstore proof that the
calling GitHub Actions job creates immediately after this succeeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from veltrix_v2.evaluation.publication_certification import (
    CERTIFICATION_MANIFEST_SCHEMA,
    verify_publication_authorization,
)
from veltrix_v2.reporting.report_identity import verify_report_identity
from veltrix_v2.reporting.trusted_runtime import (
    RAW_HOST,
    _strict_json,
    build_hash_checked_evidence_reader,
    build_provider_rights_evaluator,
)

REPOSITORY = "Nexora-Apparel/veltrix-football"
SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


def verify_pre_attestation_report(
    report_bytes: bytes,
    manifest_bytes: bytes,
    evidence_reader,
) -> tuple[bool, str]:
    try:
        report = _strict_json(report_bytes)
        manifest = _strict_json(manifest_bytes)
        identity = verify_report_identity(report)
        if not SAFE_REPORT_ID.fullmatch(identity.report_id):
            return False, "REPORT_ID_INVALID"
        if (
            not isinstance(manifest, dict)
            or manifest.get("manifest_schema") != CERTIFICATION_MANIFEST_SCHEMA
            or manifest.get("status") != "CERTIFIED"
            or manifest.get("report_id") != identity.report_id
            or manifest.get("report_sha256") != identity.report_sha256
            or not isinstance(manifest.get("certifications"), list)
            or not manifest["certifications"]
        ):
            return False, "REPORT_BOUND_MANIFEST_INVALID"
        if any(
            not isinstance(row, dict)
            or row.get("status") != "CERTIFIED"
            or row.get("blockers") != []
            for row in manifest["certifications"]
        ):
            return False, "CERTIFICATION_RECORD_NOT_QUALIFIED"
        rights_verifier = build_provider_rights_evaluator(evidence_reader)
        # The GitHub workflow creates the attestation only after this complete
        # preflight succeeds. Runtime consumers later require the actual Sigstore
        # attestation for the exact manifest bytes; this callback is never used
        # by the deployed verifier.
        authorized = verify_publication_authorization(
            report,
            manifest_bytes,
            lambda exact_bytes, digest: (
                isinstance(exact_bytes, bytes)
                and hashlib.sha256(exact_bytes).hexdigest() == digest
            ),
            rights_verifier,
            evidence_reader,
        )
        return (True, "PRE_ATTESTATION_RELEASE_EVIDENCE_VERIFIED") if authorized else (
            False, "PUBLICATION_EVIDENCE_NOT_QUALIFIED"
        )
    except Exception:
        return False, "PRE_ATTESTATION_VERIFICATION_FAILED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        hosts = frozenset({RAW_HOST})
        reader = build_hash_checked_evidence_reader(allowed_hosts=hosts)
        report_bytes = args.report.read_bytes()
        manifest_bytes = args.manifest.read_bytes()
        ok, code = verify_pre_attestation_report(report_bytes, manifest_bytes, reader)
    except Exception:
        ok, code = False, "PRE_ATTESTATION_INPUT_FAILED"
    print(json.dumps({"verified": ok, "result": code}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
