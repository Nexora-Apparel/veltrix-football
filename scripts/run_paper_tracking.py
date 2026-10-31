"""Evaluate the prior day's saved report and maintain a cumulative paper ledger."""
# Paper tracking reads published reports and cached completed results; it never calls the football provider.
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

from app.paper_tracking import evaluate_report, merge_paper_ledger

API_ROOT = "https://api.github.com"


def load_cached_results_payload(repo: str) -> tuple[dict[str, Any], str]:
    """Load completed fixture scores from the persisted cache without calling the football provider."""
    branch = os.getenv("VELTRIX_DATA_BRANCH", "command-data").strip()
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/public-data/recent_results_cache.json"
    try:
        response = requests.get(url, headers={"User-Agent": "VeltrixFootball-PaperTracking"}, timeout=20)
        response.raise_for_status()
        if len(response.content) > 4_000_000:
            return {"response": []}, "CACHE_TOO_LARGE"
        cache = response.json()
    except (requests.RequestException, OSError, ValueError):
        return {"response": []}, "CACHE_UNAVAILABLE"
    if (
        not isinstance(cache, dict)
        or cache.get("version") not in (1, 2)
        or not isinstance(cache.get("matches"), list)
    ):
        return {"response": []}, "CACHE_INVALID"

    completed = []
    for row in cache["matches"]:
        if not isinstance(row, dict):
            continue
        fixture_id = row.get("fixture_id")
        status = str(row.get("fixture_status") or "FT").upper()
        home_goals, away_goals = row.get("home_goals"), row.get("away_goals")
        if (
            not isinstance(fixture_id, int) or isinstance(fixture_id, bool)
            or status not in {"FT", "AET", "PEN"}
            or not isinstance(home_goals, int) or isinstance(home_goals, bool) or home_goals < 0
            or not isinstance(away_goals, int) or isinstance(away_goals, bool) or away_goals < 0
        ):
            continue
        completed.append({
            "fixture": {
                "id": fixture_id,
                "date": str(row.get("date") or ""),
                "status": {"short": status},
            },
            "teams": {
                "home": {"name": str(row.get("home") or "")},
                "away": {"name": str(row.get("away") or "")},
            },
            "goals": {"home": home_goals, "away": away_goals},
        })
    return {"response": completed}, "CACHE_AVAILABLE"


def github_get(session: requests.Session, url: str) -> dict[str, Any]:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API returned an unexpected response.")
    return payload


def list_relevant_runs(session: requests.Session, repo: str) -> list[dict[str, Any]]:
    # Query report-producing runs separately so frequent push-triggered tests
    # cannot crowd scheduled/manual report runs out of GitHub's first page.
    # Include the isolated recovery workflow because its ledger artifact is
    # authoritative for subsequent daily paper-tracking runs.
    runs_by_id: dict[int, dict[str, Any]] = {}
    queries = (
        ("daily-fixture-predictions.yml", ("schedule", "workflow_dispatch")),
        ("paper-tracking-recovery.yml", ("push", "schedule", "workflow_dispatch")),
    )
    for workflow, events in queries:
        for event in events:
            url = (
                f"{API_ROOT}/repos/{repo}/actions/workflows/{workflow}/runs"
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


def _report_forecast_count(report: dict[str, Any]) -> int:
    predictions = report.get("predictions")
    if not isinstance(predictions, list):
        return 0
    return sum(
        1 for row in predictions
        if isinstance(row, dict)
        and (
            (isinstance(row.get("fixture_id"), int) and not isinstance(row.get("fixture_id"), bool))
            or (isinstance(row.get("fixture_id"), str) and bool(row.get("fixture_id").strip())
                and row.get("fixture_id").strip().casefold() not in {"none", "null"})
        )
        and (
            (
                row.get("status") == "EXPERIMENTAL_ONLY"
                and isinstance(row.get("probabilities"), dict)
            )
            or isinstance(row.get("market_probabilities"), dict)
        )
    )


def find_daily_report(
    session: requests.Session, repo: str, runs: list[dict[str, Any]], report_date: str, current_run_id: str
) -> dict[str, Any] | None:
    """Choose the same-day snapshot with the most scoreable forecasts.

    Multiple manual/scheduled runs can create reports on one date. Choosing the
    newest artifact can accidentally select a late report after most fixtures
    have kicked off, leaving paper tracking with zero forecasts. Prefer the
    richest valid report; break ties by the earliest report timestamp.
    """
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for run in runs:
        created_at = str(run.get("created_at", ""))
        if str(run.get("id")) == current_run_id or created_at[:10] != report_date:
            continue
        artifact = artifact_for_run(session, repo, int(run["id"]), "veltrix-daily-predictions")
        if not artifact:
            continue
        report = read_artifact_json(session, artifact["archive_download_url"])
        if report.get("as_of_date") != report_date:
            continue
        timestamp = str(report.get("generated_at_utc") or created_at)
        candidates.append((_report_forecast_count(report), timestamp, report))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _has_trackable_forecasts(report: dict[str, Any]) -> bool:
    """Avoid burning provider quota when a saved report contains no scoreable rows."""
    return _report_forecast_count(report) > 0


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
            cached_results, cache_status = load_cached_results_payload(repo)
            evaluations = ledger.get("evaluations", [])
            evaluation_by_date = {
                str(item.get("report_date")): item for item in evaluations
                if item.get("report_date")
            }
            pending_dates = sorted({
                date.fromisoformat(day)
                for day, item in evaluation_by_date.items()
                if (
                    int(item.get("awaiting_result_or_match", 0)) > 0
                    or item.get("tracking_state") == "NO_FORECASTS_TO_SCORE"
                    or (
                        int(item.get("completed_forecasts_scored", 0)) == 0
                        and not item.get("model_versions")
                        and not item.get("tracking_state")
                        and int(item.get("withheld_or_invalid_forecasts", 0)) == 0
                    )
                )
                and day != report_date.isoformat()
                and 0 <= (report_date - date.fromisoformat(day)).days <= 85
            })[:3]
            dates_to_process = [day for day in pending_dates]
            target_summary = evaluation_by_date.get(report_date.isoformat())
            if (
                target_summary is None
                or int(target_summary.get("awaiting_result_or_match", 0)) > 0
                or (
                    int(target_summary.get("completed_forecasts_scored", 0)) == 0
                    and not target_summary.get("model_versions")
                    and not target_summary.get("tracking_state")
                    and int(target_summary.get("withheld_or_invalid_forecasts", 0)) == 0
                )
            ):
                dates_to_process.append(report_date)

            if not dates_to_process:
                attempts.append({
                    "report_date": report_date.isoformat(),
                    "status": "ALREADY_EVALUATED",
                    "detail": "No pending report dates; this date is already complete.",
                })
            else:
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
                        elif not _has_trackable_forecasts(report):
                            one.update({
                                "status": "NO_FORECASTS_TO_SCORE",
                                "detail": "The best saved report for this date contains no scoreable forecasts; provider quota was preserved.",
                            })
                            evaluations = ledger.setdefault("evaluations", [])
                            empty_summary = {
                                "report_date": date_text,
                                "fixtures_scored": 0,
                                "completed_forecasts_scored": 0,
                                "awaiting_result_or_match": 0,
                                "withheld_or_invalid_forecasts": 0,
                                "metrics": {"matches": 0, "result_accuracy": None, "brier_score": None, "log_loss": None},
                                "metrics_by_model": {},
                                "model_versions": [],
                                "tracking_state": "NO_FORECASTS_TO_SCORE",
                            }
                            existing = next(
                                (item for item in evaluations if str(item.get("report_date")) == date_text),
                                None,
                            )
                            if existing is None:
                                evaluations.append(empty_summary)
                            elif (
                                int(existing.get("completed_forecasts_scored", 0)) == 0
                                and not existing.get("model_versions")
                                and int(existing.get("withheld_or_invalid_forecasts", 0)) == 0
                            ):
                                existing.update(empty_summary)
                            ledger["evaluated_report_dates"] = len(evaluations)
                        else:
                            try:
                                # Use only persisted completed results. Live provider calls here
                                # duplicated the full fixture pagination and exhausted daily quota.
                                evaluation = evaluate_report(report, cached_results)
                                ledger = merge_paper_ledger(ledger, evaluation)
                                cache_detail = (
                                    f"Scored from {len(cached_results['response'])} cached completed matches; "
                                    "no live football-provider request was made."
                                    if cache_status == "CACHE_AVAILABLE"
                                    else "Recent-results cache unavailable; no live football-provider request was made."
                                )
                                one.update({
                                    "status": "EVALUATED",
                                    "detail": cache_detail,
                                    "fixtures_scored": evaluation.get("fixtures_scored", 0),
                                    "completed_forecasts_scored": evaluation["completed_forecasts_scored"],
                                    "metrics": evaluation["metrics"],
                                    "metrics_by_model": evaluation.get("metrics_by_model", {}),
                                    "awaiting_result_or_match": evaluation.get("awaiting_result_or_match", 0),
                                })
                            except (RuntimeError, ValueError) as exc:
                                one.update({"status": "TRACKING_ERROR", "detail": str(exc)})
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
        # A provider failure must never be published as a healthy paper ledger.
        # The workflow validator uses TRACKING_ERROR to preserve the last known-good ledger.
        top_status = "TRACKING_ERROR"
    elif "API_KEY_MISSING" in statuses:
        top_status = "API_KEY_MISSING"
    elif "NO_PREVIOUS_REPORT" in statuses:
        top_status = "NO_PREVIOUS_REPORT"
    elif "NO_FORECASTS_TO_SCORE" in statuses:
        top_status = "NO_FORECASTS_TO_SCORE"
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
