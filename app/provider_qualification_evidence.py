"""Strict, offline validators for GitHub-backed provider qualification evidence."""
from __future__ import annotations

import hashlib
import re
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
STRIKERAPI_COMPETITIONS = {
    "soccer", "mls", "laliga", "seriea", "bundesliga", "ligue1", "ucl",
    "championship", "nwsl", "ligamx", "uel", "uecl", "eredivisie",
    "primeira", "scotland", "brazil", "argentina",
}


class QualificationEvidenceError(ValueError):
    pass


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise QualificationEvidenceError(code)


def validate_run_metadata(run: Any, *, repository: str, workflow_path: str,
                          expected_branch: str, expected_sha: str) -> dict:
    _require(isinstance(run, dict), "workflow_run_not_object")
    repo = run.get("repository") or {}
    _require(repo.get("full_name", "").lower() == repository.lower(), "workflow_repository_mismatch")
    _require(run.get("path") == workflow_path, "workflow_path_mismatch")
    _require(run.get("event") == "workflow_dispatch", "workflow_event_not_manual_dispatch")
    _require(run.get("status") == "completed" and run.get("conclusion") == "success",
             "workflow_run_not_successful")
    _require(run.get("head_branch") == expected_branch, "workflow_branch_mismatch")
    _require(run.get("head_sha") == expected_sha, "workflow_commit_mismatch")
    _require(isinstance(run.get("id"), int) and not isinstance(run.get("id"), bool),
             "workflow_run_id_invalid")
    _require(bool(run.get("created_at")) and bool(run.get("updated_at")),
             "workflow_run_timestamps_missing")
    return {
        "repository": repository,
        "workflow_run_id": str(run["id"]),
        "workflow_path": workflow_path,
        "event": run["event"],
        "conclusion": run["conclusion"],
        "head_branch": run["head_branch"],
        "head_sha": run["head_sha"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
    }


def validate_artifact_metadata(artifact: Any, *, expected_name: str) -> dict:
    _require(isinstance(artifact, dict), "artifact_metadata_not_object")
    _require(artifact.get("name") == expected_name, "artifact_name_mismatch")
    _require(artifact.get("expired") is False, "artifact_expired_or_unknown")
    _require(isinstance(artifact.get("id"), int) and not isinstance(artifact.get("id"), bool),
             "artifact_id_invalid")
    digest = artifact.get("digest")
    _require(isinstance(digest, str) and digest.startswith("sha256:"), "artifact_digest_missing")
    digest_hex = digest.removeprefix("sha256:")
    _require(bool(SHA256.fullmatch(digest_hex)), "artifact_digest_invalid")
    return {"artifact_id": artifact["id"], "artifact_name": expected_name,
            "github_artifact_digest": digest_hex, "expires_at": artifact.get("expires_at")}


def validate_coverage_report(report: Any) -> dict:
    _require(isinstance(report, dict), "coverage_report_not_object")
    _require(report.get("schema_version") == 1, "coverage_schema_unsupported")
    _require(report.get("mode") == "read_only_17_competition_rolling_coverage",
             "coverage_mode_mismatch")
    _require(report.get("provider") == "StrikerAPI", "coverage_provider_mismatch")
    _require(report.get("competition_count") == 17 and report.get("check_count") == 34,
             "coverage_check_count_mismatch")
    _require(report.get("acceptance_pass") is True, "coverage_acceptance_not_passed")
    totals = report.get("totals")
    _require(isinstance(totals, dict), "coverage_totals_missing")
    _require(isinstance(totals.get("rows"), int) and totals["rows"] > 0,
             "coverage_has_no_observations")
    _require(totals.get("invalid") == 0, "coverage_invalid_rows_nonzero")
    _require(totals.get("duplicate_ids") == 0, "coverage_duplicate_ids_nonzero")
    _require(report.get("truncated_checks") == [], "coverage_pagination_truncated")
    for key in ("database_writes", "imports", "checkpoints", "canonical_merges"):
        _require(report.get(key) == 0, f"coverage_side_effect_nonzero:{key}")

    checks = report.get("checks")
    _require(isinstance(checks, list) and len(checks) == 34, "coverage_checks_invalid")
    observed: dict[str, set[str]] = {}
    accepted_by_competition: dict[str, int] = {}
    for row in checks:
        _require(isinstance(row, dict), "coverage_check_row_invalid")
        league, status = row.get("league_key"), row.get("status")
        _require(league in STRIKERAPI_COMPETITIONS, "coverage_unknown_competition")
        _require(status in {"final", "scheduled"}, "coverage_unknown_status")
        observed.setdefault(league, set()).add(status)
        for field in ("rows", "valid", "invalid", "duplicate_ids", "pages"):
            _require(isinstance(row.get(field), int) and not isinstance(row.get(field), bool)
                     and row[field] >= 0, f"coverage_check_count_invalid:{field}")
        _require(row.get("invalid") == 0 and row.get("duplicate_ids") == 0,
                 "coverage_check_quality_failure")
        _require(row.get("pagination_truncated") is False, "coverage_check_truncated")
        _require(row.get("valid") == row.get("rows"), "coverage_check_accounting_mismatch")
        if status == "final" and row["rows"] > 0:
            accepted_by_competition[league] = row["valid"]
    _require(set(observed) == STRIKERAPI_COMPETITIONS, "coverage_competition_scope_incomplete")
    _require(all(statuses == {"final", "scheduled"} for statuses in observed.values()),
             "coverage_status_scope_incomplete")
    _require(sum(row["rows"] for row in checks) == totals["rows"],
             "coverage_total_rows_mismatch")
    _require(sum(row["valid"] for row in checks) == totals.get("valid"),
             "coverage_total_valid_mismatch")
    _require(sum(row["invalid"] for row in checks) == totals["invalid"],
             "coverage_total_invalid_mismatch")
    _require(sum(row["duplicate_ids"] for row in checks) == totals["duplicate_ids"],
             "coverage_total_duplicates_mismatch")
    budget = report.get("request_budget")
    _require(isinstance(budget, dict), "coverage_request_budget_missing")
    _require(budget.get("maximum_calls") == 102 and budget.get("actual_calls", 103) <= 102,
             "coverage_request_budget_invalid")
    _require(budget.get("actual_documented_credits") == budget.get("actual_calls", -1) * 2,
             "coverage_credit_accounting_mismatch")
    return {
        "provider": "strikerapi",
        "competition_keys": sorted(accepted_by_competition),
        "competition_count": len(accepted_by_competition),
        "observed_competition_count": len(observed),
        "check_count": 34,
        "final_rows_by_competition": dict(sorted(accepted_by_competition.items())),
        "invalid_rows": 0,
        "duplicate_rows": 0,
        "pagination_complete": True,
        "report_retrieved_at": report.get("retrieved_at"),
        "actual_calls": budget["actual_calls"],
        "actual_credits": budget["actual_documented_credits"],
    }


def build_review_attestation(*, run: dict, artifact: dict, archive_sha256: str,
                             report_sha256: str, coverage: dict,
                             reviewer: str, reviewed_at: str) -> dict:
    _require(bool(SHA256.fullmatch(archive_sha256)), "local_archive_sha256_invalid")
    _require(bool(SHA256.fullmatch(report_sha256)), "local_report_sha256_invalid")
    _require(bool(reviewer.strip()) and bool(reviewed_at.strip()), "reviewer_identity_or_time_missing")
    return {
        "attestation_version": 1,
        "review_status": "qualified",
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "repository": run["repository"],
        "workflow_run_id": run["workflow_run_id"],
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
