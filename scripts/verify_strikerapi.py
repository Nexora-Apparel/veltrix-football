"""Bounded, read-only StrikerAPI qualification for VELTRIX FOOTBALL.

Seven list_games calls maximum (14 credits at the documented 2 credits/call):
final + scheduled samples for Argentina, Brazil and NWSL, plus an EPL overlap.
No database access, imports, artifact uploads, or credential output.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://mcp.strikerapi.com/v1/list_games"
TIMEOUT = 25
LIMIT = 5
WINDOW_DAYS = 90
FUTURE_DAYS = 30
# Seven calls x 2 documented credits = 14 credits maximum.
CHECKS = (
    ("argentina", "final"),
    ("argentina", "scheduled"),
    ("brazil", "final"),
    ("brazil", "scheduled"),
    ("nwsl", "final"),
    ("nwsl", "scheduled"),
    ("soccer", "final"),  # overlap sample; manually reconcile to 5Dollar IDs
)


class ProbeError(RuntimeError):
    pass


def safe_text(value: object, max_len: int = 180) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return "not reported"
    return re.sub(r"[^A-Za-z0-9 _./:+-]", "", str(value))[:max_len] or "not reported"


def call_api(api_key: str, league: str, status: str, start: str, end: str) -> dict:
    body = {
        "league": league,
        "status": status,
        "from": start,
        "to": end,
        "limit": LIMIT,
    }
    request = Request(
        BASE,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": "VELTRIX-FOOTBALL-read-only-qualification/1.0",
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
        # Do not print response body: it may contain account or request details.
        raise ProbeError(f"HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("invalid JSON response") from None


def validate_game(row: object, expected_status: str) -> tuple[bool, str]:
    if not isinstance(row, dict):
        return False, "not_object"
    required = ("game_id", "date", "starts_at", "status", "home", "away")
    if any(row.get(field) in (None, "") for field in required):
        return False, "missing_identity_or_schedule_fields"
    if row.get("status") != expected_status:
        return False, "status_mismatch"
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
    print(f"PROBE_WINDOWS: final={historical_start}..{today_text}; scheduled={today_text}..{future_end}")
    print("REQUEST_BUDGET: maximum_calls=7; documented_credits_per_call=2; maximum_credits=14")
    print("NOTE: This is a sample qualification, not a complete historical export.")

    seen = {}
    total_rows = 0
    attempted_calls = 0
    total_valid = 0
    total_invalid = 0
    final_counts = {}
    schedule_counts = {}

    for league, status in CHECKS:
        start, end = (historical_start, today_text) if status == "final" else (today_text, future_end)
        attempted_calls += 1
        try:
            data = call_api(key, league, status, start, end)
        except ProbeError as exc:
            print(f"STRIKERAPI_CHECK_FAILED: league={league}; status={status}; reason={safe_text(str(exc))}")
            print(f"API_CALLS_ATTEMPTED: {attempted_calls}; DATABASE_WRITES: 0; IMPORTS: 0")
            return 1

        games = data.get("games")
        if not isinstance(games, list):
            print(f"STRIKERAPI_UNEXPECTED_SCHEMA: league={league}; status={status}; expected_games_array")
            return 1

        valid = invalid = duplicates = 0
        for row in games:
            total_rows += 1
            ok, reason = validate_game(row, status)
            if ok:
                valid += 1
                total_valid += 1
                game_id = str(row["game_id"])
                identity = (league, game_id)
                if identity in seen:
                    duplicates += 1
                else:
                    seen[identity] = row
            else:
                invalid += 1
                total_invalid += 1

        if status == "final":
            final_counts[league] = len(games)
        else:
            schedule_counts[league] = len(games)

        print(
            f"STRIKERAPI_SAMPLE: league={league}; status={status}; rows={len(games)}; "
            f"valid={valid}; invalid={invalid}; duplicate_ids={duplicates}; "
            f"count_field={safe_text(data.get('count'))}; next_offset={safe_text(data.get('next_offset'))}"
        )

    print(
        "STRIKERAPI_SUMMARY: "
        f"calls={len(CHECKS)}; documented_credit_cost={len(CHECKS) * 2}; "
        f"rows={total_rows}; valid={total_valid}; invalid={total_invalid}; "
        f"final_samples={json.dumps(final_counts, sort_keys=True)}; "
        f"scheduled_samples={json.dumps(schedule_counts, sort_keys=True)}"
    )
    print("DATABASE_WRITES: 0; IMPORTED_RECORDS: 0; IMPORT_RUNS: 0; CHECKPOINTS: 0")
    if total_invalid:
        print("STRIKERAPI_RESULT: REVIEW_REQUIRED")
        return 3
    if not any(final_counts.get(k, 0) for k in ("argentina", "brazil", "nwsl")):
        print("STRIKERAPI_RESULT: INSUFFICIENT_HISTORICAL_SAMPLE")
        return 4
    print("STRIKERAPI_RESULT: SAMPLE_PASS_PENDING_MANUAL_COVERAGE_AND_TERMS_REVIEW")
    return 0


if __name__ == "__main__":
    sys.exit(main())
