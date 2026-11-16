#!/usr/bin/env python3
"""One-shot, no-write 5Dollar forecast batch using the free provider account."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlencode

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.phase2_fivedollar_history_dry_run import (  # noqa: E402
    BASE,
    EXPECTED_COMPETITIONS,
    PROVIDER,
    SOURCE_ID,
    _integer,
    _parse_json,
    _request,
    _safe_headers,
    _source_approval,
    ProbeFailure,
)
from veltrix_v2.data.fivedollar import FixturePageError, parse_fixture_page  # noqa: E402
from veltrix_v2.data.fivedollar_engine import build_fivedollar_forecast_batch  # noqa: E402


REQUEST_BUDGET = 24
PACE_SECONDS = 6.0
HISTORY_DAYS = 90
UPCOMING_DAYS = 14
PER_PAGE = 100


def _report_hash(report: dict) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_forecast_probe(
    api_key: str,
    *,
    now: datetime | None = None,
    request_fn=_request,
    sleep=time.sleep,
    clock=None,
) -> dict:
    clock = clock or (lambda: datetime.now(timezone.utc))
    checked_at = (now or clock()).astimezone(timezone.utc)
    approval = _source_approval(checked_at)
    request_count = 0
    last_headers: dict[str, str] = {}
    all_fixtures = []
    selected_competitions: dict[str, str] = {}
    competition_summary: list[dict] = []
    skipped_outside_window = 0
    failure: str | None = None
    status_summary: dict = {}

    def call(path: str):
        nonlocal request_count, last_headers
        if request_count >= REQUEST_BUDGET:
            raise ProbeFailure("REQUEST_BUDGET_EXHAUSTED")
        if request_count:
            sleep(PACE_SECONDS)
        request_count += 1
        status, raw, headers = request_fn(path, api_key)
        last_headers = _safe_headers(headers)
        payload = _parse_json(raw, status)
        return payload, headers, raw, clock().astimezone(timezone.utc)

    if not isinstance(api_key, str) or not api_key.strip():
        failure = "MISSING_SECRET"
    else:
        try:
            status_payload, status_headers, status_raw, _ = call("/status")
            status_data = status_payload.get("data")
            if not isinstance(status_data, dict):
                raise ProbeFailure("STATUS_SCHEMA_INVALID")
            limits = status_data.get("limits") if isinstance(status_data.get("limits"), dict) else {}
            rate_limit = _integer(limits.get("rate_limit"))
            burst_limit = _integer(limits.get("burst_per_minute"))
            remaining = _integer(_safe_headers(status_headers).get("x-ratelimit-remaining"))
            if not rate_limit or rate_limit < 16 or not burst_limit or burst_limit < 10:
                raise ProbeFailure("ACCOUNT_QUOTA_TOO_LOW_FOR_BOUNDED_CAPTURE")
            if remaining is None or remaining < 16:
                raise ProbeFailure("INSUFFICIENT_REMAINING_QUOTA")
            status_summary = {
                "plan": str(status_data.get("plan") or "not_reported").casefold(),
                "rate_limit_hour": rate_limit,
                "burst_per_minute": burst_limit,
                "remaining_at_start": remaining,
                "status_response_sha256": hashlib.sha256(status_raw).hexdigest(),
            }

            leagues_payload, _, leagues_raw, _ = call("/leagues")
            league_rows = leagues_payload.get("data")
            if isinstance(league_rows, dict):
                league_rows = league_rows.get("leagues")
            if not isinstance(league_rows, list):
                raise ProbeFailure("LEAGUE_CATALOGUE_INVALID")
            pagination = leagues_payload.get("pagination")
            if not isinstance(pagination, dict) or pagination.get("has_more") is not False:
                raise ProbeFailure("LEAGUE_CATALOGUE_PAGINATION_INCOMPLETE")
            allowed = {
                item.strip() for item in approval.competition_scope.split(",") if item.strip()
            }
            for row in league_rows:
                if not isinstance(row, dict) or row.get("id") is None:
                    continue
                competition_id = str(row["id"])
                if competition_id in allowed:
                    selected_competitions[competition_id] = str(row.get("name") or "unknown")
            if not selected_competitions:
                raise ProbeFailure("NO_APPROVED_COMPETITIONS_AVAILABLE")
            status_summary["catalogue_sha256"] = hashlib.sha256(leagues_raw).hexdigest()
            status_summary["approved_competitions_available"] = len(selected_competitions)

            history_start = checked_at - timedelta(days=HISTORY_DAYS)
            upcoming_end = checked_at + timedelta(days=UPCOMING_DAYS)
            windows = (
                ("finished", int(history_start.timestamp()), int(checked_at.timestamp())),
                ("scheduled", int(checked_at.timestamp()), int(upcoming_end.timestamp())),
            )
            for competition_id, competition_name in sorted(selected_competitions.items()):
                per_status = {}
                for status_name, start_epoch, end_epoch in windows:
                    page = 1
                    count = 0
                    outside_count = 0
                    while True:
                        params = {
                            "status": status_name,
                            "from_time": start_epoch,
                            "to_time": end_epoch,
                            "per_page": PER_PAGE,
                            "page": page,
                        }
                        path = f"/leagues/{competition_id}/fixtures?{urlencode(params)}"
                        payload, headers, raw, retrieved_at = call(path)
                        parsed = parse_fixture_page(
                            raw, headers=headers, retrieved_at_utc=retrieved_at,
                            rights_approval_id=approval.approval_id,
                        )
                        if parsed.page != page or parsed.per_page != PER_PAGE:
                            raise ProbeFailure("FIXTURE_PAGINATION_RESPONSE_MISMATCH")
                        if any(row.provider_competition_id != competition_id for row in parsed.fixtures):
                            raise ProbeFailure("FIXTURE_COMPETITION_SCOPE_MISMATCH")
                        if any(row.status.value.casefold() != status_name for row in parsed.fixtures):
                            raise ProbeFailure("FIXTURE_STATUS_FILTER_MISMATCH")
                        in_window = [
                            row for row in parsed.fixtures
                            if start_epoch <= row.kickoff_at_utc.timestamp() <= end_epoch
                        ]
                        outside_count += len(parsed.fixtures) - len(in_window)
                        all_fixtures.extend(in_window)
                        count += len(in_window)
                        if not parsed.has_more:
                            break
                        if not parsed.fixtures:
                            raise ProbeFailure("EMPTY_PAGE_WITH_MORE_RESULTS")
                        page_times = [row.kickoff_at_utc.timestamp() for row in parsed.fixtures]
                        ascending = page_times == sorted(page_times)
                        descending = page_times == sorted(page_times, reverse=True)
                        if ascending and max(page_times) >= end_epoch:
                            break
                        if descending and min(page_times) <= start_epoch:
                            break
                        page += 1
                    skipped_outside_window += outside_count
                    per_status[status_name] = count
                    per_status[f"{status_name}_outside_window"] = outside_count
                competition_summary.append({
                    "competition_id": competition_id,
                    "competition": competition_name,
                    "finished_rows": per_status.get("finished", 0),
                    "scheduled_rows": per_status.get("scheduled", 0),
                    "outside_window_rows": per_status.get("finished_outside_window", 0) + per_status.get("scheduled_outside_window", 0),
                })

            cutoff_at = clock().astimezone(timezone.utc)
            batch = build_fivedollar_forecast_batch(
                all_fixtures, approval=approval, cutoff_at=cutoff_at, max_fixtures=25
            )
            forecasts = []
            for row in batch.prediction_report.forecasts:
                model = row.model
                wat_zone = timezone(timedelta(hours=1))
                kickoff_wat = row.kickoff_at.astimezone(wat_zone)
                forecasts.append({
                    "fixture_id": row.fixture_id,
                    "competition_id": row.competition_id,
                    "home_team": row.home_team_name,
                    "away_team": row.away_team_name,
                    "kickoff_utc": row.kickoff_at.isoformat(),
                    "kickoff_wat": kickoff_wat.isoformat(),
                    "expected_home_goals": round(model.expected_home_goals, 4),
                    "expected_away_goals": round(model.expected_away_goals, 4),
                    "probabilities": {
                        "home": round(model.home_win, 6),
                        "draw": round(model.draw, 6),
                        "away": round(model.away_win, 6),
                        "btts_yes": round(model.btts_yes, 6),
                        "over_2_5": round(model.over_2_5, 6),
                    },
                    "evidence_match_count": model.evidence_match_count,
                    "home_team_match_count": model.home_team_match_count,
                    "away_team_match_count": model.away_team_match_count,
                    "sample_floor_met": model.sample_floor_met,
                    "publishable": False,
                    "publication_reason": model.publication_reason,
                })
            report = {
                "schema_version": 1,
                "provider": PROVIDER,
                "source_id": SOURCE_ID,
                "mode": "free_first_read_only_forecast_batch",
                "generated_at_utc": cutoff_at.isoformat(),
                "cutoff_at_utc": cutoff_at.isoformat(),
                "attribution": {
                    "text": approval.attribution_text,
                    "url": approval.attribution_url,
                },
                "source_approval_id": approval.approval_id,
                "account": status_summary,
                "competition_results": competition_summary,
                "source_fixture_count": batch.source_fixture_count,
                "skipped_outside_window": skipped_outside_window,
                "history_observation_count": batch.observation_count,
                "scheduled_target_count": batch.target_count,
                "forecast_count": batch.prediction_report.forecast_count,
                "skips": {
                    "duplicate_source_fixtures": batch.skipped_duplicate_source_fixtures,
                    "rights": batch.skipped_rights,
                    "unsettled": batch.skipped_unsettled,
                    "unavailable_results": batch.skipped_unavailable_results,
                    "duplicate_targets": batch.prediction_report.skipped_duplicate_target_ids,
                    "invalid_targets": batch.prediction_report.skipped_invalid_targets,
                    "not_yet_known_targets": batch.prediction_report.skipped_targets_not_yet_known,
                    "no_history": batch.prediction_report.skipped_no_history,
                    "capacity": batch.prediction_report.skipped_capacity,
                    "outside_window": skipped_outside_window,
                },
                "request_count": request_count,
                "request_budget": REQUEST_BUDGET,
                "last_quota_headers": last_headers,
                "status": "CALCULATED_NOT_PUBLISHED" if forecasts else "NO_FORECASTS",
                "publication_locked": True,
                "forecasts": forecasts,
                "side_effects": {
                    "database_writes": 0,
                    "imports": 0,
                    "website_publications": 0,
                    "telegram_messages": 0,
                    "schedule_changes": 0,
                    "paid_requests": 0,
                },
            }
        except (ProbeFailure, FixturePageError, ValueError) as exc:
            failure = str(exc)
            cutoff_at = clock().astimezone(timezone.utc)
            report = {
                "schema_version": 1,
                "provider": PROVIDER,
                "source_id": SOURCE_ID,
                "mode": "free_first_read_only_forecast_batch",
                "generated_at_utc": cutoff_at.isoformat(),
                "cutoff_at_utc": cutoff_at.isoformat(),
                "source_approval_id": approval.approval_id,
                "account": status_summary,
                "competition_results": competition_summary,
                "source_fixture_count": len(all_fixtures),
                "skipped_outside_window": skipped_outside_window,
                "history_observation_count": 0,
                "scheduled_target_count": 0,
                "forecast_count": 0,
                "skips": {},
                "request_count": request_count,
                "request_budget": REQUEST_BUDGET,
                "last_quota_headers": last_headers,
                "status": "CAPTURE_FAILED",
                "failure_reason": failure,
                "publication_locked": True,
                "forecasts": [],
                "side_effects": {
                    "database_writes": 0,
                    "imports": 0,
                    "website_publications": 0,
                    "telegram_messages": 0,
                    "schedule_changes": 0,
                    "paid_requests": 0,
                },
            }

    if "report" not in locals():
        cutoff_at = clock().astimezone(timezone.utc)
        report = {
            "schema_version": 1,
            "provider": PROVIDER,
            "source_id": SOURCE_ID,
            "mode": "free_first_read_only_forecast_batch",
            "generated_at_utc": cutoff_at.isoformat(),
            "cutoff_at_utc": cutoff_at.isoformat(),
            "source_approval_id": approval.approval_id,
            "account": status_summary,
            "competition_results": competition_summary,
            "source_fixture_count": len(all_fixtures),
            "history_observation_count": 0,
            "scheduled_target_count": 0,
            "forecast_count": 0,
            "skips": {},
            "request_count": request_count,
            "request_budget": REQUEST_BUDGET,
            "last_quota_headers": last_headers,
            "status": "CAPTURE_FAILED",
            "failure_reason": failure,
            "publication_locked": True,
            "forecasts": [],
            "side_effects": {
                "database_writes": 0, "imports": 0, "website_publications": 0,
                "telegram_messages": 0, "schedule_changes": 0, "paid_requests": 0,
            },
        }
    report["report_sha256"] = _report_hash(report)
    return report


def validate_report(report: dict) -> None:
    if report.get("provider") != PROVIDER or report.get("mode") != "free_first_read_only_forecast_batch":
        raise ValueError("REPORT_SCOPE_INVALID")
    if report.get("request_budget") != REQUEST_BUDGET or report.get("request_count", 0) > REQUEST_BUDGET:
        raise ValueError("REPORT_REQUEST_BUDGET_INVALID")
    if report.get("publication_locked") is not True:
        raise ValueError("PUBLICATION_MUST_REMAIN_LOCKED")
    if any(item.get("publishable") is not False for item in report.get("forecasts", [])):
        raise ValueError("FORECAST_PUBLICATION_FLAG_INVALID")
    if len(report.get("forecasts", [])) > 25:
        raise ValueError("FORECAST_BATCH_EXCEEDS_25")
    if report.get("side_effects") != {
        "database_writes": 0, "imports": 0, "website_publications": 0,
        "telegram_messages": 0, "schedule_changes": 0, "paid_requests": 0,
    }:
        raise ValueError("REPORT_SIDE_EFFECTS_INVALID")
    if report.get("report_sha256") != _report_hash(report):
        raise ValueError("REPORT_SHA256_INVALID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase5/fivedollar-forecast-dry-run.json")
    args = parser.parse_args()
    report = run_forecast_probe(os.getenv("FIVEDOLLARFOOTBALL_API_KEY", ""))
    validate_report(report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "request_count": report["request_count"],
        "forecast_count": report["forecast_count"],
        "history_observation_count": report["history_observation_count"],
        "scheduled_target_count": report["scheduled_target_count"],
        "report_sha256": report["report_sha256"],
        "failure_reason": report.get("failure_reason"),
    }, sort_keys=True))
    return 0 if report["status"] != "CAPTURE_FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
