#!/usr/bin/env python3
"""Bounded read-only rolling-window coverage probe for all 17 StrikerAPI competitions."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_strikerapi import ProbeError, call_api, validate_game

COMPETITIONS = (
    ("soccer", "English Premier League"),
    ("mls", "Major League Soccer"),
    ("laliga", "Spanish La Liga"),
    ("seriea", "Italian Serie A"),
    ("bundesliga", "German Bundesliga"),
    ("ligue1", "French Ligue 1"),
    ("ucl", "UEFA Champions League"),
    ("championship", "EFL Championship"),
    ("nwsl", "NWSL"),
    ("ligamx", "Mexican Liga MX"),
    ("uel", "UEFA Europa League"),
    ("uecl", "UEFA Conference League"),
    ("eredivisie", "Dutch Eredivisie"),
    ("primeira", "Portuguese Primeira Liga"),
    ("scotland", "Scottish Premiership"),
    ("brazil", "Brazil Serie A"),
    ("argentina", "Argentina Liga Profesional"),
)
STATUSES = ("final", "scheduled")
LIMIT = 50
MAX_PAGES_PER_CHECK = 3
MAX_CALLS = len(COMPETITIONS) * len(STATUSES) * MAX_PAGES_PER_CHECK
FINAL_WINDOW_DAYS = 90
SCHEDULE_WINDOW_DAYS = 60


def collect_bounded(api_key, league, status, start, end, call, budget, pause_seconds=0.0, sleep=time.sleep, max_429_retries=2):
    rows, page_counts = [], []
    offset, pages = 0, 0
    truncated = False
    while pages < MAX_PAGES_PER_CHECK:
        if budget["calls"] >= MAX_CALLS:
            raise ProbeError("global 17-competition request budget exhausted")
        if budget["calls"] and pause_seconds:
            sleep(pause_seconds)
        budget["calls"] += 1
        retries = 0
        while True:
            try:
                data = call(api_key, league, status, start, end, offset)
                break
            except ProbeError as exc:
                if "HTTP 429" not in str(exc) or retries >= max_429_retries:
                    raise
                retries += 1
                if budget["calls"] >= MAX_CALLS:
                    raise ProbeError("global request budget exhausted during 429 retry")
                sleep(65.0)
                budget["calls"] += 1
        games = data.get("games")
        if not isinstance(games, list):
            raise ProbeError("expected games array")
        rows.extend(games)
        page_counts.append(data.get("count"))
        pages += 1
        next_offset = data.get("next_offset")
        if next_offset is None:
            return rows, pages, False, page_counts
        if isinstance(next_offset, bool) or not isinstance(next_offset, int) or next_offset <= offset:
            raise ProbeError("next_offset is invalid or did not advance")
        if not games:
            raise ProbeError("empty page reported a continuation offset")
        offset = next_offset
    truncated = True
    return rows, pages, truncated, page_counts


def qualify(api_key: str, now: datetime, call=call_api, pause_seconds=0.0, sleep=time.sleep) -> dict:
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    today = now.date()
    final_start = (today - timedelta(days=FINAL_WINDOW_DAYS)).isoformat()
    schedule_end = (today + timedelta(days=SCHEDULE_WINDOW_DAYS)).isoformat()
    today_text = today.isoformat()
    budget = {"calls": 0}
    seen: set[tuple[str, str]] = set()
    summaries = []
    total_rows = total_valid = total_invalid = total_duplicates = 0

    for league, competition in COMPETITIONS:
        for status in STATUSES:
            start, end = (
                (final_start, today_text)
                if status == "final"
                else (today_text, schedule_end)
            )
            rows, pages, truncated, page_counts = collect_bounded(
                api_key, league, status, start, end, call, budget,
                pause_seconds=pause_seconds, sleep=sleep,
            )
            valid = invalid = duplicates = 0
            for row in rows:
                ok, _reason = validate_game(row, status)
                if not ok:
                    invalid += 1
                    continue
                valid += 1
                identity = (league, str(row["game_id"]))
                if identity in seen:
                    duplicates += 1
                else:
                    seen.add(identity)
            total_rows += len(rows)
            total_valid += valid
            total_invalid += invalid
            total_duplicates += duplicates
            summaries.append({
                "league_key": league,
                "competition": competition,
                "status": status,
                "window_start": start,
                "window_end_inclusive": end,
                "rows": len(rows),
                "valid": valid,
                "invalid": invalid,
                "duplicate_ids": duplicates,
                "pages": pages,
                "pagination_truncated": truncated,
                "page_count_fields": page_counts,
                "empty_result": len(rows) == 0,
            })

    truncated_checks = [
        f"{x['league_key']}:{x['status']}" for x in summaries
        if x["pagination_truncated"]
    ]
    empty_final = [x["league_key"] for x in summaries if x["status"] == "final" and x["empty_result"]]
    empty_scheduled = [x["league_key"] for x in summaries if x["status"] == "scheduled" and x["empty_result"]]
    result = {
        "schema_version": 1,
        "mode": "read_only_17_competition_rolling_coverage",
        "provider": "StrikerAPI",
        "retrieved_at": now.isoformat(),
        "windows": {
            "final_days": FINAL_WINDOW_DAYS,
            "scheduled_days": SCHEDULE_WINDOW_DAYS,
            "final_start": final_start,
            "scheduled_end": schedule_end,
        },
        "competition_count": len(COMPETITIONS),
        "check_count": len(summaries),
        "request_budget": {
            "maximum_calls": MAX_CALLS,
            "actual_calls": budget["calls"],
            "documented_credits_per_call": 2,
            "maximum_credits": MAX_CALLS * 2,
            "actual_documented_credits": budget["calls"] * 2,
            "max_pages_per_check": MAX_PAGES_PER_CHECK,
            "page_size": LIMIT,
        },
        "totals": {
            "rows": total_rows,
            "valid": total_valid,
            "invalid": total_invalid,
            "duplicate_ids": total_duplicates,
        },
        "empty_final_competitions": empty_final,
        "empty_scheduled_competitions": empty_scheduled,
        "truncated_checks": truncated_checks,
        "database_writes": 0,
        "imports": 0,
        "checkpoints": 0,
        "canonical_merges": 0,
        "acceptance_pass": (
            total_rows > 0 and total_invalid == 0 and total_duplicates == 0
            and not truncated_checks
        ),
        "checks": summaries,
    }
    return result


def main() -> int:
    key = os.getenv("STRIKERAPI_API_KEY", "").strip()
    if not key:
        print("STRIKERAPI_17_LEAGUE_RESULT: BLOCKED_MISSING_SECRET")
        return 2
    now = datetime.now(timezone.utc)
    try:
        report = qualify(key, now, pause_seconds=7.0)
    except ProbeError as exc:
        print(f"STRIKERAPI_17_LEAGUE_FAILED: {str(exc)[:160]}")
        print("DATABASE_WRITES: 0; IMPORTS: 0; CHECKPOINTS: 0; CANONICAL_MERGES: 0")
        return 1
    output = Path("strikerapi_17_competition_coverage.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for row in report["checks"]:
        print(
            f"STRIKERAPI_17_CHECK: league={row['league_key']}; status={row['status']}; "
            f"rows={row['rows']}; valid={row['valid']}; invalid={row['invalid']}; "
            f"duplicates={row['duplicate_ids']}; pages={row['pages']}; "
            f"truncated={str(row['pagination_truncated']).lower()}"
        )
    print(f"STRIKERAPI_17_SUMMARY: {json.dumps(report['totals'], sort_keys=True)}")
    print(f"STRIKERAPI_17_CALLS: {report['request_budget']['actual_calls']}; credits={report['request_budget']['actual_documented_credits']}; max_credits={report['request_budget']['maximum_credits']}")
    print(f"STRIKERAPI_17_EMPTY_FINAL: {json.dumps(empty_final := report['empty_final_competitions'])}")
    print(f"STRIKERAPI_17_EMPTY_SCHEDULED: {json.dumps(report['empty_scheduled_competitions'])}")
    print(f"STRIKERAPI_17_TRUNCATED: {json.dumps(report['truncated_checks'])}")
    print(f"STRIKERAPI_17_ACCEPTANCE: {'PASS' if report['acceptance_pass'] else 'FAIL_REVIEW_REQUIRED'}")
    print(f"STRIKERAPI_17_REPORT: {output.name}")
    print("DATABASE_WRITES: 0; IMPORTS: 0; CHECKPOINTS: 0; CANONICAL_MERGES: 0")
    return 0 if report["acceptance_pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
