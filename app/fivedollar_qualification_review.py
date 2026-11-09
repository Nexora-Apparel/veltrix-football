"""Convert independently verified 5Dollar artifacts into signed registry entries."""
from __future__ import annotations

import re

from app.fivedollar_qualification_report import validate_fivedollar_qualification_report
from app.provider_qualification_evidence import sign_attestation

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def build_fivedollar_registry(*, run: dict, artifact: dict, report: dict,
                              archive_sha256: str, report_sha256: str,
                              reviewer: str, reviewed_at: str,
                              signing_key: str, artifact_url: str) -> dict:
    integrity = validate_fivedollar_qualification_report(report)
    if not integrity["acceptance_pass"]:
        raise ValueError("fivedollar_report_not_qualified")
    if str(report.get("run_id")) != str(run.get("workflow_run_id")):
        raise ValueError("fivedollar_report_run_id_mismatch")
    if not isinstance(archive_sha256, str) or not _SHA256.fullmatch(archive_sha256):
        raise ValueError("fivedollar_archive_hash_invalid")
    if not isinstance(report_sha256, str) or not _SHA256.fullmatch(report_sha256):
        raise ValueError("fivedollar_report_hash_invalid")
    if not reviewer.strip() or not reviewed_at.strip():
        raise ValueError("fivedollar_reviewer_identity_missing")
    if run.get("event") != "workflow_dispatch":
        raise ValueError("fivedollar_run_event_invalid")
    if run.get("workflow_path") != ".github/workflows/qualify-fivedollar-competitions.yml":
        raise ValueError("fivedollar_workflow_path_invalid")
    if run.get("head_branch") != "phase-3/budget-aware-acquisition-contract":
        raise ValueError("fivedollar_run_branch_invalid")
    if artifact.get("artifact_name") != "fivedollar-competition-qualification":
        raise ValueError("fivedollar_artifact_name_invalid")
    if artifact.get("github_artifact_digest") != archive_sha256:
        raise ValueError("fivedollar_archive_digest_mismatch")
    expected_url = (f"https://github.com/{run.get('repository')}/actions/runs/"
                    f"{run.get('workflow_run_id')}/artifacts/{artifact.get('artifact_id')}")
    if artifact_url != expected_url:
        raise ValueError("fivedollar_artifact_url_invalid")

    competition_keys = sorted(str(row["competition_id"]) for row in report["competitions"])
    coverage = {
        "provider": "fivedollar",
        "competition_keys": competition_keys,
        "competition_count": len(competition_keys),
        "source_rows": report["aggregates"]["source_rows"],
        "accepted_rows": report["aggregates"]["accepted_rows"],
        "invalid_rows": report["aggregates"]["invalid_rows"],
        "duplicate_rows": report["aggregates"]["duplicate_ids"],
        "missing_team_ids": report["aggregates"]["missing_team_ids"],
        "pagination_complete": True,
        "window_start_utc": report["window_start_utc"],
        "window_end_utc": report["window_end_utc"],
    }
    unsigned = {
        "attestation_version": 1,
        "review_status": "qualified",
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "repository": run["repository"],
        "workflow_run_id": str(run["workflow_run_id"]),
        "workflow_path": run["workflow_path"],
        "event": run["event"],
        "head_branch": run["head_branch"],
        "head_sha": run["head_sha"],
        "artifact_id": artifact["artifact_id"],
        "artifact_name": artifact["artifact_name"],
        "github_artifact_digest": artifact["github_artifact_digest"],
        "local_archive_sha256": archive_sha256,
        "local_report_sha256": report_sha256,
        "coverage": coverage,
    }
    attestation = sign_attestation(unsigned, signing_key)
    sources = []
    for row in report["competitions"]:
        sources.append({
            "provider": "fivedollar",
            "competition_key": str(row["competition_id"]),
            "qualification_status": "qualified",
            "qualification_run_id": str(run["workflow_run_id"]),
            "artifact_sha256": archive_sha256,
            "evidence_ref": artifact_url,
            "pagination_complete": True,
            "invalid_rows": row["invalid_rows"],
            "duplicate_rows": row["duplicate_ids"],
            "missing_team_ids": row["missing_team_ids"],
            "review_attestation": attestation,
        })
    return {
        "schema_version": 1,
        "registry_status": "reviewed_github_artifact_evidence",
        "sources": sources,
    }
