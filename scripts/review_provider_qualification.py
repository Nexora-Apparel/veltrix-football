#!/usr/bin/env python3
"""Review a completed GitHub Actions StrikerAPI qualification artifact offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.provider_qualification_evidence import (
    QualificationEvidenceError,
    build_review_attestation,
    validate_artifact_metadata,
    validate_coverage_report,
    validate_run_metadata,
)

WORKFLOW = ".github/workflows/verify-strikerapi-17-competitions.yml"
ARTIFACT_NAME = "strikerapi-17-competition-coverage"
REPORT_NAME = "strikerapi_17_competition_coverage.json"
API = "https://api.github.com"
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_REPORT_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 50


def read_limited(stream, limit: int) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("download_or_report_size_limit_exceeded")
    return data


def gh_json(endpoint: str) -> dict:
    completed = subprocess.run(
        ["gh", "api", endpoint],
        check=False, capture_output=True, text=True, timeout=30,
    )
    if completed.returncode:
        raise RuntimeError("github_api_request_failed:" + completed.stderr.strip()[:180])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("github_api_response_not_json") from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_artifact_zip(repo: str, artifact_id: int, destination: Path) -> None:
    token_result = subprocess.run(
        ["gh", "auth", "token"], check=False, capture_output=True,
        text=True, timeout=15,
    )
    token = token_result.stdout.strip()
    if token_result.returncode or not token:
        raise RuntimeError("github_cli_authentication_required")
    url = f"{API}/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "veltrix-qualification-reviewer",
    })
    opener = urllib.request.build_opener(NoRedirect)
    try:
        response = opener.open(request, timeout=30)
        data = read_limited(response, MAX_ARCHIVE_BYTES)
    except urllib.error.HTTPError as exc:
        if exc.code != 302:
            raise RuntimeError(f"artifact_download_http_{exc.code}") from None
        location = exc.headers.get("Location")
        if not location:
            raise RuntimeError("artifact_download_redirect_missing") from None
        # The redirect is a short-lived signed URL; do not forward the GitHub token.
        with urllib.request.urlopen(location, timeout=60) as response:
            data = read_limited(response, MAX_ARCHIVE_BYTES)
    if not data.startswith(b"PK"):
        raise RuntimeError("artifact_download_not_zip")
    destination.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="owner/repository")
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output", default="provider_qualification_registry.reviewed.json")
    args = parser.parse_args()

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
        artifacts_response = gh_json(
            f"repos/{args.repository}/actions/runs/{args.run_id}/artifacts"
        )
        artifacts = artifacts_response.get("artifacts")
        if not isinstance(artifacts, list):
            raise QualificationEvidenceError("artifact_list_missing")
        matches = [item for item in artifacts if item.get("name") == ARTIFACT_NAME]
        if len(matches) != 1:
            raise QualificationEvidenceError("expected_exactly_one_qualification_artifact")
        artifact_evidence = validate_artifact_metadata(
            matches[0], expected_name=ARTIFACT_NAME
        )

        with tempfile.TemporaryDirectory(prefix="veltrix-qualification-") as temp:
            archive = Path(temp) / "qualification.zip"
            download_artifact_zip(args.repository, artifact_evidence["artifact_id"], archive)
            archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
            if archive_sha != artifact_evidence["github_artifact_digest"]:
                raise QualificationEvidenceError("github_artifact_digest_mismatch")
            with zipfile.ZipFile(archive) as bundle:
                members = bundle.infolist()
                if len(members) > MAX_ARCHIVE_ENTRIES:
                    raise QualificationEvidenceError("artifact_archive_entry_limit_exceeded")
                files = [item for item in members
                         if Path(item.filename).name == REPORT_NAME
                         and not item.is_dir()]
                if len(files) != 1:
                    raise QualificationEvidenceError("coverage_report_missing_or_ambiguous")
                if files[0].file_size > MAX_REPORT_BYTES:
                    raise QualificationEvidenceError("coverage_report_size_limit_exceeded")
                report_bytes = bundle.read(files[0])
            report_sha = hashlib.sha256(report_bytes).hexdigest()
            try:
                report = json.loads(report_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise QualificationEvidenceError("coverage_report_not_valid_json") from None

        coverage = validate_coverage_report(report)
        attestation = build_review_attestation(
            run=run_evidence, artifact=artifact_evidence,
            archive_sha256=archive_sha, report_sha256=report_sha,
            coverage=coverage, reviewer=args.reviewer,
            reviewed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            signing_key=signing_key,
        )
        run_url = f"https://github.com/{args.repository}/actions/runs/{args.run_id}"
        sources = []
        for competition in coverage["competition_keys"]:
            sources.append({
                "provider": "strikerapi",
                "competition_key": competition,
                "qualification_status": "qualified",
                "qualification_run_id": str(args.run_id),
                "artifact_sha256": archive_sha,
                "evidence_ref": run_url + f"/artifacts/{artifact_evidence['artifact_id']}",
                "pagination_complete": True,
                "invalid_rows": 0,
                "duplicate_rows": 0,
                "review_attestation": attestation,
            })
        output = {
            "schema_version": 1,
            "registry_status": "reviewed_github_artifact_evidence",
            "sources": sources,
        }
        Path(args.output).write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("QUALIFICATION_REVIEW: PASS")
        print(f"WORKFLOW_RUN: {args.run_id}")
        print(f"HEAD_SHA: {run_evidence['head_sha']}")
        print(f"ARTIFACT_SHA256: {archive_sha}")
        print(f"REPORT_SHA256: {report_sha}")
        print(f"QUALIFIED_COMPETITIONS: {coverage['competition_count']}")
        print(f"REGISTRY_OUTPUT: {args.output}")
        print("PROVIDER_REQUESTS: 0; DATABASE_WRITES: 0; IMPORTS: 0")
        return 0
    except (QualificationEvidenceError, RuntimeError, OSError, zipfile.BadZipFile,
            subprocess.TimeoutExpired, urllib.error.URLError) as exc:
        reason = str(exc).replace("\n", " ")[:200]
        print(f"QUALIFICATION_REVIEW: REJECTED ({reason})")
        print("NO_REGISTRY_WRITTEN: true")
        return 1


if __name__ == "__main__":
    sys.exit(main())
