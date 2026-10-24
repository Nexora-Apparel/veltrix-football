"""Refresh stale historical scores from football-data.org without using current-day results."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.football_api import FootballAPIError
from app.live_predictions import LEAGUE_DIVISION_BY_CODE, LEAGUE_DIVISION_BY_ID, _name_key

COMPLETED_STATUSES = {"FT", "AET", "PEN"}


def split_date_ranges(start: date, end: date, max_days: int = 7) -> list[tuple[date, date]]:
    """Return non-overlapping inclusive ranges, newest first."""
    if max_days < 1:
        raise ValueError("max_days must be positive")
    if end < start:
        return []
    ranges: list[tuple[date, date]] = []
    cursor = end
    while cursor >= start:
        chunk_start = max(start, cursor - timedelta(days=max_days - 1))
        ranges.append((chunk_start, cursor))
        cursor = chunk_start - timedelta(days=1)
    return ranges


def extract_completed_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize completed football-data.org matches into the same row shape as historical CSV."""
    response = payload.get("response")
    if not isinstance(response, list):
        raise ValueError("Recent-results payload must contain a response list.")
    rows: list[dict[str, Any]] = []
    for item in response:
        fixture = item.get("fixture") or {}
        status = (fixture.get("status") or {}).get("short")
        if status not in COMPLETED_STATUSES:
            continue
        try:
            match_date = date.fromisoformat(str(fixture.get("date", ""))[:10])
        except ValueError:
            continue
        teams = item.get("teams") or {}
        home, away = teams.get("home") or {}, teams.get("away") or {}
        home_name, away_name = str(home.get("name") or "").strip(), str(away.get("name") or "").strip()
        goals = item.get("goals") or {}
        home_goals, away_goals = goals.get("home"), goals.get("away")
        league = item.get("league") or {}
        league_id = league.get("id")
        try:
            league_id = int(league_id)
        except (TypeError, ValueError):
            league_id = None
        if (
            not home_name or not away_name or _name_key(home_name) == _name_key(away_name)
            or not isinstance(home_goals, int) or isinstance(home_goals, bool) or home_goals < 0
            or not isinstance(away_goals, int) or isinstance(away_goals, bool) or away_goals < 0
        ):
            continue
        rows.append({
            "date": match_date,
            "division": LEAGUE_DIVISION_BY_CODE.get(str(league.get("code") or "").upper()) or LEAGUE_DIVISION_BY_ID.get(league_id, ""),
            "home": home_name,
            "away": away_name,
            "home_key": _name_key(home_name),
            "away_key": _name_key(away_name),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "source": "FOOTBALL_DATA_RECENT_RESULTS",
        })
    return rows


def _range_parameters_rejected(exc: FootballAPIError) -> bool:
    """Detect the API's validation response for from/to/timezone range requests."""
    message = str(exc).lower()
    return (
        "api reported errors" in message
        and "need another parameter" in message
        and any(field in message for field in ("'from'", '"from"', "'to'", '"to"'))
    )


def fetch_recent_results(
    api: Any,
    historical_matches: list[dict[str, Any]],
    end_date: date,
    *,
    max_chunk_days: int = 7,
    timezone_name: str = "Africa/Lagos",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch results newer than the open CSV, stopping safely on API-plan errors.

    Date ranges are queried newest-first. If the API rejects the documented range
    parameters, retry that range using individual date queries. The target day is
    excluded by callers passing yesterday as end_date.
    """
    if not historical_matches:
        return [], {
            "status": "NO_BASE_HISTORY",
            "results_added": 0,
            "requested_start": None,
            "requested_end": end_date.isoformat(),
            "covered_from": None,
            "covered_through": None,
            "ranges_succeeded": 0,
            "warning": "No base historical matches were available to anchor the refresh.",
        }
    latest_base = max(row["date"] for row in historical_matches)
    start_date = latest_base + timedelta(days=1)
    if start_date > end_date:
        return [], {
            "status": "UP_TO_DATE",
            "results_added": 0,
            "requested_start": start_date.isoformat(),
            "requested_end": end_date.isoformat(),
            "covered_from": None,
            "covered_through": latest_base.isoformat(),
            "ranges_succeeded": 0,
            "warning": None,
        }

    ranges = split_date_ranges(start_date, end_date, max_chunk_days)
    fetched: list[dict[str, Any]] = []
    successful_ranges: list[tuple[date, date]] = []
    warning = None
    for range_start, range_end in ranges:
        try:
            payload = api.fixtures_between(
                range_start.isoformat(), range_end.isoformat(), timezone_name
            )
            rows = extract_completed_results(payload)
        except (FootballAPIError, ValueError) as exc:
            if not isinstance(exc, FootballAPIError) or not _range_parameters_rejected(exc):
                warning = str(exc)
                break
            # Some API accounts/endpoints reject from/to combinations even though
            # the single-date fixtures endpoint works. Retry only this validation
            # failure, and keep the fallback bounded to the failed range.
            fallback_rows: list[dict[str, Any]] = []
            try:
                day = range_start
                while day <= range_end:
                    daily_payload = api.fixtures(day.isoformat(), timezone_name)
                    fallback_rows.extend(extract_completed_results(daily_payload))
                    day += timedelta(days=1)
            except (FootballAPIError, ValueError) as fallback_exc:
                warning = (
                    f"Range query rejected ({exc}); single-date fallback failed "
                    f"for {day.isoformat()}: {fallback_exc}"
                )
                break
            fetched.extend(
                row for row in fallback_rows
                if range_start <= row["date"] <= range_end
            )
            successful_ranges.append((range_start, range_end))
            continue
        fetched.extend(
            row for row in rows
            if range_start <= row["date"] <= range_end
        )
        successful_ranges.append((range_start, range_end))

    # Deduplicate by date, division, and normalized home/away identity.
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in fetched:
        key = (
            row["date"].isoformat(), row.get("division", ""),
            row["home_key"], row["away_key"],
        )
        unique[key] = row
    fetched = sorted(unique.values(), key=lambda row: (row["date"], row["division"], row["home_key"], row["away_key"]))

    all_ranges_succeeded = len(successful_ranges) == len(ranges)
    if all_ranges_succeeded:
        status = "COMPLETE"
    elif successful_ranges:
        status = "PARTIAL"
    else:
        status = "UNAVAILABLE"
    covered_from = min((start for start, _ in successful_ranges), default=None)
    covered_through = max((end for _, end in successful_ranges), default=None)
    return fetched, {
        "status": status,
        "results_added": len(fetched),
        "requested_start": start_date.isoformat(),
        "requested_end": end_date.isoformat(),
        "covered_from": covered_from.isoformat() if covered_from else None,
        "covered_through": covered_through.isoformat() if covered_through else None,
        "ranges_succeeded": len(successful_ranges),
        "ranges_requested": len(ranges),
        "warning": warning,
    }
