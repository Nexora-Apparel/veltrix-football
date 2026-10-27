"""Refresh stale historical scores from the primary API-Football feed without using current-day results."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.football_api import FootballAPIError  # retained for compatibility with Highlightly adapter tests
from app.api_football_odds import APIFootballError
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
    """Normalize completed API-Football matches into historical rows with stable fixture IDs."""
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
        fixture_id = fixture.get("id")
        try:
            fixture_id = int(fixture_id)
        except (TypeError, ValueError):
            fixture_id = None
        rows.append({
            "date": match_date,
            "division": LEAGUE_DIVISION_BY_CODE.get(str(league.get("code") or "").upper()) or LEAGUE_DIVISION_BY_ID.get(league_id, ""),
            "home": home_name,
            "away": away_name,
            "home_key": _name_key(home_name),
            "away_key": _name_key(away_name),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "fixture_id": fixture_id,
            "fixture_status": status,
            "source": "API_FOOTBALL_RECENT_RESULTS",
        })
    return rows


def _range_parameters_rejected(exc: Exception) -> bool:
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
    max_ranges: int | None = None,
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
    if max_ranges is not None and max_ranges < 1:
        raise ValueError("max_ranges must be positive when provided")
    ranges_to_fetch = ranges if max_ranges is None else ranges[:max_ranges]
    fetched: list[dict[str, Any]] = []
    successful_ranges: list[tuple[date, date]] = []
    warning = None
    for range_start, range_end in ranges_to_fetch:
        try:
            payload = api.fixtures_between(
                range_start.isoformat(), range_end.isoformat(), timezone_name
            )
            rows = extract_completed_results(payload)
        except (FootballAPIError, APIFootballError, ValueError) as exc:
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
            except (FootballAPIError, APIFootballError, ValueError) as fallback_exc:
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

    all_ranges_succeeded = len(successful_ranges) == len(ranges) and len(ranges_to_fetch) == len(ranges)
    if all_ranges_succeeded:
        status = "COMPLETE"
    elif successful_ranges:
        status = "PARTIAL"
    else:
        status = "UNAVAILABLE"
    if max_ranges is not None and len(ranges_to_fetch) < len(ranges):
        limit_notice = (
            f"Refresh limited to {len(ranges_to_fetch)} of {len(ranges)} historical date ranges "
            "per run to protect the provider request quota."
        )
        warning = f"{warning}; {limit_notice}" if warning else limit_notice
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

def fetch_recent_results_incremental(
    api: Any,
    historical_matches: list[dict[str, Any]],
    end_date: date,
    cache_state: dict[str, Any] | None = None,
    *,
    max_chunk_days: int = 7,
    timezone_name: str = "Africa/Lagos",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch one date range per run and return a cursor for resumable, quota-safe history backfill.

    The newest week is fetched first and retained by the caller. Older ranges are then
    backfilled one range per run; after the gap is closed, the cursor advances forward.
    """
    state = dict(cache_state or {})
    if max_chunk_days < 1:
        raise ValueError("max_chunk_days must be positive")
    if not historical_matches:
        return [], {
            "status": "NO_BASE_HISTORY", "results_added": 0,
            "requested_start": None, "requested_end": end_date.isoformat(),
            "covered_from": None, "covered_through": None,
            "ranges_succeeded": 0, "ranges_requested": 0,
            "warning": "No base historical matches were available to anchor the refresh.",
            "cache_state": state,
        }

    latest_base = max(row["date"] for row in historical_matches)
    base_start = latest_base + timedelta(days=1)
    if base_start > end_date and not state.get("backfill_anchor_end"):
        state.update({
            "backfill_complete": True,
            "latest_covered_through": latest_base.isoformat(),
            "next_backfill_end_date": (base_start - timedelta(days=1)).isoformat(),
        })
        return [], {
            "status": "UP_TO_DATE", "results_added": 0,
            "requested_start": base_start.isoformat(), "requested_end": end_date.isoformat(),
            "covered_from": None, "covered_through": latest_base.isoformat(),
            "ranges_succeeded": 0, "ranges_requested": 0, "warning": None,
            "cache_state": state,
        }

    anchor_raw = state.get("backfill_anchor_end")
    cursor_raw = state.get("next_backfill_end_date")
    latest_covered_raw = state.get("latest_covered_through")
    if not anchor_raw:
        anchor = end_date
        state["backfill_anchor_end"] = anchor.isoformat()
        state["next_backfill_end_date"] = end_date.isoformat()
        state["backfill_complete"] = False
        cursor = end_date
    else:
        try:
            anchor = date.fromisoformat(str(anchor_raw))
            cursor = date.fromisoformat(str(cursor_raw)) if cursor_raw else base_start - timedelta(days=1)
        except ValueError:
            anchor = end_date
            cursor = end_date
            state = {
                "backfill_anchor_end": anchor.isoformat(),
                "next_backfill_end_date": cursor.isoformat(),
                "latest_covered_through": latest_covered_raw,
                "backfill_complete": False,
            }

    backfill_complete = bool(state.get("backfill_complete")) or cursor < base_start
    if not backfill_complete:
        range_end = min(cursor, end_date)
        range_start = max(base_start, range_end - timedelta(days=max_chunk_days - 1))
        total_ranges = len(split_date_ranges(base_start, anchor, max_chunk_days))
        phase = "backfill"
        progress_before = (
            total_ranges - len(split_date_ranges(base_start, cursor, max_chunk_days))
            if cursor >= base_start else total_ranges
        )
    else:
        latest_covered = (
            date.fromisoformat(str(latest_covered_raw))
            if latest_covered_raw else latest_base
        )
        range_start = max(base_start, latest_covered + timedelta(days=1))
        if range_start > end_date:
            state["backfill_complete"] = True
            state["next_backfill_end_date"] = (base_start - timedelta(days=1)).isoformat()
            return [], {
                "status": "UP_TO_DATE", "results_added": 0,
                "requested_start": range_start.isoformat(), "requested_end": end_date.isoformat(),
                "covered_from": None, "covered_through": latest_covered.isoformat(),
                "ranges_succeeded": 0, "ranges_requested": 0, "warning": None,
                "cache_state": state,
            }
        range_end = min(end_date, range_start + timedelta(days=max_chunk_days - 1))
        total_ranges = len(split_date_ranges(range_start, end_date, max_chunk_days))
        phase = "catchup"
        progress_before = 0

    rows: list[dict[str, Any]] = []
    warning = None
    provider_meta: dict[str, Any] = {}
    successful_dates: list[str] = []
    failed_dates: list[str] = []
    try:
        payload = api.fixtures_between(
            range_start.isoformat(), range_end.isoformat(), timezone_name
        )
        rows = extract_completed_results(payload)
        provider_meta = payload.get("_veltrix_meta") or {}
        raw_failed = provider_meta.get("failed_dates")
        failed_dates = [str(value) for value in raw_failed if isinstance(value, str)] if isinstance(raw_failed, list) else []
        raw_successful = provider_meta.get("successful_dates")
        if isinstance(raw_successful, list):
            successful_dates = [str(value) for value in raw_successful if isinstance(value, str)]
        else:
            day = range_start
            while day <= range_end:
                successful_dates.append(day.isoformat())
                day += timedelta(days=1)
    except (FootballAPIError, APIFootballError, ValueError) as exc:
        if isinstance(exc, FootballAPIError) and _range_parameters_rejected(exc):
            try:
                day = range_start
                while day <= range_end:
                    daily_payload = api.fixtures(day.isoformat(), timezone_name)
                    rows.extend(extract_completed_results(daily_payload))
                    successful_dates.append(day.isoformat())
                    day += timedelta(days=1)
            except (FootballAPIError, APIFootballError, ValueError) as fallback_exc:
                warning = f"Range query rejected; single-date fallback failed: {fallback_exc}"
                rows = []
                successful_dates = []
        else:
            warning = str(exc)

    rows = [row for row in rows if range_start <= row["date"] <= range_end]
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["date"].isoformat(), row.get("division", ""), row["home_key"], row["away_key"])
        unique[key] = row
    rows = sorted(
        unique.values(),
        key=lambda row: (row["date"], row.get("division", ""), row["home_key"], row["away_key"]),
    )

    existing_gaps = state.get("history_gaps")
    history_gaps = set(str(value) for value in existing_gaps if isinstance(value, str)) if isinstance(existing_gaps, list) else set()
    history_gaps.difference_update(successful_dates)
    history_gaps.update(failed_dates)
    if history_gaps:
        state["history_gaps"] = sorted(history_gaps)
    elif "history_gaps" in state:
        state.pop("history_gaps", None)
    plan_warning = provider_meta.get("warning") if failed_dates else None

    succeeded = warning is None
    successful_date_objects = []
    for value in successful_dates:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            continue
        if range_start <= parsed <= range_end:
            successful_date_objects.append(parsed)
    if succeeded and phase == "backfill":
        next_cursor = range_start - timedelta(days=1)
        previous_latest = date.fromisoformat(str(latest_covered_raw)) if latest_covered_raw else (base_start - timedelta(days=1))
        latest_covered = max([previous_latest, *successful_date_objects])
        complete_now = next_cursor < base_start
        state.update({
            "backfill_anchor_end": anchor.isoformat(),
            "next_backfill_end_date": next_cursor.isoformat(),
            "latest_covered_through": latest_covered.isoformat(),
            "backfill_complete": complete_now,
        })
        progress_after = (
            total_ranges if complete_now
            else total_ranges - len(split_date_ranges(base_start, next_cursor, max_chunk_days))
        )
        status = "PARTIAL" if failed_dates or not complete_now else "COMPLETE"
        if plan_warning:
            warning = str(plan_warning)
        elif not complete_now:
            warning = (
                f"Historical backfill progress: {progress_after} of {total_ranges} date ranges. "
                "History remains non-contiguous until the remaining ranges are fetched."
            )
    elif succeeded:
        previous_latest = date.fromisoformat(str(latest_covered_raw)) if latest_covered_raw else (base_start - timedelta(days=1))
        latest_covered = max([previous_latest, *successful_date_objects])
        state.update({
            "backfill_complete": True,
            "latest_covered_through": latest_covered.isoformat(),
            "next_backfill_end_date": (base_start - timedelta(days=1)).isoformat(),
        })
        progress_after = 1
        status = "PARTIAL" if failed_dates or range_end < end_date else "COMPLETE"
        if plan_warning:
            warning = str(plan_warning)
        elif status == "PARTIAL":
            warning = f"Catch-up progress: 1 of {total_ranges} date ranges refreshed; remaining dates will be handled in later runs."
    else:
        progress_after = progress_before
        status = "PARTIAL" if progress_before else "UNAVAILABLE"

    return rows, {
        "status": status,
        "results_added": len(rows),
        "requested_start": range_start.isoformat(),
        "requested_end": range_end.isoformat(),
        "covered_from": min(successful_date_objects).isoformat() if succeeded and successful_date_objects else None,
        "covered_through": max(successful_date_objects).isoformat() if succeeded and successful_date_objects else None,
        "ranges_succeeded": progress_after,
        "ranges_requested": total_ranges,
        "warning": warning,
        "cache_state": state,
    }

