"""Publish a small CI/live verification receipt to the command-data branch."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


BRANCH = "command-data"
PATH = "public-data/verification_status.json"


def _read_json(path_text: str) -> dict:
    if not path_text:
        return {}
    try:
        value = json.loads(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def build_status(env: dict[str, str]) -> dict:
    keys = (
        "unit_tests", "dashboard_js", "fixture_generation", "report_recovery",
        "same_day_report_download", "same_day_report_filter", "fixture_visibility", "odds_enrichment", "value_evidence_update",
        "value_evidence_artifact", "value_certificate", "telegram_webhook",
        "telegram_delivery", "daily_report_artifact", "paper_ledger_artifact",
        "command_data_publication", "paper_tracking",
    )
    steps = {key: env.get("VELTRIX_STEP_" + key.upper(), "not_run") for key in keys}
    critical = ("unit_tests", "dashboard_js")
    passed = all(steps[key] == "success" for key in critical)
    live = steps["fixture_generation"] == "success"
    report = _read_json(env.get("VELTRIX_REPORT_PATH", "reports/daily_predictions.json"))
    same_day_replay = (
        steps["same_day_report_filter"] == "success"
        and report.get("publication_status") == "REUSED_SNAPSHOT_NOT_REFRESHED"
    )
    recovered = steps["report_recovery"] == "success" or same_day_replay
    live_attempted = steps["fixture_generation"] not in {"skipped", "not_run"}
    if live_attempted and not live and not recovered:
        passed = False
    if live or recovered:
        passed = passed and steps["fixture_visibility"] == "success"
        passed = passed and steps["value_evidence_update"] == "success"
        passed = passed and steps["value_evidence_artifact"] == "success"
        passed = passed and steps["daily_report_artifact"] == "success"
        passed = passed and steps["paper_ledger_artifact"] in {"success", "skipped"}
        passed = passed and steps["command_data_publication"] == "success"
        passed = passed and steps["paper_tracking"] in {"success", "skipped"}
        passed = passed and steps["telegram_webhook"] in {"success", "skipped"}
        passed = passed and steps["telegram_delivery"] == "success"
        passed = passed and env.get("VELTRIX_TELEGRAM_CONFIGURED", "false").casefold() == "true"
        if live:
            passed = passed and steps["odds_enrichment"] in {"success", "skipped"}
            passed = passed and steps["value_certificate"] == "success"
    rows = report.get("predictions") if isinstance(report.get("predictions"), list) else []
    row_counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            key = str(row.get("status") or "UNKNOWN").upper()
            row_counts[key] = row_counts.get(key, 0) + 1
    report_summary = None
    if report:
        report_summary = {
            "as_of_date": report.get("as_of_date"),
            "publication_status": report.get("publication_status"),
            "fixtures_received": report.get("fixtures_received"),
            "same_day_pre_match_fixtures": report.get("same_day_pre_match_fixtures"),
            "future_fixtures_considered": report.get("future_fixtures_considered"),
            "fixture_rows": len(rows),
            "fixture_status_counts": row_counts,
            "fixture_visibility_validation": report.get("fixture_visibility_validation"),
            "historical_data_coverage": (report.get("historical_data_coverage") or {}).get("status"),
            "live_odds_sync": (report.get("live_odds_sync") or {}).get("status"),
            "value_intelligence": report.get("value_intelligence"),
            "value_validation_certificate": (report.get("value_validation_certificate") or {}).get("status"),
        }
        if (live or recovered) and (
            not isinstance(report.get("fixture_visibility_validation"), dict)
            or report["fixture_visibility_validation"].get("status") != "PASSED"
            or report.get("future_fixtures_considered") != len(rows)
        ):
            passed = False
        if recovered and report.get("publication_status") != "REUSED_SNAPSHOT_NOT_REFRESHED":
            passed = False
    elif live or recovered:
        passed = False
    evidence = _read_json(env.get("VELTRIX_VALUE_EVIDENCE_PATH", "reports/value_evidence_ledger.json"))
    paper = _read_json(env.get("VELTRIX_PAPER_LEDGER_PATH", "reports/paper_tracking_ledger.json"))
    return {
        "schema_version": 1,
        "workflow": env.get("GITHUB_WORKFLOW"),
        "run_id": env.get("GITHUB_RUN_ID"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "event": env.get("GITHUB_EVENT_NAME"),
        "commit_sha": env.get("GITHUB_SHA"),
        "branch": env.get("GITHUB_REF_NAME"),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": (
            "PASSED" if live else "DEGRADED_REUSED_SNAPSHOT" if recovered else "TESTS_PASSED"
        ) if passed else "NEEDS_REVIEW",
        "validation_scope": (
            "LIVE_PIPELINE" if live else "SAME_DAY_RECOVERY" if recovered else "LIVE_PIPELINE" if live_attempted else "TESTS_ONLY"
        ),
        "telegram_configured": env.get("VELTRIX_TELEGRAM_CONFIGURED", "false").casefold() == "true",
        "steps": steps,
        "report_summary": report_summary,
        "value_evidence_summary": evidence.get("summary"),
        "paper_tracking_summary": {
            "evaluated_report_dates": paper.get("evaluated_report_dates"),
            "cumulative_metrics_by_model": paper.get("cumulative_metrics_by_model"),
        } if paper else None,
        "release_status": "LOCKED_SHADOW_MODE",
        "betting_alerts_enabled": False,
    }


def merge_test_only_status(previous: dict, current: dict) -> dict:
    """Keep the last full delivery receipt when a later push only ran tests."""
    if (
        current.get("validation_scope") != "TESTS_ONLY"
        or previous.get("validation_scope") not in {"LIVE_PIPELINE", "SAME_DAY_RECOVERY"}
    ):
        return current
    merged = dict(previous)
    merged["latest_test_run"] = {
        "run_id": current.get("run_id"),
        "commit_sha": current.get("commit_sha"),
        "recorded_at_utc": current.get("recorded_at_utc"),
        "overall_status": current.get("overall_status"),
        "steps": {
            "unit_tests": current.get("steps", {}).get("unit_tests"),
            "dashboard_js": current.get("steps", {}).get("dashboard_js"),
        },
    }
    merged["latest_test_status"] = current.get("overall_status")
    merged["last_test_run_id"] = current.get("run_id")
    if current.get("overall_status") != "TESTS_PASSED":
        merged["last_full_pipeline_status"] = previous.get("overall_status")
        merged["overall_status"] = "NEEDS_REVIEW"
    return merged


def publish_status(status: dict, repo: str, token: str) -> dict:
    api = f"https://api.github.com/repos/{repo}/contents/{quote(PATH, safe='/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Veltrix-Verification-Receipt",
        "Content-Type": "application/json",
    }
    sha = None
    previous = {}
    request = Request(api + "?ref=" + quote(BRANCH, safe=""), headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            current_file = json.loads(response.read().decode("utf-8"))
            sha = current_file.get("sha")
            encoded = current_file.get("content") or ""
            if current_file.get("encoding") == "base64" and encoded:
                try:
                    previous_value = json.loads(base64.b64decode(encoded).decode("utf-8"))
                    previous = previous_value if isinstance(previous_value, dict) else {}
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    previous = {}
    except HTTPError as exc:
        if exc.code != 404:
            raise
    status = merge_test_only_status(previous, status)
    data = json.dumps(status, indent=2, ensure_ascii=False).encode("utf-8")
    body = {
        "message": f"Record VELTRIX verification run {status.get('run_id')}",
        "content": base64.b64encode(data).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    request = Request(api, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
    with urlopen(request, timeout=20) as response:
        json.loads(response.read().decode("utf-8"))
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    token = os.getenv("GITHUB_TOKEN", "")
    if not args.repo or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required.")
    status = build_status(dict(os.environ))
    published = publish_status(status, args.repo, token)
    print(json.dumps(published, indent=2))


if __name__ == "__main__":
    main()
