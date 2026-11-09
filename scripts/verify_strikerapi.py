"""Bounded, read-only StrikerAPI coverage qualification for VELTRIX FOOTBALL.

Eight competition/status checks, at most six pages each, with a 48-call hard
cap (96 documented credits). No database access, imports, artifact uploads or secrets
in logs. This is a coverage probe, not a complete historical export.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://mcp.strikerapi.com/v1/list_games"
TIMEOUT = 25
LIMIT = 50
MAX_PAGES_PER_CHECK = 6
MAX_CALLS = 48
WINDOW_DAYS = 90
FUTURE_DAYS = 180
# StrikerAPI documents "soccer" as the Premier League default/key.
CHECKS = (
    ("argentina", "final", "Argentina Liga Profesional"),
    ("argentina", "scheduled", "Argentina Liga Profesional"),
    ("brazil", "final", "Brazil Serie A"),
    ("brazil", "scheduled", "Brazil Serie A"),
    ("nwsl", "final", "NWSL"),
    ("nwsl", "scheduled", "NWSL"),
    ("soccer", "final", "English Premier League"),
    ("soccer", "scheduled", "English Premier League"),
)


class ProbeError(RuntimeError):
    pass


def safe_text(value: object, max_len: int = 180) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return "not reported"
    return re.sub(r"[^A-Za-z0-9 _./:+-]", "", str(value))[:max_len] or "not reported"


def call_api(
    api_key: str, league: str, status: str, start: str | None, end: str | None,
    offset: int = 0, season: int | None = None, stage: str | None = None
) -> dict:
    body = {"league": league, "status": status, "limit": LIMIT, "offset": offset}
    if start is not None:
        body["from"] = start
    if end is not None:
        body["to"] = end
    if season is not None:
        body["season"] = season
    if stage is not None:
        body["stage"] = stage
    request = Request(
        BASE,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": "VELTRIX-FOOTBALL-read-only-qualification/1.1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ProbeError("response is not a JSON object")
            data = payload.get("data", payload)
            if not isinstance(data, dict):
                raise ProbeError("response data is not an object")
            return data
    except HTTPError as exc:
        raise ProbeError(f"HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("invalid JSON response") from None


def collect_pages(
    api_key: str,
    league: str,
    status: str,
    start: str,
    end: str,
    call: Callable[..., dict] = call_api,
    extra_params: dict | None = None,
) -> tuple[list, int, bool, list]:
    """Collect at most MAX_PAGES_PER_CHECK pages; reject broken pagination."""
    rows: list = []
    page_count = 0
    offset = 0
    page_counts: list = []
    while page_count < MAX_PAGES_PER_CHECK:
        if extra_params:
            data = call(api_key, league, status, start, end, offset, **extra_params)
        else:
            data = call(api_key, league, status, start, end, offset)
        games = data.get("games")
        if not isinstance(games, list):
            raise ProbeError("expected games array")
        rows.extend(games)
        page_count += 1
        page_counts.append(data.get("count"))
        next_offset = data.get("next_offset")
        if next_offset is None:
            return rows, page_count, False, page_counts
        if isinstance(next_offset, bool) or not isinstance(next_offset, int):
            raise ProbeError("next_offset is not an integer")
        if next_offset <= offset:
            raise ProbeError("next_offset did not advance")
        if not games:
            raise ProbeError("empty page reported a continuation offset")
        offset = next_offset
    # A continuation token after the final allowed page means this window is
    # deliberately incomplete; it must never be reported as fully paginated.
    return rows, page_count, True, page_counts


def validate_game(row: object, expected_status: str) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "not_object"
    required = ("game_id", "date", "starts_at", "status", "home", "away")
    if any(row.get(field) in (None, "") for field in required):
        return False, "missing_identity_or_schedule_fields"
    if row.get("status") != expected_status:
        return False, "status_mismatch"
    try:
        datetime.fromisoformat(str(row["date"]))
        timestamp = datetime.fromisoformat(str(row["starts_at"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return False, "timezone_missing_from_kickoff_timestamp"
    except ValueError:
        return False, "invalid_date_or_timestamp"
    for side in ("home", "away"):
        team = row.get(side)
        if not isinstance(team, dict) or not team.get("team_id") or not team.get("name"):
            return False, f"missing_{side}_team_identity"
    if expected_status == "final":
        for side in ("home", "away"):
            score = row[side].get("score")
            if not isinstance(score, int) or isinstance(score, bool) or score < 0:
                return False, "invalid_final_score"
    return True, "valid"


def main() -> int:
    key = os.getenv("STRIKERAPI_API_KEY", "").strip()
    if not key:
        print("STRIKERAPI_RESULT: BLOCKED_MISSING_SECRET (STRIKERAPI_API_KEY)")
        return 2

    today = datetime.now(timezone.utc).date()
    historical_start = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    future_end = (today + timedelta(days=FUTURE_DAYS)).isoformat()
    today_text = today.isoformat()
    max_credits = MAX_CALLS * 2
    print(
        f"PROBE_WINDOWS: final={historical_start}..{today_text}; "
        f"scheduled={today_text}..{future_end}"
    )
    print(
        f"REQUEST_BUDGET: maximum_calls={MAX_CALLS}; "
        f"documented_credits_per_call=2; maximum_credits={max_credits}; "
        f"page_limit={LIMIT}; max_pages_per_check={MAX_PAGES_PER_CHECK}"
    )
    print("NOTE: Bounded 90-day history / 180-day schedule coverage probe; not a full-season export.")
    print("COMPETITION_MAP: soccer=English Premier League; nwsl=NWSL; brazil=Brazil Serie A; argentina=Argentina Liga Profesional")

    seen: dict[tuple[str, str], tuple[str, str]] = {}
    total_rows = total_valid = total_invalid = total_duplicates = 0
    attempted_calls = 0
    truncated_checks = []
    empty_scheduled = []
    summaries = []

    for league, status, competition in CHECKS:
        start, end = (
            (historical_start, today_text)
            if status == "final"
            else (today_text, future_end)
        )
        remaining = MAX_CALLS - attempted_calls
        if remaining <= 0:
            print("STRIKERAPI_CHECK_FAILED: hard request budget exhausted")
            return 1

        def bounded_call(api_key, selected_league, selected_status, from_date, to_date, offset, **extra_params):
            nonlocal attempted_calls
            if attempted_calls >= MAX_CALLS:
                raise ProbeError("hard request budget exhausted")
            attempted_calls += 1
            return call_api(
                api_key, selected_league, selected_status, from_date, to_date, offset,
                **extra_params
            )

        try:
            games, pages, truncated, page_counts = collect_pages(
                key, league, status, start, end, bounded_call
            )
        except ProbeError as exc:
            print(
                f"STRIKERAPI_CHECK_FAILED: competition={competition}; "
                f"status={status}; reason={safe_text(str(exc))}"
            )
            print(f"API_CALLS_ATTEMPTED: {attempted_calls}; DATABASE_WRITES: 0; IMPORTS: 0")
            return 1

        valid = invalid = duplicates = 0
        for row in games:
            total_rows += 1
            ok, reason = validate_game(row, status)
            if not ok:
                invalid += 1
                total_invalid += 1
                continue
            valid += 1
            total_valid += 1
            game_id = str(row["game_id"])
            identity = (league, game_id)
            if identity in seen:
                duplicates += 1
                total_duplicates += 1
            else:
                seen[identity] = (status, str(row["date"]))

        if truncated:
            truncated_checks.append(f"{league}:{status}")
        if status == "scheduled" and not games:
            empty_scheduled.append(competition)

        summaries.append({
            "competition": competition,
            "status": status,
            "rows": len(games),
            "valid": valid,
            "invalid": invalid,
            "duplicates": duplicates,
            "pages": pages,
            "truncated": truncated,
            "page_count_fields": page_counts,
        })
        print(
            f"STRIKERAPI_CHECK: competition={competition}; status={status}; "
            f"rows={len(games)}; valid={valid}; invalid={invalid}; "
            f"duplicate_ids={duplicates}; pages={pages}; "
            f"pagination_truncated={str(truncated).lower()}; "
            f"page_count_fields={json.dumps(page_counts)}"
        )

    # NWSL uses calendar-year seasons. Diagnose the empty rolling-window
    # schedule by checking 2026 completed games and the next season's schedule,
    # separately for league and knockout stages.
    nwsl_diagnostic_invalid = False
    nwsl_diagnostics = (
        (2026, "final", "league"),
        (2026, "final", "knockout"),
        (2027, "scheduled", "league"),
        (2027, "scheduled", "knockout"),
    )
    for season, status, stage in nwsl_diagnostics:
        try:
            games, pages, truncated, page_counts = collect_pages(
                key, "nwsl", status, None, None, bounded_call,
                extra_params={"season": season, "stage": stage},
            )
        except ProbeError as exc:
            print(
                f"NWSL_SEASON_DIAGNOSTIC_FAILED: season={season}; "
                f"status={status}; stage={stage}; reason={safe_text(str(exc))}"
            )
            print(
                f"API_CALLS_ATTEMPTED: {attempted_calls}; "
                "DATABASE_WRITES: 0; IMPORTS: 0"
            )
            return 1
        valid = invalid = 0
        for row in games:
            ok, _reason = validate_game(row, status)
            if ok:
                valid += 1
            else:
                invalid += 1
        print(
            f"NWSL_SEASON_DIAGNOSTIC: season={season}; status={status}; "
            f"stage={stage}; rows={len(games)}; valid={valid}; invalid={invalid}; "
            f"pages={pages}; pagination_truncated={str(truncated).lower()}; "
            f"page_count_fields={json.dumps(page_counts)}"
        )
        if truncated:
            truncated_checks.append(f"nwsl:season={season}:stage={stage}:{status}")
        if invalid:
            nwsl_diagnostic_invalid = True

    print(
        f"NWSL_SEASON_DIAGNOSTIC_CHECKS: {len(nwsl_diagnostics)}; "
        f"invalid_rows_present={str(nwsl_diagnostic_invalid).lower()}"
    )
    print(
        "STRIKERAPI_SUMMARY: "
        f"calls={attempted_calls}; documented_credit_cost={attempted_calls * 2}; "
        f"rows={total_rows}; valid={total_valid}; invalid={total_invalid}; "
        f"duplicate_ids={total_duplicates}; "
        f"truncated_checks={json.dumps(truncated_checks)}; "
        f"empty_scheduled_checks={json.dumps(empty_scheduled)}"
    )
    print("DATABASE_WRITES: 0; IMPORTED_RECORDS: 0; IMPORT_RUNS: 0; CHECKPOINTS: 0")

    if total_invalid or total_duplicates or nwsl_diagnostic_invalid:
        print("STRIKERAPI_RESULT: REVIEW_REQUIRED")
        return 3
    if truncated_checks:
        print("STRIKERAPI_RESULT: PAGINATION_INCOMPLETE")
        return 4
    if not any(
        item["status"] == "final" and item["rows"] > 0
        for item in summaries
    ):
        print("STRIKERAPI_RESULT: INSUFFICIENT_HISTORICAL_SAMPLE")
        return 5
    print("STRIKERAPI_RESULT: BOUNDED_COVERAGE_PASS_PENDING_MANUAL_RECONCILIATION_AND_TERMS_REVIEW")
    return 0


if __name__ == "__main__":
    sys.exit(main())
