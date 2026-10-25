"""Highlightly Football API client with Veltrix's stable fixture shape.

Direct Highlightly authentication uses the x-rapidapi-key header. The free plan
does not guarantee bookmaker odds, so this adapter never fabricates them.
"""
from __future__ import annotations

from datetime import date as date_type, timedelta
from typing import Any
import re

import requests

from app.config import Settings


class FootballAPIError(RuntimeError):
    """A safe, user-facing provider or response error."""


_STATUS_MAP = {
    "NOT STARTED": "NS",
    "TO BE ANNOUNCED": "TBD",
    "FIRST HALF": "LIVE",
    "SECOND HALF": "LIVE",
    "HALF TIME": "LIVE",
    "EXTRA TIME": "LIVE",
    "BREAK TIME": "LIVE",
    "PENALTIES": "LIVE",
    "IN PROGRESS": "LIVE",
    "FINISHED": "FT",
    "FINISHED AFTER PENALTIES": "FT",
    "FINISHED AFTER EXTRA TIME": "FT",
    "AWARDED": "FT",
    "POSTPONED": "PST",
    "CANCELLED": "CANC",
    "SUSPENDED": "SUSP",
    "INTERRUPTED": "SUSP",
    "ABANDONED": "ABD",
    "UNKNOWN": "TBD",
}

_LEAGUE_CODES = {
    "PREMIER LEAGUE": "PL",
    "ENGLISH PREMIER LEAGUE": "PL",
    "CHAMPIONSHIP": "ELC",
    "ENGLISH FOOTBALL LEAGUE CHAMPIONSHIP": "ELC",
    "LEAGUE ONE": "EL1",
    "LEAGUE TWO": "EL2",
    "LA LIGA": "PD",
    "LALIGA": "PD",
    "LALIGA EA SPORTS": "PD",
    "SEGUNDA DIVISION": "SD",
    "SERIE A": "SA",
    "SERIE B": "SB",
    "BUNDESLIGA": "BL1",
    "2. BUNDESLIGA": "BL2",
    "LIGUE 1": "FL1",
    "LIGUE 2": "FL2",
    "EREDIVISIE": "DED",
    "PRIMEIRA LIGA": "PPL",
    "LIGA PORTUGAL": "PPL",
    "SCOTTISH PREMIERSHIP": "SPL",
    "SCOTTISH CHAMPIONSHIP": "SC1",
    "BRASILEIRAO": "BSA",
    "BRAZIL SERIE A": "BSA",
}


def _score_pair(value: Any) -> tuple[int | None, int | None]:
    """Parse Highlightly's 'home - away' score without guessing missing scores."""
    if not isinstance(value, str):
        return None, None
    match = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", value)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def normalize_match(match: dict[str, Any]) -> dict[str, Any]:
    """Translate a Highlightly match into the internal fixture shape."""
    league = match.get("league") or {}
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    state = match.get("state") or {}
    score = state.get("score") or {}
    home_goals, away_goals = _score_pair(score.get("current"))
    status_text = str(state.get("description") or "Unknown").strip()
    status_key = status_text.upper()
    league_name = str(league.get("name") or "")
    league_code = _LEAGUE_CODES.get(league_name.strip().upper())
    return {
        "fixture": {
            "id": match.get("id"),
            "date": match.get("date"),
            "status": {"short": _STATUS_MAP.get(status_key, "TBD")},
        },
        "teams": {
            "home": {"id": home.get("id"), "name": home.get("name")},
            "away": {"id": away.get("id"), "name": away.get("name")},
        },
        "league": {
            "id": league.get("id"),
            "name": league_name,
            "code": league_code,
            "season": league.get("season"),
        },
        "goals": {"home": home_goals, "away": away_goals},
        "_highlightly_status": status_text,
    }


class FootballAPI:
    """Small Highlightly client; rate limits and missing odds are explicit."""

    def __init__(self, settings: Settings, timeout: int = 20):
        self.settings = settings
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "x-rapidapi-key": settings.api_key,
            "Accept": "application/json",
            "User-Agent": "VeltrixFootball/1.0",
        })

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.settings.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=params or {}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FootballAPIError(
                f"Highlightly network request failed: {exc.__class__.__name__}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise FootballAPIError(
                f"Highlightly returned non-JSON content (HTTP {response.status_code})."
            ) from exc
        if response.status_code >= 400:
            message = (
                payload.get("message", payload.get("error", "no details"))
                if isinstance(payload, dict) else "unexpected response"
            )
            if response.status_code in (401, 403):
                message = "API key was rejected or the key/header is not valid for this subscription."
            elif response.status_code == 429:
                message = "daily API request quota or rate limit reached."
            raise FootballAPIError(
                f"Highlightly request failed with HTTP {response.status_code}: {message}"
            )
        if not isinstance(payload, dict):
            raise FootballAPIError("Highlightly response had an unexpected JSON shape.")
        payload["_veltrix_meta"] = {
            "provider": "Highlightly",
            "http_status": response.status_code,
            "requests_limit": response.headers.get("x-ratelimit-requests-limit"),
            "requests_remaining": response.headers.get("x-ratelimit-requests-remaining"),
        }
        return payload

    def _matches(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch every page for the filter, without silently truncating fixtures."""
        first = self.get("matches", params)
        page = first.get("data")
        if not isinstance(page, list):
            raise FootballAPIError("Highlightly payload is missing its data list.")
        matches = list(page)
        meta = dict(first.get("_veltrix_meta", {}))
        pagination = dict(first.get("pagination") or {})
        plan = first.get("plan")
        try:
            total_count = int(pagination.get("totalCount", len(matches)))
            limit = int(pagination.get("limit", params.get("limit", 100)))
        except (TypeError, ValueError):
            total_count, limit = len(matches), max(1, len(matches))
        if limit < 1:
            raise FootballAPIError("Highlightly returned an invalid pagination limit.")
        pages_fetched = 1
        offset = int(pagination.get("offset", params.get("offset", 0)) or 0)
        # Defensive cap prevents malformed provider metadata from exhausting quota.
        max_pages = 20
        while len(matches) < total_count and pages_fetched < max_pages:
            next_offset = offset + len(page)
            if next_offset >= total_count:
                break
            next_params = {**params, "limit": limit, "offset": next_offset}
            next_payload = self.get("matches", next_params)
            next_page = next_payload.get("data")
            if not isinstance(next_page, list):
                raise FootballAPIError("Highlightly pagination response is missing its data list.")
            if not next_page:
                raise FootballAPIError(
                    f"Highlightly pagination stopped early ({len(matches)} of {total_count} matches retrieved)."
                )
            matches.extend(next_page)
            page = next_page
            offset = next_offset
            pages_fetched += 1
            meta = dict(next_payload.get("_veltrix_meta", meta))
            plan = next_payload.get("plan", plan)
            next_pagination = next_payload.get("pagination") or {}
            try:
                total_count = int(next_pagination.get("totalCount", total_count))
            except (TypeError, ValueError):
                pass
        complete = len(matches) >= total_count
        if not complete and pages_fetched >= max_pages:
            raise FootballAPIError(
                f"Highlightly returned more than {max_pages * limit} matches for one filter; "
                "refusing to silently publish a truncated fixture list."
            )
        pagination.update({
            "totalCount": total_count,
            "fetchedCount": len(matches),
            "pagesFetched": pages_fetched,
            "complete": complete,
        })
        meta["requests_made"] = pages_fetched
        return {
            "response": [normalize_match(match) for match in matches if isinstance(match, dict)],
            "results": len(matches),
            "pagination": pagination,
            "plan": plan,
            "_veltrix_meta": meta,
            "provider": "Highlightly",
        }

    def status(self) -> dict[str, Any]:
        """Validate API access using a lightweight, supported league query."""
        return self.leagues(current=True)

    def fixtures(self, date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        """Fetch a local-calendar day's fixtures; Highlightly accepts a single date."""
        date_type.fromisoformat(date)  # validate input before making a request
        return self._matches({
            "date": date,
            "timezone": timezone,
            "limit": 100,
            "offset": 0,
        })

    def fixtures_between(
        self, start_date: str, end_date: str, timezone: str = "Africa/Lagos"
    ) -> dict[str, Any]:
        """Fetch an inclusive range using one provider request per calendar date.

        Highlightly's matches endpoint documents a single 'date' filter, not a
        from/to range. Callers should keep ranges small to respect free-tier quotas.
        """
        start = date_type.fromisoformat(start_date)
        end = date_type.fromisoformat(end_date)
        if end < start:
            raise FootballAPIError("end date must be on or after start date.")
        if (end - start).days >= 7:
            raise FootballAPIError(
                "Highlightly range queries are capped at 7 calendar days to protect the free daily quota."
            )
        combined: list[dict[str, Any]] = []
        metas: list[dict[str, Any]] = []
        cursor = start
        while cursor <= end:
            payload = self.fixtures(cursor.isoformat(), timezone)
            combined.extend(payload["response"])
            metas.append(payload.get("_veltrix_meta", {}))
            cursor += timedelta(days=1)
        return {
            "response": combined,
            "results": len(combined),
            "_veltrix_meta": {
                "provider": "Highlightly",
                "requests_made": sum(int(m.get("requests_made", 1) or 1) for m in metas),
                "requests_remaining": next(
                    (m.get("requests_remaining") for m in reversed(metas)
                     if m.get("requests_remaining") is not None), None
                ),
            },
            "provider": "Highlightly",
        }

    def odds_for_date(self, date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        """Do not spend quota or imply odds exist on a plan that may not expose them."""
        return {
            "response": [],
            "_veltrix_meta": {
                "provider": "Highlightly",
                "odds_status": "UNAVAILABLE",
                "reason": "Bookmaker odds are not available on the Highlightly free/basic plan.",
            },
        }

    def leagues(self, current: bool = True) -> dict[str, Any]:
        # Highlightly requires a primary filter; limit alone is not sufficient.
        # The provider exposes seasons explicitly, so avoid pretending this is an
        # unfiltered all-seasons catalogue.
        year = date_type.today().year
        params: dict[str, Any] = {"season": year if current else year - 1, "limit": 100}
        payload = self.get("leagues", params)
        leagues = payload.get("data")
        if not isinstance(leagues, list):
            raise FootballAPIError("Highlightly leagues payload is missing its data list.")
        return {
            "response": leagues,
            "results": len(leagues),
            "pagination": payload.get("pagination"),
            "plan": payload.get("plan"),
            "_veltrix_meta": payload.get("_veltrix_meta", {}),
            "provider": "Highlightly",
        }
