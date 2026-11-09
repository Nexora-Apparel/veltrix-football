#!/usr/bin/env python3
"""Review a completed manual 5Dollar qualification artifact using GitHub metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.fivedollar_qualification_report import validate_fivedollar_qualification_report
from app.fivedollar_qualification_review import build_fivedollar_registry
from app.provider_qualification_evidence import (
    QualificationEvidenceError,
    validate_artifact_metadata,
    validate_run_metadata,
)
from scripts.review_provider_qualification import download_artifact_zip, gh_json

WORKFLOW = ".github/workflows/qualify-fivedollar-competitions.yml"
ARTIFACT_NAME = "fivedollar-competition-qualification"
REPORT_NAME = "fivedollar_competition_qualification.json"
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_REPORT_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 50


def extract_report(archive: Path) -> bytes:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise QualificationEvidenceError("artifact_archive_entry_limit_exceeded")
        matches = [item for item in members
                   if Path(item.filename).name == REPORT_NAME and not item.is_dir()]
        if len(matches) != 1:
            raise QualificationEvidenceError("qualification_report_missing_or_ambiguous")
        if matches[0].file_size > MAX_REPORT_BYTES:
            raise QualificationEvidenceError("qualification_report_size_limit_exceeded")
        return bundle.read(matches[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output", default="data/provider_qualification_registry.reviewed.json")
    args = parser.parse_args()

    if args.expected_branch != "phase-3/budget-aware-acquisition-contract":
        print("QUALIFICATION_REVIEW: REJECTED (unexpected_qualification_branch)")
        return 2
    if len(args.expected_head_sha) != 40 or any(c not in "0123456789abcdef" for c in args.expected_head_sha.lower()):
        print("QUALIFICATION_REVIEW: REJECTED (expected_head_sha_invalid)")
        return 2
    signing_key = os.getenv("VELTRIX_QUALIFICATION_ATTESTATION_KEY", "")
    if len(signing_key) < 32:
        print("QUALIFICATION_REVIEW: REJECTED (VELTRIX_QUALIFICATION_ATTESTATION_KEY missing_or_weak)")
        print("NO_REGISTRY_WRITTEN: true")
        return 2

    try:
        run = gh_json(f"repos/{args.repository}/actions/runs/{args.run_id}")
        run_evidence = validate_run_metadata(
            run, repository=args.repository, workflow_path=WORKFLOW,
            expected_branch=args.expected_branch, expected_sha=args.expected_head_sha,
        )
        artifacts_response = gh_json(f"repos/{args.repository}/actions/runs/{args.run_id}/artifacts")
        artifacts = artifacts_response.get("artifacts")
        if not isinstance(artifacts, list):
            raise QualificationEvidenceError("artifact_list_missing")
        matches = [item for item in artifacts if item.get("name") == ARTIFACT_NAME]
        if len(matches) != 1:
            raise QualificationEvidenceError("expected_exactly_one_qualification_artifact")
        artifact = validate_artifact_metadata(matches[0], expected_name=ARTIFACT_NAME)

        with tempfile.TemporaryDirectory(prefix="veltrix-fivedollar-review-") as temp:
            archive = Path(temp) / "qualification.zip"
            download_artifact_zip(args.repository, artifact["artifact_id"], archive)
            archive_bytes = archive.read_bytes()
            if len(archive_bytes) > MAX_ARCHIVE_BYTES:
                raise QualificationEvidenceError("artifact_archive_size_limit_exceeded")
            archive_sha = hashlib.sha256(archive_bytes).hexdigest()
            if archive_sha != artifact["github_artifact_digest"]:
                raise QualificationEvidenceError("github_artifact_digest_mismatch")
            report_bytes = extract_report(archive)
            report_sha = hashlib.sha256(report_bytes).hexdigest()
            try:
                report = json.loads(report_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise QualificationEvidenceError("qualification_report_not_valid_json") from None

        validation = validate_fivedollar_qualification_report(report)
        if not validation["acceptance_pass"]:
            raise QualificationEvidenceError("qualification_report_acceptance_not_passed")
        artifact_url = (
            f"https://github.com/{args.repository}/actions/runs/{args.run_id}"
            f"/artifacts/{artifact['artifact_id']}"
        )
        registry = build_fivedollar_registry(
            run=run_evidence, artifact=artifact, report=report,
            archive_sha256=archive_sha, report_sha256=report_sha,
            reviewer=args.reviewer,
            reviewed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            signing_key=signing_key, artifact_url=artifact_url,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("QUALIFICATION_REVIEW: PASS")
        print(f"WORKFLOW_RUN: {args.run_id}")
        print(f"HEAD_SHA: {run_evidence['head_sha']}")
        print(f"ARTIFACT_SHA256: {archive_sha}")
        print(f"REPORT_SHA256: {report_sha}")
        print(f"QUALIFIED_COMPETITIONS: {validation['competition_count']}")
        print(f"REGISTRY_OUTPUT: {output}")
        print("PROVIDER_REQUESTS: 0; DATABASE_WRITES: 0; IMPORTS: 0")
        return 0
    except (QualificationEvidenceError, RuntimeError, OSError, zipfile.BadZipFile,
            KeyError, ValueError) as exc:
        print(f"QUALIFICATION_REVIEW: REJECTED ({str(exc).replace(chr(10), ' ')[:200]})")
        print("NO_REGISTRY_WRITTEN: true")
        return 1


if __name__ == "__main__":
    sys.exit(main())
