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
    "brasileirao": "BSA", "brazil serie a": "BSA",
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
        cursor = start
        while cursor <= end:
            day_text = cursor.isoformat()
            try:
                payload = self.fixtures(day_text, timezone)
                rows.extend(payload["response"])
                meta = payload.get("_veltrix_meta") or {}
                requests_made += int(meta.get("requests_made", 1) or 1)
                remaining = meta.get("requests_remaining", remaining)
                successful_dates.append(day_text)
            except ProviderAPIError:
                # Keep successful dates from this window instead of discarding them
                # when one date is inaccessible. Failed dates remain retryable.
                requests_made += 1
                failed_dates.append(day_text)
            cursor += timedelta(days=1)
        return {
            "response": rows, "results": len(rows), "provider": "5DollarFootballAPI",
            "_veltrix_meta": {
                "provider": "5DollarFootballAPI", "requests_made": requests_made,
                "requests_remaining": remaining, "successful_dates": successful_dates,
                "failed_dates": failed_dates,
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


def enrich_report_with_multi_source_odds(
    report: dict[str, Any],
    fixtures_payload: dict[str, Any],
    *,
    timezone_name: str = "Africa/Lagos",
    five_dollar_client: FiveDollarFootballClient | None = None,
    odds_api_client: TheOddsAPIClient | None = None,
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
            "note": "No report fixtures available for odds matching; no supplemental odds requests were made.",
        }
        return report
    zone = ZoneInfo(timezone_name)
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
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
        by_key[(day, _name_key(home), _name_key(away))] = item

    pred_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
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
            pred_by_key[key] = prediction

    # Attach source-local fixture identity only after a strict team/date join.
    # Never assume that fixture IDs are interchangeable across providers.
    for key, item in by_key.items():
        prediction = pred_by_key.get(key)
        if prediction is not None:
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
            if prediction is None:
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
        "note": "Market prices are reference data only; model probabilities remain unchanged and unvalidated for betting.",
    }
    return report
