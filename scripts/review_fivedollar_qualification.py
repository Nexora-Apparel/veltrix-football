#!/usr/bin/env python3
"""Review a completed manual 5Dollar qualification artifact using GitHub metadata."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.fivedollar_qualification_report import validate_fivedollar_qualification_report
from app.fivedollar_qualification_review import build_fivedollar_registry
from app.provider_qualification_evidence import (
    QualificationEvidenceError,
    validate_artifact_metadata,
    validate_checkout_metadata,
    validate_run_metadata,
)
from scripts.review_provider_qualification import download_artifact_zip, gh_json

WORKFLOW = ".github/workflows/qualify-fivedollar-competitions.yml"
ARTIFACT_NAME = "fivedollar-competition-qualification"
REPORT_NAME = "fivedollar_competition_qualification.json"
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_REPORT_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 50
MAX_JOB_LOG_BYTES = 20 * 1024 * 1024


def download_job_logs(repository: str, job_id: int) -> str:
    """Download the authenticated GitHub job-log ZIP without leaking the token."""
    token_result = subprocess.run(
        ["gh", "auth", "token"], check=False, capture_output=True,
        text=True, timeout=15,
    )
    token = token_result.stdout.strip()
    if token_result.returncode or not token:
        raise RuntimeError("github_cli_authentication_required")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/jobs/{job_id}/logs",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "veltrix-qualification-reviewer",
        },
    )
    opener = urllib.request.build_opener()
    try:
        with opener.open(request, timeout=30) as response:
            archive_bytes = response.read(MAX_JOB_LOG_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code != 302:
            raise RuntimeError(f"job_log_download_http_{exc.code}") from None
        location = exc.headers.get("Location")
        if not location:
            raise RuntimeError("job_log_redirect_missing") from None
        with urllib.request.urlopen(location, timeout=60) as response:
            archive_bytes = response.read(MAX_JOB_LOG_BYTES + 1)
    if len(archive_bytes) > MAX_JOB_LOG_BYTES:
        raise RuntimeError("job_log_archive_size_limit_exceeded")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as bundle:
            text_files = [item for item in bundle.infolist()
                          if not item.is_dir() and item.filename.endswith(".txt")]
            if not text_files:
                raise RuntimeError("job_log_text_missing")
            return "\n".join(bundle.read(item).decode("utf-8", errors="replace")
                              for item in text_files)
    except zipfile.BadZipFile:
        raise RuntimeError("job_log_download_not_zip") from None


def extract_report(archive: Path) -> bytes:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise QualificationEvidenceError("artifact_archive_entry_limit_exceeded")
        files = [item for item in members if not item.is_dir()]
        matches = [item for item in files if Path(item.filename).name == REPORT_NAME]
        if len(files) != 1 or len(matches) != 1:
            raise QualificationEvidenceError("qualification_report_missing_or_ambiguous")
        if matches[0].file_size > MAX_REPORT_BYTES:
            raise QualificationEvidenceError("qualification_report_size_limit_exceeded")
        return bundle.read(matches[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--expected-dispatch-ref", default="main")
    parser.add_argument("--expected-dispatch-sha",
                        default="a30348ee19bb601ed0047d226ba7bc89b19a8f59")
    parser.add_argument("--expected-checkout-ref",
                        default="phase-3/budget-aware-acquisition-contract")
    parser.add_argument("--expected-checkout-sha",
                        default="60cfbc3775b67e6a3227e6294c8fd458b1555bc0")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output", default="data/provider_qualification_registry.reviewed.json")
    args = parser.parse_args()

    for expected_sha in (args.expected_dispatch_sha, args.expected_checkout_sha):
        if len(expected_sha) != 40 or any(c not in "0123456789abcdef" for c in expected_sha.lower()):
            print("QUALIFICATION_REVIEW: REJECTED (expected_commit_sha_invalid)")
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
            expected_branch=args.expected_dispatch_ref, expected_sha=args.expected_dispatch_sha,
        )
        jobs_response = gh_json(
            f"repos/{args.repository}/actions/runs/{args.run_id}/jobs"
        )
        jobs = jobs_response.get("jobs")
        if not isinstance(jobs, list):
            raise QualificationEvidenceError("workflow_jobs_missing")
        matching_jobs = [job for job in jobs if job.get("name") == "qualify"]
        if len(matching_jobs) != 1 or matching_jobs[0].get("conclusion") != "success":
            raise QualificationEvidenceError("qualification_job_missing_or_unsuccessful")
        job_logs = download_job_logs(args.repository, matching_jobs[0]["id"])
        run_evidence.update(validate_checkout_metadata(
            job_logs, expected_ref=args.expected_checkout_ref,
            expected_sha=args.expected_checkout_sha,
        ))
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
        print(f"DISPATCH_REF: {run_evidence['dispatch_ref']}")
        print(f"DISPATCH_SHA: {run_evidence['dispatch_sha']}")
        print(f"CHECKOUT_REF: {run_evidence['checkout_ref']}")
        print(f"CHECKOUT_SHA: {run_evidence['checkout_sha']}")
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
