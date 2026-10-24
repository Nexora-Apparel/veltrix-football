"""Evaluate the prior day's saved report and maintain a cumulative paper ledger."""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError
from app.paper_tracking import evaluate_report, merge_paper_ledger

API_ROOT = "https://api.github.com"


def github_get(session: requests.Session, url: str) -> dict[str, Any]:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API returned an unexpected response.")
    return payload


def list_relevant_runs(session: requests.Session, repo: str) -> list[dict[str, Any]]:
    # Query these event types separately so frequent push-triggered test runs
    # cannot crowd scheduled/manual report runs out of GitHub's first page.
    runs_by_id: dict[int, dict[str, Any]] = {}
    for event in ("schedule", "workflow_dispatch"):
        url = (
            f"{API_ROOT}/repos/{repo}/actions/workflows/daily-fixture-predictions.yml/runs"
            f"?event={event}&per_page=100&status=completed"
        )
        payload = github_get(session, url)
        for run in payload.get("workflow_runs", []):
            if isinstance(run.get("id"), int):
                runs_by_id[run["id"]] = run
    return sorted(
        runs_by_id.values(),
        key=lambda run: run.get("created_at", ""),
        reverse=True,
    )


def artifact_for_run(session: requests.Session, repo: str, run_id: int, artifact_name: str) -> dict[str, Any] | None:
    url = f"{API_ROOT}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100"
    payload = github_get(session, url)
    return next(
        (item for item in payload.get("artifacts", [])
         if item.get("name") == artifact_name and not item.get("expired")),
        None,
    )


def read_artifact_json(session: requests.Session, artifact_url: str) -> dict[str, Any]:
    response = session.get(artifact_url, timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith(".json")]
        if not candidates:
            raise RuntimeError("GitHub artifact contains no JSON file.")
        # These artifacts each contain one report/ledger JSON document.
        value = json.loads(archive.read(candidates[0]).decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Downloaded artifact JSON has an unexpected shape.")
    return value


def find_daily_report(
    session: requests.Session, repo: str, runs: list[dict[str, Any]], report_date: str, current_run_id: str
) -> dict[str, Any] | None:
    for run in runs:
        if str(run.get("id")) == current_run_id or str(run.get("created_at", ""))[:10] != report_date:
            continue
        artifact = artifact_for_run(session, repo, int(run["id"]), "veltrix-daily-predictions")
        if artifact:
            report = read_artifact_json(session, artifact["archive_download_url"])
            if report.get("as_of_date") == report_date:
                return report
    return None


def find_latest_ledger(
    session: requests.Session, repo: str, runs: list[dict[str, Any]], current_run_id: str
) -> dict[str, Any]:
    # Ledger artifacts are retained for 90 days; search at least 100 relevant
    # runs so daily scheduled executions cannot reset the ledger before expiry.
    # Stop at the first ledger found, keeping API calls bounded.
    for run in runs[:100]:
        if str(run.get("id")) == current_run_id:
            continue
        artifact = artifact_for_run(session, repo, int(run["id"]), "veltrix-paper-ledger")
        if artifact:
            return read_artifact_json(session, artifact["archive_download_url"])
    return {
        "product": "Veltrix Football",
        "model_status": "PAPER_TRACKING_ONLY",
        "evaluations": [],
        "scored_matches": [],
    }


def run(report_date: date, output_path: str) -> dict[str, Any]:
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GITHUB_TOKEN", "")
    current_run_id = os.getenv("GITHUB_RUN_ID", "")
    ledger: dict[str, Any] = {
        "product": "Veltrix Football",
        "model_status": "PAPER_TRACKING_ONLY",
        "evaluations": [],
        "scored_matches": [],
    }
    attempts: list[dict[str, Any]] = []

    try:
        if not repo or not token:
            raise RuntimeError("GITHUB_REPOSITORY or GITHUB_TOKEN is unavailable.")
        with requests.Session() as session:
            session.headers.update({
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "VeltrixFootball/0.1",
            })
            runs = list_relevant_runs(session, repo)
            ledger = find_latest_ledger(session, repo, runs, current_run_id)
            evaluations = ledger.get("evaluations", [])
            evaluation_by_date = {
                str(item.get("report_date")): item for item in evaluations
                if item.get("report_date")
            }
            pending_dates = sorted({
                date.fromisoformat(day)
                for day, item in evaluation_by_date.items()
                if int(item.get("awaiting_result_or_match", 0)) > 0
                and day != report_date.isoformat()
                and 0 <= (report_date - date.fromisoformat(day)).days <= 85
            })[:3]
            dates_to_process = [day for day in pending_dates]
            target_summary = evaluation_by_date.get(report_date.isoformat())
            if (
                target_summary is None
                or int(target_summary.get("awaiting_result_or_match", 0)) > 0
            ):
                dates_to_process.append(report_date)

            if not dates_to_process:
                attempts.append({
                    "report_date": report_date.isoformat(),
                    "status": "ALREADY_EVALUATED",
                    "detail": "No pending report dates; this date is already complete.",
                })
            else:
                api_client = None
                for date_to_process in dates_to_process:
                    date_text = date_to_process.isoformat()
                    one: dict[str, Any] = {
                        "report_date": date_text,
                        "status": "NOT_EVALUATED",
                        "detail": None,
                    }
                    try:
                        report = find_daily_report(
                            session, repo, runs, date_text, current_run_id
                        )
                        if report is None:
                            one.update({
                                "status": "NO_PREVIOUS_REPORT",
                                "detail": "No saved daily report was found for this date.",
                            })
                        elif not os.getenv("API_FOOTBALL_KEY"):
                            one.update({
                                "status": "API_KEY_MISSING",
                                "detail": "Cannot fetch completed results without API_FOOTBALL_KEY.",
                            })
                        else:
                            try:
                                if api_client is None:
                                    api_client = FootballAPI(get_settings())
                                results = api_client.fixtures(date_text, "Africa/Lagos")
                                evaluation = evaluate_report(report, results)
                                ledger = merge_paper_ledger(ledger, evaluation)
                                one.update({
                                    "status": "EVALUATED",
                                    "fixtures_scored": evaluation.get("fixtures_scored", 0),
                                    "completed_forecasts_scored": evaluation["completed_forecasts_scored"],
                                    "metrics": evaluation["metrics"],
                                    "metrics_by_model": evaluation.get("metrics_by_model", {}),
                                    "awaiting_result_or_match": evaluation.get("awaiting_result_or_match", 0),
                                })
                            except (FootballAPIError, RuntimeError, ValueError) as exc:
                                one.update({"status": "RESULT_FETCH_FAILED", "detail": str(exc)})
                    except (requests.RequestException, RuntimeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
                        one.update({"status": "TRACKING_ERROR", "detail": str(exc)})
                    attempts.append(one)
    except (requests.RequestException, RuntimeError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        # Paper tracking must never prevent the current day's predictions from running.
        attempts.append({
            "report_date": report_date.isoformat(),
            "status": "TRACKING_ERROR",
            "detail": str(exc),
        })

    statuses = {item["status"] for item in attempts}
    if "EVALUATED" in statuses:
        top_status = "EVALUATED"
    elif "TRACKING_ERROR" in statuses:
        top_status = "TRACKING_ERROR"
    elif "RESULT_FETCH_FAILED" in statuses:
        top_status = "RESULT_FETCH_FAILED"
    elif "API_KEY_MISSING" in statuses:
        top_status = "API_KEY_MISSING"
    elif "NO_PREVIOUS_REPORT" in statuses:
        top_status = "NO_PREVIOUS_REPORT"
    elif "ALREADY_EVALUATED" in statuses:
        top_status = "ALREADY_EVALUATED"
    else:
        top_status = "NOT_EVALUATED"

    ledger["product"] = "Veltrix Football"
    ledger["model_status"] = "PAPER_TRACKING_ONLY"
    ledger["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    ledger["last_attempt"] = {
        "report_date": report_date.isoformat(),
        "status": top_status,
        "attempts": attempts,
        "detail": None,
        "metrics_by_model": ledger.get("cumulative_metrics_by_model", {}),
    }
    ledger.setdefault("evaluations", [])
    ledger.setdefault("scored_matches", [])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Nigeria-local date of the saved report to evaluate (YYYY-MM-DD)")
    parser.add_argument("--output", default="reports/paper_tracking_ledger.json")
    args = parser.parse_args()
    try:
        report_date = date.fromisoformat(args.date)
        ledger = run(report_date, args.output)
        print(json.dumps({
            "report_date": report_date.isoformat(),
            "last_attempt": ledger["last_attempt"],
            "evaluated_report_dates": len(ledger.get("evaluations", [])),
            "model_versions": ledger.get("model_versions", []),
            "cumulative_metrics": ledger.get("cumulative_metrics", {}),
            "cumulative_metrics_by_model": ledger.get("cumulative_metrics_by_model", {}),
            "output": args.output,
        }, indent=2))
    except (ValueError, OSError) as exc:
        print(f"PAPER TRACKING FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
