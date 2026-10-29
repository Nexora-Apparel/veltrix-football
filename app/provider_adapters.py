"""Multi-source football provider adapters for Veltrix.

5DollarFootballAPI supplies canonical fixtures/results and its Bet365 market feed.
The Odds API supplies independent bookmaker market snapshots. Provider IDs are never
assumed to be interchangeable; cross-source odds are joined by exact normalized
home/away names and the kickoff's Africa/Lagos calendar date.
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from app.api_football_odds import APIFootballError
from app.live_predictions import _name_key as _canonical_name_key


FIVEDOLLAR_BASE_URL = "https://api.5dollarfootballapi.com/v1"
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_SOCCER_SPORTS = (
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
)
STATUS_MAP = {
    "scheduled": "NS", "in_play": "LIVE", "finished": "FT",
    "unknown": "TBD", "postponed": "PST", "cancelled": "CANC",
}
LEAGUE_CODES = {
    "premier league": "PL", "english premier league": "PL",
    "championship": "ELC", "league one": "EL1", "league two": "EL2",
    "la liga": "PD", "laliga": "PD", "serie a": "SA", "serie b": "SB",
    "bundesliga": "BL1", "2. bundesliga": "BL2", "ligue 1": "FL1",
    "ligue 2": "FL2", "eredivisie": "DED", "primeira liga": "PPL",
    "liga portugal": "PPL", "scottish premiership": "SPL",
    "brasileirao": "BSA", "brazil serie a": "BSA", "bra a": "BSA",
    "allsvenskan": "SWE", "swedish allsvenskan": "SWE",
}


class ProviderAPIError(APIFootballError):
    """Sanitized provider error compatible with the existing history-refresh guard."""


def _name_key(value: Any) -> str:
    """Use the model pipeline's canonical team aliases for cross-source joins."""
    return _canonical_name_key(value)


def _json_request(url: str, headers: dict[str, str] | None = None, timeout: int = 20):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "VeltrixFootball/1.0", **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, response.headers, payload
    except HTTPError as exc:
        raise ProviderAPIError(f"Provider request failed with HTTP {exc.code}.") from None
    except (URLError, OSError, TimeoutError):
        raise ProviderAPIError("Provider network request failed.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderAPIError("Provider returned invalid JSON.") from None


def _status_code(raw: Any) -> str:
    return STATUS_MAP.get(str(raw or "unknown").strip().casefold(), "TBD")


def normalize_fivedollar_fixture(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a 5DollarFootballAPI fixture to Veltrix's existing fixture schema."""
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    goals = item.get("goals") or {}
    league_name = str(league.get("name") or "").strip()
    kickoff = str(item.get("kickoff_utc") or "")
    if not kickoff and item.get("kickoff_ts") is not None:
        try:
            kickoff = datetime.fromtimestamp(int(item["kickoff_ts"]), timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            kickoff = ""
    return {
        "fixture": {
            "id": item.get("id"),
            "date": kickoff,
            "timestamp": item.get("kickoff_ts"),
            "status": {"short": _status_code(item.get("status")), "long": str(item.get("status") or "unknown")},
        },
        "teams": {
            "home": {"id": home.get("id"), "name": home.get("name")},
            "away": {"id": away.get("id"), "name": away.get("name")},
        },
        "league": {
            "id": league.get("id"),
            "name": league_name,
            "code": LEAGUE_CODES.get(league_name.casefold()),
            "season": None,
        },
        "goals": {"home": goals.get("home"), "away": goals.get("away")},
        "_veltrix_source": "5DollarFootballAPI",
        "_source_status": item.get("status"),
    }


class FiveDollarFootballClient:
    """5DollarFootballAPI client; all date filters are converted to UTC timestamps."""

    provider_name = "5DollarFootballAPI"
    base_url = FIVEDOLLAR_BASE_URL

    def __init__(self, api_key: str | None = None, timeout: int = 20):
        self.api_key = (api_key if api_key is not None else os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "")).strip()
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any, Any]:
        if not self.api_key:
            raise ProviderAPIError("FIVEDOLLARFOOTBALL_API_KEY is missing.")
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}/{path.lstrip('/')}" + (f"?{query}" if query else "")
        status, headers, payload = _json_request(url, {"Authorization": f"Bearer {self.api_key}"}, self.timeout)
        if status != 200 or not isinstance(payload, dict) or payload.get("success") != 1:
            raise ProviderAPIError("5DollarFootballAPI returned an unsuccessful or unexpected response.")
        return payload, headers

    @staticmethod
    def _local_day_window(day: date, timezone_name: str) -> tuple[int, int]:
        zone = ZoneInfo(timezone_name)
        start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
        return int(start.timestamp()), int(end.timestamp())

    def fixtures(self, day: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        target = date.fromisoformat(day)
        start_ts, end_ts = self._local_day_window(target, timezone)
        all_items: list[dict[str, Any]] = []
        page, pages = 1, 0
        remaining = None
        while pages < 20:
            payload, headers = self._get("fixtures", {
                "start_time": start_ts, "end_time": end_ts, "status": "all",
                "page": page, "per_page": 100,
            })
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise ProviderAPIError("5DollarFootballAPI fixtures response is missing its data list.")
            all_items.extend(item for item in rows if isinstance(item, dict))
            remaining = headers.get("X-RateLimit-Remaining", remaining)
            pages += 1
            pagination = payload.get("pagination") or {}
            if not pagination.get("has_more"):
                break
            page += 1
        else:
            raise ProviderAPIError("5DollarFootballAPI fixture pagination exceeded the safety limit.")
        normalized = [normalize_fivedollar_fixture(item) for item in all_items]
        return {
            "response": normalized,
            "results": len(normalized),
            "pagination": {"fetchedCount": len(normalized), "pagesFetched": pages, "complete": True},
            "provider": "5DollarFootballAPI",
            "_veltrix_meta": {
                "provider": "5DollarFootballAPI", "requests_made": pages,
                "requests_remaining": remaining, "pages_fetched": pages,
            },
        }

    def fixtures_between(self, start_date: str, end_date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if end < start:
            raise ProviderAPIError("end date must be on or after start date.")
        if (end - start).days > 6:
            raise ProviderAPIError("5DollarFootballAPI fixture windows are limited to seven days per history chunk.")
        rows: list[dict[str, Any]] = []
        requests_made = 0
        remaining = None
        successful_dates: list[str] = []
        failed_dates: list[str] = []
        empty_response_dates: list[str] = []
        today_local = datetime.now(ZoneInfo(timezone)).date()
        cursor = start
        while cursor <= end:
            day_text = cursor.isoformat()
            try:
                payload = self.fixtures(day_text, timezone)
                day_rows = payload["response"]
                rows.extend(day_rows)
                meta = payload.get("_veltrix_meta") or {}
                requests_made += int(meta.get("requests_made", 1) or 1)
                remaining = meta.get("requests_remaining", remaining)
                if not day_rows and cursor < today_local:
                    # An empty response for a historical date is not proof that
                    # the date is covered; keep it as a retryable gap.
                    failed_dates.append(day_text)
                    empty_response_dates.append(day_text)
                else:
                    successful_dates.append(day_text)
            except ProviderAPIError:
                # Keep successful dates from this window instead of discarding them
                # when one date is inaccessible. Failed dates remain retryable.
                requests_made += 1
                failed_dates.append(day_text)
            cursor += timedelta(days=1)
        warning = (
            f"No fixtures returned for {len(empty_response_dates)} historical date(s); dates remain retryable."
            if empty_response_dates else None
        )
        return {
            "response": rows, "results": len(rows), "provider": "5DollarFootballAPI",
            "_veltrix_meta": {
                "provider": "5DollarFootballAPI", "requests_made": requests_made,
                "requests_remaining": remaining, "successful_dates": successful_dates,
                "failed_dates": failed_dates, "empty_response_dates": empty_response_dates,
                "warning": warning,
            },
        }

    def status(self) -> dict[str, Any]:
        payload, headers = self._get("status")
        return {
            "provider": "5DollarFootballAPI",
            "status": "CONNECTED",
            "data": payload.get("data"),
            "_veltrix_meta": {"provider": "5DollarFootballAPI", "requests_remaining": headers.get("X-RateLimit-Remaining")},
        }

    def leagues(self, page: int = 1, per_page: int = 100) -> dict[str, Any]:
        payload, headers = self._get("leagues", {"page": page, "per_page": min(max(per_page, 1), 100)})
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ProviderAPIError("5DollarFootballAPI leagues response is missing its data list.")
        return {
            "response": rows, "results": len(rows), "pagination": payload.get("pagination"),
            "provider": "5DollarFootballAPI",
            "_veltrix_meta": {"provider": "5DollarFootballAPI", "requests_remaining": headers.get("X-RateLimit-Remaining")},
        }

    def fixture_odds(self, fixture_id: Any) -> dict[str, Any]:
        payload, headers = self._get(f"fixtures/{fixture_id}/odds")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProviderAPIError("5DollarFootballAPI fixture-odds response is missing its data object.")
        return {"data": data, "_veltrix_meta": {"provider": "5DollarFootballAPI", "requests_remaining": headers.get("X-RateLimit-Remaining")}}


class TheOddsAPIClient:
    """The Odds API v4 adapter. Additional BTTS markets are fetched per event, with a hard cap."""

    base_url = ODDS_API_BASE_URL

    def __init__(self, api_key: str | None = None, timeout: int = 20):
        self.api_key = (api_key if api_key is not None else os.getenv("THE_ODDS_API_KEY", "")).strip()
        self.timeout = timeout
        self.last_quota: dict[str, str | None] = {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any, Any]:
        if not self.api_key:
            raise ProviderAPIError("THE_ODDS_API_KEY is missing.")
        query = dict(params or {})
        query["apiKey"] = self.api_key
        status, headers, payload = _json_request(f"{self.base_url}/{path.lstrip('/')}?{urlencode(query)}", timeout=self.timeout)
        self.last_quota = {
            "remaining": headers.get("x-requests-remaining"),
            "used": headers.get("x-requests-used"),
            "last_cost": headers.get("x-requests-last"),
        }
        if status != 200:
            raise ProviderAPIError("The Odds API returned an unsuccessful response.")
        return payload, headers

    def soccer_sports(self) -> list[dict[str, Any]]:
        payload, _ = self._get("sports")
        if not isinstance(payload, list):
            raise ProviderAPIError("The Odds API sports response had an unexpected shape.")
        return [row for row in payload if isinstance(row, dict) and str(row.get("key", "")).startswith("soccer_") and row.get("active", True)]

    def events_for_sport(self, sport_key: str) -> list[dict[str, Any]]:
        """List events for a supported soccer competition without requesting odds markets."""
        payload, _ = self._get(f"sports/{sport_key}/events", {"dateFormat": "iso"})
        if not isinstance(payload, list):
            raise ProviderAPIError("The Odds API events response had an unexpected shape.")
        return [row for row in payload if isinstance(row, dict)]

    def odds_for_sport(self, sport_key: str, *, regions: str = "uk", markets: str = "h2h,totals") -> list[dict[str, Any]]:
        payload, _ = self._get(f"sports/{sport_key}/odds", {
            "regions": regions, "markets": markets, "oddsFormat": "decimal", "dateFormat": "iso",
        })
        if not isinstance(payload, list):
            raise ProviderAPIError("The Odds API odds response had an unexpected shape.")
        return [row for row in payload if isinstance(row, dict)]

    def event_btts(self, sport_key: str, event_id: str, *, regions: str = "uk") -> list[dict[str, Any]]:
        payload, _ = self._get(f"sports/{sport_key}/events/{event_id}/odds", {
            "regions": regions, "markets": "btts", "oddsFormat": "decimal", "dateFormat": "iso",
        })
        if isinstance(payload, dict):
            return [payload]
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []


class InferSportsClient:
    """Keyless read-only InferSports REST client for supplemental full-time totals/1X2."""

    base_url = "https://api.infersports.dev"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any, Any]:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}/{path.lstrip('/')}" + (f"?{query}" if query else "")
        status, headers, payload = _json_request(url, timeout=self.timeout)
        if status != 200:
            raise ProviderAPIError("InferSports returned an unsuccessful response.")
        return payload, headers

    def events_for_date(self, day: str, timezone_name: str = "Africa/Lagos") -> list[dict[str, Any]]:
        payload, _ = self._get("v1/events", {
            "sport": "football", "date": day, "timezone": timezone_name,
            "status": "scheduled", "limit": 200,
        })
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ProviderAPIError("InferSports events response had an unexpected shape.")
        return [row for row in rows if isinstance(row, dict)]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        payload, _ = self._get(f"v1/events/{event_id}/odds", {
            "markets": "1x2,totals", "period": "full_time", "format": "decimal",
        })
        if not isinstance(payload, dict) or not isinstance(payload.get("odds"), list):
            raise ProviderAPIError("InferSports odds response had an unexpected shape.")
        return payload


def _valid_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return price if math.isfinite(price) and 1.0 < price < 1000 else None


def _event_local_date(event: dict[str, Any], timezone_name: str) -> str | None:
    raw = event.get("commence_time")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    except (ValueError, OverflowError):
        return None


def _event_market_summary(event: dict[str, Any]) -> dict[str, Any]:
    markets: dict[str, Any] = {"h2h": [], "totals": [], "btts": []}
    for bookmaker in event.get("bookmakers") or []:
        if not isinstance(bookmaker, dict):
            continue
        for market in bookmaker.get("markets") or []:
            if not isinstance(market, dict):
                continue
            key = str(market.get("key") or "")
            if key not in markets:
                continue
            outcomes = []
            for outcome in market.get("outcomes") or []:
                if not isinstance(outcome, dict):
                    continue
                price = _valid_price(outcome.get("price"))
                if price is None:
                    continue
                outcomes.append({
                    "name": str(outcome.get("name") or ""),
                    "price": price,
                    "point": outcome.get("point"),
                })
            if outcomes:
                markets[key].append({
                    "bookmaker": str(bookmaker.get("title") or bookmaker.get("key") or ""),
                    "last_update": market.get("last_update"),
                    "outcomes": outcomes,
                })
    return markets


def supplement_fixtures_from_odds_api(
    fixtures_payload: dict[str, Any],
    day: str,
    *,
    timezone_name: str = "Africa/Lagos",
    client: TheOddsAPIClient | None = None,
    max_sports: int = 5,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Supplement limited primary fixture coverage with same-day major-league events.

    Only scheduled future events on the requested local date are added. Existing
    fixtures win duplicate joins; failed supplemental requests never discard the
    primary provider's data.
    """
    odds_client = client or TheOddsAPIClient()
    if not odds_client.api_key:
        return fixtures_payload
    zone = ZoneInfo(timezone_name)
    target_day = date.fromisoformat(day)
    current = now or datetime.now(zone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=zone)
    current = current.astimezone(zone)

    league_by_sport = {
        "soccer_epl": ("Premier League", "PL"),
        "soccer_spain_la_liga": ("La Liga", "PD"),
        "soccer_germany_bundesliga": ("Bundesliga", "BL1"),
        "soccer_italy_serie_a": ("Serie A", "SA"),
        "soccer_france_ligue_one": ("Ligue 1", "FL1"),
    }
    rows = fixtures_payload.get("response")
    if not isinstance(rows, list):
        rows = []
        fixtures_payload["response"] = rows

    def event_key(home: Any, away: Any) -> tuple[str, str, str]:
        return (target_day.isoformat(), _name_key(home), _name_key(away))

    existing: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        teams = row.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        raw = (row.get("fixture") or {}).get("date")
        if not home or not away or not isinstance(raw, str):
            continue
        try:
            kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=zone)
            local = kickoff.astimezone(zone)
            if local.date() == target_day:
                existing.add(event_key(home, away))
        except (ValueError, OverflowError):
            continue

    added = 0
    queried: list[str] = []
    failed: list[str] = []
    for sport_key in list(league_by_sport)[:max(0, min(max_sports, 5))]:
        try:
            events = odds_client.events_for_sport(sport_key)
            queried.append(sport_key)
        except ProviderAPIError:
            failed.append(sport_key)
            continue
        league_name, division_code = league_by_sport[sport_key]
        for event in events:
            home, away = event.get("home_team"), event.get("away_team")
            raw = event.get("commence_time")
            if not isinstance(home, str) or not home.strip() or not isinstance(away, str) or not away.strip() or not isinstance(raw, str):
                continue
            try:
                kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)
                local = kickoff.astimezone(zone)
            except (ValueError, OverflowError):
                continue
            if local.date() != target_day or local <= current:
                continue
            key = event_key(home, away)
            if key in existing:
                continue
            event_id = event.get("id")
            rows.append({
                "fixture": {
                    "id": str(event_id) if event_id is not None else None,
                    "date": kickoff.isoformat(),
                    "timestamp": int(kickoff.timestamp()),
                    "status": {"short": "NS", "long": "scheduled"},
                },
                "teams": {"home": {"id": None, "name": home}, "away": {"id": None, "name": away}},
                "league": {"id": None, "name": league_name, "code": division_code, "season": None},
                "_veltrix_source": "The Odds API",
                "_supplemental_event_id": str(event_id or ""),
            })
            existing.add(key)
            added += 1

    meta = fixtures_payload.get("_veltrix_meta")
    if not isinstance(meta, dict):
        meta = {}
        fixtures_payload["_veltrix_meta"] = meta
    meta["supplemental_fixture_source"] = "The Odds API"
    meta["supplemental_fixtures_added"] = added
    meta["supplemental_sports_queried"] = queried
    meta["supplemental_sports_failed"] = failed
    meta["fixtures_total_after_supplement"] = len(rows)
    return fixtures_payload



def supplement_fixtures_from_infersports(
    fixtures_payload: dict[str, Any],
    day: str,
    *,
    timezone_name: str = "Africa/Lagos",
    client: InferSportsClient | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Add scheduled future same-day fixtures from InferSports without fetching odds.

    This is fixture discovery only. Primary rows win duplicates, and competition
    eligibility/history thresholds remain the responsibility of the report builder.
    """
    infer_client = client or InferSportsClient()
    zone = ZoneInfo(timezone_name)
    target_day = date.fromisoformat(day)
    current = now or datetime.now(zone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=zone)
    current = current.astimezone(zone)
    rows = fixtures_payload.get("response")
    if not isinstance(rows, list):
        rows = []
        fixtures_payload["response"] = rows

    def team_name(value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("name") or value.get("display_name") or value.get("short_name")
        return str(value or "").strip()

    def local_key(home: Any, away: Any) -> tuple[str, str, str]:
        return (target_day.isoformat(), _name_key(home), _name_key(away))

    existing: set[tuple[str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        teams = row.get("teams") or {}
        home = team_name(teams.get("home"))
        away = team_name(teams.get("away"))
        raw = (row.get("fixture") or {}).get("date")
        if not home or not away or not isinstance(raw, str):
            continue
        try:
            kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=zone)
            if kickoff.astimezone(zone).date() == target_day:
                existing.add(local_key(home, away))
        except (ValueError, OverflowError):
            continue

    events_received = 0
    future_same_day = 0
    duplicates = 0
    added = 0
    status = "AVAILABLE"
    error_type = None
    try:
        events = infer_client.events_for_date(target_day.isoformat(), timezone_name)
        events_received = len(events)
    except (ProviderAPIError, OSError, TimeoutError, ValueError) as exc:
        events = []
        status = "FAILED"
        error_type = type(exc).__name__

    for event in events:
        home = team_name(event.get("home_team") or event.get("home"))
        away = team_name(event.get("away_team") or event.get("away"))
        raw = event.get("scheduled_at") or event.get("kickoff") or event.get("commence_time") or event.get("date")
        if not home or not away or not isinstance(raw, str):
            continue
        try:
            kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            local = kickoff.astimezone(zone)
        except (ValueError, OverflowError):
            continue
        if local.date() != target_day or local <= current:
            continue
        future_same_day += 1
        key = local_key(home, away)
        if key in existing:
            duplicates += 1
            continue

        competition = event.get("competition") or event.get("league") or {}
        if isinstance(competition, dict):
            league_name = str(competition.get("name") or competition.get("display_name") or "").strip()
            league_id = competition.get("id")
        else:
            league_name = str(event.get("competition_name") or event.get("league_name") or competition or "").strip()
            league_id = event.get("competition_id") or event.get("league_id")
        league_name = league_name or "Unknown Competition"
        event_id = event.get("id")
        rows.append({
            "fixture": {
                "id": str(event_id) if event_id is not None else None,
                "date": kickoff.isoformat(),
                "timestamp": int(kickoff.timestamp()),
                "status": {"short": "NS", "long": "scheduled"},
            },
            "teams": {
                "home": {"id": None, "name": home},
                "away": {"id": None, "name": away},
            },
            "league": {
                "id": league_id, "name": league_name,
                "code": LEAGUE_CODES.get(league_name.casefold()), "season": None,
            },
            "_veltrix_source": "InferSports",
            "_supplemental_event_id": str(event_id or ""),
        })
        existing.add(key)
        added += 1

    meta = fixtures_payload.get("_veltrix_meta")
    if not isinstance(meta, dict):
        meta = {}
        fixtures_payload["_veltrix_meta"] = meta
    meta["infersports_fixture_discovery"] = {
        "status": status,
        "events_received": events_received,
        "future_same_day_events": future_same_day,
        "duplicates_skipped": duplicates,
        "fixtures_added": added,
        "error_type": error_type,
    }
    meta["fixtures_total_after_supplement"] = len(rows)
    return fixtures_payload


def enrich_report_with_multi_source_odds(
    report: dict[str, Any],
    fixtures_payload: dict[str, Any],
    *,
    timezone_name: str = "Africa/Lagos",
    five_dollar_client: FiveDollarFootballClient | None = None,
    odds_api_client: TheOddsAPIClient | None = None,
    infer_sports_client: InferSportsClient | None = None,
    enable_infersports: bool | None = None,
    max_fivedollar_fixtures: int = 15,
    max_odds_api_sports: int = 5,
    max_btts_events: int = 3,
) -> dict[str, Any]:
    """Attach genuine BTTS/O-U prices from both providers without changing forecasts.

    FiveDollar calls are capped per run to stay within the free tier's hourly quota.
    The Odds API calls are bounded to five major soccer leagues (two featured markets
    per league) plus at most three event-specific BTTS requests to limit monthly credits.
    """
    predictions = report.get("predictions")
    source_fixtures = fixtures_payload.get("response")
    if not isinstance(predictions, list) or not isinstance(source_fixtures, list):
        return report
    if not predictions or not source_fixtures:
        report["multi_source_odds_sync"] = {
            "five_dollar": {"status": "SKIPPED_NO_FUTURE_FIXTURES", "fixtures_with_market_odds": 0, "max_fixture_odds_calls": max_fivedollar_fixtures, "warning": None},
            "the_odds_api": {"status": "SKIPPED_NO_FUTURE_FIXTURES", "fixtures_with_market_odds": 0, "sports_queried": [], "max_btts_event_calls": max_btts_events, "quota": {}, "warning": None},
            "infer_sports": {"status": "SKIPPED_NO_FUTURE_FIXTURES", "fixtures_with_market_odds": 0, "events_checked": 0, "max_event_odds_calls": 3, "warning": None},
            "note": "No report fixtures available for odds matching; no supplemental odds requests were made.",
        }
        return report
    zone = ZoneInfo(timezone_name)
    by_key: dict[tuple[str, str, str], dict[str, Any] | None] = {}
    for item in source_fixtures:
        if not isinstance(item, dict):
            continue
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        raw_date = fixture.get("date")
        if not isinstance(raw_date, str) or not home or not away:
            continue
        try:
            kickoff = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=zone)
            day = kickoff.astimezone(zone).date().isoformat()
        except (ValueError, OverflowError):
            continue
        key = (day, _name_key(home), _name_key(away))
        # Duplicate same-team fixtures on one local date are ambiguous without a
        # stronger competition/kickoff match; quarantine instead of overwriting.
        if key in by_key:
            by_key[key] = None
        else:
            by_key[key] = item

    pred_by_key: dict[tuple[str, str, str], dict[str, Any] | None] = {}
    for prediction in predictions:
        if not isinstance(prediction, dict):
            continue
        raw = prediction.get("kickoff_local") or prediction.get("kickoff")
        if not isinstance(raw, str):
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=zone)
            day = dt.astimezone(zone).date().isoformat()
        except (ValueError, OverflowError):
            continue
        key = (day, _name_key(prediction.get("home_team")), _name_key(prediction.get("away_team")))
        if key[1] and key[2]:
            if key in pred_by_key:
                pred_by_key[key] = None
            else:
                pred_by_key[key] = prediction

    # Attach source-local fixture identity only after a strict team/date join.
    # Never assume that fixture IDs are interchangeable across providers.
    for key, item in by_key.items():
        prediction = pred_by_key.get(key)
        if item is not None and prediction is not None:
            fixture = item.get("fixture") or {}
            prediction["fixture_source"] = str(item.get("_veltrix_source") or "5DollarFootballAPI")
            prediction["source_fixture_id"] = fixture.get("id")

    fivedollar_status = "NOT_CONFIGURED"
    fivedollar_attached = 0
    fivedollar_error = None
    fivedollar = five_dollar_client or FiveDollarFootballClient()
    if fivedollar.api_key:
        fivedollar_status = "NO_MATCHED_MARKET_ODDS"
        upcoming = []
        for key, item in by_key.items():
            prediction = pred_by_key.get(key)
            if item is None or prediction is None:
                continue
            if str(item.get("_veltrix_source") or "5DollarFootballAPI") != "5DollarFootballAPI":
                continue
            short = str(((item.get("fixture") or {}).get("status") or {}).get("short") or "")
            if short != "NS":
                continue
            upcoming.append((key, item, prediction))
        for key, item, prediction in upcoming[:max_fivedollar_fixtures]:
            fixture_id = (item.get("fixture") or {}).get("id")
            if fixture_id is None:
                continue
            try:
                odds_data = fivedollar.fixture_odds(fixture_id).get("data") or {}
                bookmaker_rows = odds_data.get("bookmakers") or []
                normalized_books = []
                for book in bookmaker_rows:
                    if not isinstance(book, dict):
                        continue
                    odds = book.get("odds") or {}
                    btts = odds.get("btts") or {}
                    btts_prices = btts.get("closing") or btts.get("opening") or {}
                    goal = odds.get("goal_line") or {}
                    goal_prices = goal.get("closing") or goal.get("opening") or {}
                    fixed = odds.get("goal_line_fixed") or []
                    fixed_25 = next((line for line in fixed if isinstance(line, dict) and str(line.get("line")) in {"2.5", "2.50"}), None) if isinstance(fixed, list) else None
                    fixed_prices = ((fixed_25 or {}).get("closing") or (fixed_25 or {}).get("opening") or {})
                    one_x_two = odds.get("1x2") or {}
                    one_x_two_prices = one_x_two.get("closing") or one_x_two.get("opening") or {}
                    normalized_books.append({
                        "bookmaker": str(book.get("name") or book.get("slug") or "unknown"),
                        "btts": {"yes": _valid_price(btts_prices.get("yes")), "no": _valid_price(btts_prices.get("no"))},
                        "over_under": {
                            "line": (fixed_25 or {}).get("line", goal_prices.get("line")),
                            "over": _valid_price(fixed_prices.get("over") if fixed_25 else goal_prices.get("over")),
                            "under": _valid_price(fixed_prices.get("under") if fixed_25 else goal_prices.get("under")),
                        },
                        "1x2": {
                            "home": _valid_price(one_x_two_prices.get("home")),
                            "draw": _valid_price(one_x_two_prices.get("draw")),
                            "away": _valid_price(one_x_two_prices.get("away")),
                        },
                    })
                if any(any(price is not None for price in (book["btts"]["yes"], book["btts"]["no"], book["over_under"]["over"], book["over_under"]["under"])) for book in normalized_books):
                    prediction["five_dollar_market_odds"] = {
                        "provider": "5DollarFootballAPI", "fixture_id": str(fixture_id),
                        "bookmakers": normalized_books, "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                    fivedollar_attached += 1
            except (ProviderAPIError, TypeError, ValueError, KeyError):
                # One missing odds board must not block the daily report.
                continue
        fivedollar_status = "AVAILABLE" if fivedollar_attached else "NO_MATCHED_MARKET_ODDS"

    odds_api_status = "NOT_CONFIGURED"
    odds_api_attached = 0
    odds_api_error = None
    odds_client = odds_api_client or TheOddsAPIClient()
    if odds_client.api_key:
        odds_api_status = "NO_MATCHED_MARKET_ODDS"
        configured = os.getenv("THE_ODDS_API_SOCCER_SPORTS", "").strip()
        if configured:
            sports = [key.strip() for key in configured.split(",") if key.strip()][:max_odds_api_sports]
        else:
            # Query only competitions represented in the current report to protect monthly quota.
            aliases = {
                "soccer_epl": ("premierleague", "englishpremierleague", "epl"),
                "soccer_spain_la_liga": ("laliga", "spanishprimera", "spainlaliga"),
                "soccer_germany_bundesliga": ("bundesliga", "germanbundesliga"),
                "soccer_italy_serie_a": ("seriea", "italianseriea"),
                "soccer_france_ligue_one": ("ligue1", "frenchligue1"),
            }
            league_keys = {_name_key(p.get("league")) for p in predictions if isinstance(p, dict) and p.get("league")}
            sports = [sport for sport, names in aliases.items() if any(any(name in league_key or league_key in name for name in names) for league_key in league_keys if league_key)][:max_odds_api_sports]
        odds_events: list[tuple[str, dict[str, Any]]] = []
        for sport_key in sports:
            try:
                for event in odds_client.odds_for_sport(sport_key, regions="uk", markets="h2h,totals"):
                    odds_events.append((sport_key, event))
            except ProviderAPIError:
                continue
        attached_keys: set[tuple[str, str, str]] = set()
        for sport_key, event in odds_events:
            key = (_event_local_date(event, timezone_name) or "", _name_key(event.get("home_team")), _name_key(event.get("away_team")))
            prediction = pred_by_key.get(key)
            if prediction is None or not key[0] or not key[1] or not key[2]:
                continue
            summary = _event_market_summary(event)
            if not any(summary.values()):
                continue
            prediction["the_odds_api_market_odds"] = {
                "provider": "The Odds API", "sport_key": sport_key, "event_id": str(event.get("id") or ""),
                "commence_time": event.get("commence_time"), "markets": summary,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            attached_keys.add(key)
            odds_api_attached += 1

        # BTTS is an event-specific additional market in The Odds API. Cap requests
        # to protect the 500-credit monthly allowance observed during the smoke check.
        btts_attempts = 0
        for sport_key, event in odds_events:
            if btts_attempts >= max_btts_events:
                break
            key = (_event_local_date(event, timezone_name) or "", _name_key(event.get("home_team")), _name_key(event.get("away_team")))
            prediction = pred_by_key.get(key)
            if prediction is None or not key[0] or not key[1] or not key[2]:
                continue
            current = prediction.get("the_odds_api_market_odds")
            if isinstance(current, dict) and current.get("markets", {}).get("btts"):
                continue
            event_id = str(event.get("id") or "")
            if not event_id:
                continue
            btts_attempts += 1
            try:
                btts_events = odds_client.event_btts(sport_key, event_id, regions="uk")
            except ProviderAPIError:
                continue
            for btts_event in btts_events:
                summary = _event_market_summary(btts_event)
                if not summary.get("btts"):
                    continue
                if not isinstance(current, dict):
                    current = {
                        "provider": "The Odds API", "sport_key": sport_key, "event_id": event_id,
                        "commence_time": event.get("commence_time"), "markets": {"h2h": [], "totals": [], "btts": []},
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                    prediction["the_odds_api_market_odds"] = current
                current["markets"]["btts"] = summary["btts"]
                if key not in attached_keys:
                    attached_keys.add(key)
                    odds_api_attached += 1
                break
        odds_api_status = "AVAILABLE" if odds_api_attached else "NO_MATCHED_MARKET_ODDS"

    infer_status = "DISABLED"
    infer_attached = 0
    infer_events_checked = 0
    infer_error = None
    infer_enabled = (
        enable_infersports if enable_infersports is not None
        else os.getenv("VELTRIX_ENABLE_INFERSports", "false").strip().casefold() in {"1", "true", "yes"}
    )
    infer_client = infer_sports_client or InferSportsClient()
    if infer_enabled:
        infer_status = "NO_MATCHED_MARKET_ODDS"
        try:
            infer_events = infer_client.events_for_date(str(report.get("as_of_date") or ""), timezone_name)
            infer_events_checked = len(infer_events)
            seen_event_keys: set[tuple[str, str, str]] = set()
            matched_events = []
            for event in infer_events:
                home_obj = event.get("home_team") or {}
                away_obj = event.get("away_team") or {}
                home_name = home_obj.get("name") if isinstance(home_obj, dict) else str(home_obj)
                away_name = away_obj.get("name") if isinstance(away_obj, dict) else str(away_obj)
                scheduled = event.get("scheduled_at")
                event_day = _event_local_date({"commence_time": scheduled}, timezone_name) if scheduled else str(report.get("as_of_date") or "")
                key = (event_day or "", _name_key(home_name), _name_key(away_name))
                if not key[0] or not key[1] or not key[2] or key in seen_event_keys:
                    continue
                seen_event_keys.add(key)
                prediction = pred_by_key.get(key)
                if prediction is not None:
                    matched_events.append((key, event, prediction, str(home_name), str(away_name)))
            for key, event, prediction, home_name, away_name in matched_events[:3]:
                event_id = str(event.get("id") or "")
                if not event_id:
                    continue
                try:
                    odds_block = infer_client.event_odds(event_id)
                except ProviderAPIError:
                    continue
                if odds_block.get("stale") is True:
                    continue
                normalized = {"h2h": [], "totals": [], "btts": []}
                for quote in odds_block.get("odds") or []:
                    if not isinstance(quote, dict) or str(quote.get("period") or "").casefold() != "full_time":
                        continue
                    status_text = str(quote.get("status") or "").casefold()
                    if any(token in status_text for token in ("suspend", "closed", "stale", "unavailable")):
                        continue
                    market_type = str(quote.get("market_type") or "").casefold()
                    prices = quote.get("prices") or {}
                    bookmaker = str(quote.get("bookmaker") or "bookmaker")
                    as_of = quote.get("as_of") or odds_block.get("as_of")
                    if market_type == "totals":
                        over, under = _valid_price(prices.get("over")), _valid_price(prices.get("under"))
                        if over is not None and under is not None:
                            normalized["totals"].append({
                                "bookmaker": bookmaker, "last_update": as_of,
                                "outcomes": [
                                    {"name": "Over", "price": over, "point": quote.get("line")},
                                    {"name": "Under", "price": under, "point": quote.get("line")},
                                ],
                            })
                    elif market_type == "1x2":
                        home_price, draw_price, away_price = (
                            _valid_price(prices.get("home")), _valid_price(prices.get("draw")), _valid_price(prices.get("away"))
                        )
                        if home_price is not None and draw_price is not None and away_price is not None:
                            normalized["h2h"].append({
                                "bookmaker": bookmaker, "last_update": as_of,
                                "outcomes": [
                                    {"name": home_name, "price": home_price},
                                    {"name": "Draw", "price": draw_price},
                                    {"name": away_name, "price": away_price},
                                ],
                            })
                if normalized["totals"] or normalized["h2h"]:
                    prediction["infer_sports_market_odds"] = {
                        "provider": "InferSports", "event_id": event_id,
                        "scheduled_at": event.get("scheduled_at"),
                        "as_of": odds_block.get("as_of"), "stale": False,
                        "markets": normalized, "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                    infer_attached += 1
            infer_status = "AVAILABLE" if infer_attached else "NO_MATCHED_MARKET_ODDS"
        except ProviderAPIError as exc:
            infer_status = "UNAVAILABLE"
            infer_error = str(exc)[:160]

    report["multi_source_odds_sync"] = {
        "five_dollar": {
            "status": fivedollar_status, "fixtures_with_market_odds": fivedollar_attached,
            "max_fixture_odds_calls": max_fivedollar_fixtures, "warning": fivedollar_error,
        },
        "the_odds_api": {
            "status": odds_api_status, "fixtures_with_market_odds": odds_api_attached,
            "sports_queried": sports if odds_client.api_key else [],
            "max_btts_event_calls": max_btts_events,
            "quota": dict(odds_client.last_quota) if odds_client.api_key else {},
            "warning": odds_api_error,
        },
        "infer_sports": {
            "status": infer_status, "fixtures_with_market_odds": infer_attached,
            "events_checked": infer_events_checked, "max_event_odds_calls": 3,
            "warning": infer_error,
        },
        "note": "Market prices are reference data only; model probabilities remain unchanged and unvalidated for betting.",
    }
    return report
