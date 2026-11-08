"""Low-quota provider verification and historical preflight; strictly read-only.

Uses at most nine GET requests: four account/coverage/sample requests plus one
90-day finished-fixture page for each competition available on the account.
Never prints credentials, request URLs, or raw provider payloads.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.5dollarfootballapi.com/v1"
TIMEOUT = 20
PAGE_SIZE = 100


class ProviderCheckError(RuntimeError):
    pass


def request_json(path: str, params: dict[str, object] | None = None):
    query = "?" + urlencode(params or {}) if params else ""
    req = Request(
        BASE + path + query,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {os.environ['FIVEDOLLARFOOTBALL_API_KEY'].strip()}",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, response.headers, payload
    except HTTPError as exc:
        safe = [f"HTTP {exc.code}"]
        for header, label in (
            ("X-RateLimit-Limit", "limit"),
            ("X-RateLimit-Remaining", "remaining"),
            ("X-RateLimit-Reset", "reset"),
            ("Retry-After", "retry_after"),
        ):
            value = (exc.headers or {}).get(header)
            if value:
                safe.append(f"{label}={str(value)[:40]}")
        raise ProviderCheckError("; ".join(safe)) from None
    except (URLError, TimeoutError, OSError):
        raise ProviderCheckError("network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderCheckError("invalid JSON response") from None


def envelope(payload):
    if not isinstance(payload, dict) or payload.get("success") not in (1, True, "1", "true"):
        return None
    return payload.get("data")


def safe_scalar(value) -> str:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return re.sub(r"[^A-Za-z0-9 _./+-]", "", str(value))[:60] or "not reported"
    return "not reported"


def rate_summary(headers) -> str:
    fields = []
    for name, label in (
        ("X-RateLimit-Limit", "limit"),
        ("X-RateLimit-Remaining", "remaining"),
        ("X-RateLimit-Reset", "reset"),
    ):
        value = headers.get(name)
        if value is not None:
            fields.append(f"{label}={str(value)[:40]}")
    return ", ".join(fields) if fields else "rate-limit headers not supplied"


def is_nonnegative_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def main() -> int:
    if not os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip():
        print("5DollarFootballAPI: MISSING_SECRET (FIVEDOLLARFOOTBALL_API_KEY)")
        return 2

    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=90)
    start_ts, end_ts = int(start.timestamp()), int(now.timestamp())
    print(f"HISTORICAL_PREFLIGHT_WINDOW_UTC: [{start.isoformat()}, {now.isoformat()})")

    checks = (
        ("/status", None, "account status"),
        ("/countries", {"per_page": PAGE_SIZE}, "country coverage"),
        ("/leagues", {"per_page": PAGE_SIZE}, "competition coverage"),
        ("/fixtures", {"status": "scheduled", "per_page": 1}, "single scheduled fixture"),
    )
    results = {}
    for path, params, label in checks:
        try:
            status, headers, payload = request_json(path, params)
            data = envelope(payload)
            if status != 200 or data is None:
                print(f"5DollarFootballAPI {label}: UNEXPECTED_RESPONSE")
                return 1
            results[path] = (data, headers, payload.get("pagination"))
            print(f"5DollarFootballAPI {label}: HTTP {status}; {rate_summary(headers)}")
        except ProviderCheckError as exc:
            print(f"5DollarFootballAPI {label}: FAILED ({exc})")
            return 1

    status_data = results["/status"][0]
    if not isinstance(status_data, dict):
        print("5DollarFootballAPI status payload: UNEXPECTED_DATA_SHAPE")
        return 1
    limits = status_data.get("limits") if isinstance(status_data.get("limits"), dict) else {}
    usage = status_data.get("usage") if isinstance(status_data.get("usage"), dict) else {}
    plan = status_data.get("plan")
    print(
        "5DollarFootballAPI entitlement: "
        f"plan={safe_scalar(plan)}; daily_usage={safe_scalar(usage.get('today'))}; "
        f"rate_limit={safe_scalar(limits.get('rate_limit'))}/"
        f"{safe_scalar(limits.get('rate_window_seconds'))}s; "
        f"burst_per_minute={safe_scalar(limits.get('burst_per_minute'))}"
    )

    countries, leagues, scheduled = (results[k][0] for k in ("/countries", "/leagues", "/fixtures"))
    if not all(isinstance(v, list) for v in (countries, leagues, scheduled)):
        print("5DollarFootballAPI catalog/sample: UNEXPECTED_DATA_SHAPE")
        return 1

    for endpoint, rows, label in (
        ("/countries", countries, "country"),
        ("/leagues", leagues, "competition"),
    ):
        meta = results[endpoint][2] if isinstance(results[endpoint][2], dict) else {}
        print(
            f"5DollarFootballAPI {label} catalog: page_records={len(rows)}; "
            f"page={safe_scalar(meta.get('page'))}; per_page={safe_scalar(meta.get('per_page'))}; "
            f"has_more={str(meta.get('has_more', 'not reported'))}"
        )
    print(f"5DollarFootballAPI scheduled sample: {len(scheduled)} fixture(s), maximum requested 1")

    # One bounded historical page per competition exposed by this account.
    # The provider's Free plan is documented as three months of results.
    all_ids = set()
    duplicate_ids = set()
    source_rows = valid_results = invalid_finished = unresolved_team_ids = 0
    has_more_competitions = []
    earliest = latest = None
    final_remaining = None

    for league in leagues:
        if not isinstance(league, dict) or not isinstance(league.get("id"), int):
            print("HISTORICAL_PREFLIGHT: invalid competition identity in provider catalog")
            return 1
        league_id = league["id"]
        league_name = safe_scalar(league.get("name"))
        path = f"/leagues/{league_id}/fixtures"
        params = {
            "start_time": start_ts,
            "end_time": end_ts,
            "status": "finished",
            "page": 1,
            "per_page": PAGE_SIZE,
            "order": "asc",
        }
        try:
            status, headers, payload = request_json(path, params)
        except ProviderCheckError as exc:
            print(f"HISTORICAL_PREFLIGHT {league_name}: FAILED ({exc})")
            return 1
        rows = envelope(payload)
        if status != 200 or not isinstance(rows, list):
            print(f"HISTORICAL_PREFLIGHT {league_name}: UNEXPECTED_RESPONSE")
            return 1
        final_remaining = headers.get("X-RateLimit-Remaining", final_remaining)
        pagination = payload.get("pagination") if isinstance(payload, dict) else {}
        more = bool(pagination.get("has_more")) if isinstance(pagination, dict) else False
        if more:
            has_more_competitions.append(league_name)

        comp_valid = comp_invalid = 0
        for fixture in rows:
            source_rows += 1
            if not isinstance(fixture, dict):
                invalid_finished += 1
                comp_invalid += 1
                continue
            fixture_id = fixture.get("id")
            if fixture_id is None:
                invalid_finished += 1
                comp_invalid += 1
            elif fixture_id in all_ids:
                duplicate_ids.add(fixture_id)
            else:
                all_ids.add(fixture_id)

            goals = fixture.get("goals") if isinstance(fixture.get("goals"), dict) else {}
            score_ok = is_nonnegative_integer(goals.get("home")) and is_nonnegative_integer(goals.get("away"))
            if fixture.get("status") == "finished" and score_ok:
                valid_results += 1
                comp_valid += 1
            else:
                invalid_finished += 1
                comp_invalid += 1

            teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
            home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
            away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
            if home.get("id") is None or away.get("id") is None:
                unresolved_team_ids += 1

            kickoff = fixture.get("kickoff_utc")
            if isinstance(kickoff, str):
                try:
                    parsed = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                    earliest = parsed if earliest is None or parsed < earliest else earliest
                    latest = parsed if latest is None or parsed > latest else latest
                except ValueError:
                    pass

        print(
            f"HISTORICAL_PREFLIGHT {league_name} (id={league_id}): "
            f"source_rows={len(rows)}; valid_finished_results={comp_valid}; "
            f"invalid_or_unsettled={comp_invalid}; has_more={str(more)}"
        )

    complete = not has_more_competitions
    print(
        "HISTORICAL_PREFLIGHT_SUMMARY: "
        f"competitions={len(leagues)}; source_rows={source_rows}; "
        f"unique_fixture_ids={len(all_ids)}; duplicate_fixture_ids={len(duplicate_ids)}; "
        f"valid_finished_results={valid_results}; invalid_or_unsettled={invalid_finished}; "
        f"missing_team_ids={unresolved_team_ids}; "
        f"kickoff_range={earliest.isoformat() if earliest else 'none'}..{latest.isoformat() if latest else 'none'}; "
        f"all_pages_complete={str(complete)}; "
        f"additional_pages_required_at_least={len(has_more_competitions)}; "
        f"rate_limit_remaining_after_run={safe_scalar(final_remaining)}"
    )
    print("DATABASE_WRITES: 0; IMPORTED_RECORDS: 0; IMPORT_RUNS_CREATED: 0; CHECKPOINTS_CREATED: 0")
    if not complete:
        print("HISTORICAL_PREFLIGHT_RESULT: INCOMPLETE (additional pages required; no import performed)")
        return 3
    if invalid_finished or duplicate_ids or unresolved_team_ids:
        print("HISTORICAL_PREFLIGHT_RESULT: REVIEW_REQUIRED (identity/result integrity exceptions; no import performed)")
        return 4
    print("HISTORICAL_PREFLIGHT_RESULT: PASS (bounded 90-day source dry-run; no database writes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
