"""football-data.org v4 client with a compatibility shape for Veltrix's model."""
from __future__ import annotations

from datetime import date as date_type, timedelta
from typing import Any

import requests

from app.config import Settings


class FootballAPIError(RuntimeError):
    pass


_STATUS_MAP = {
    "SCHEDULED": "NS",
    "TIMED": "TBD",
    "IN_PLAY": "LIVE",
    "LIVE": "LIVE",
    "PAUSED": "LIVE",
    "FINISHED": "FT",
    "AWARDED": "FT",
    "POSTPONED": "PST",
    "CANCELLED": "CANC",
    "SUSPENDED": "SUSP",
}


def normalize_match(match: dict[str, Any]) -> dict[str, Any]:
    """Translate a football-data.org match into the internal fixture shape."""
    competition = match.get("competition") or {}
    home = match.get("homeTeam") or {}
    away = match.get("awayTeam") or {}
    score = match.get("score") or {}
    full_time = score.get("fullTime") or {}
    status = str(match.get("status") or "").upper()
    return {
        "fixture": {
            "id": match.get("id"),
            "date": match.get("utcDate"),
            "status": {"short": _STATUS_MAP.get(status, status)},
        },
        "teams": {
            "home": {"id": home.get("id"), "name": home.get("name")},
            "away": {"id": away.get("id"), "name": away.get("name")},
        },
        "league": {
            "id": competition.get("id"),
            "name": competition.get("name"),
            "code": competition.get("code"),
        },
        "goals": {"home": full_time.get("home"), "away": full_time.get("away")},
        "_football_data_status": status,
    }


class FootballAPI:
    """Small football-data.org v4 client; never returns invented odds."""

    def __init__(self, settings: Settings, timeout: int = 20):
        self.settings = settings
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "X-Auth-Token": settings.api_key,
            "Accept": "application/json",
            "User-Agent": "VeltrixFootball/0.2",
        })

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.settings.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=params or {}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FootballAPIError(
                f"football-data.org network request failed: {exc.__class__.__name__}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise FootballAPIError(
                f"football-data.org returned non-JSON content (HTTP {response.status_code})."
            ) from exc
        if response.status_code >= 400:
            message = payload.get("message", payload.get("error", "no details")) if isinstance(payload, dict) else "unexpected response"
            raise FootballAPIError(
                f"football-data.org request failed with HTTP {response.status_code}: {message}"
            )
        if not isinstance(payload, dict):
            raise FootballAPIError("football-data.org response had an unexpected JSON shape.")
        payload["_veltrix_meta"] = {
            "provider": "football-data.org",
            "http_status": response.status_code,
            "requests_remaining": response.headers.get("X-Requests-Available-Minute"),
            "request_counter_reset": response.headers.get("X-RequestCounter-Reset"),
        }
        return payload

    def _matches(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = self.get("matches", params)
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise FootballAPIError("football-data.org payload is missing its matches list.")
        return {
            "response": [normalize_match(match) for match in matches if isinstance(match, dict)],
            "_veltrix_meta": payload.get("_veltrix_meta", {}),
            "provider": "football-data.org",
        }

    def status(self) -> dict[str, Any]:
        return self.get("competitions")

    def fixtures(self, date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        """Fetch all matches visible to the account for a single UTC-date window."""
        next_day = (date_type.fromisoformat(date) + timedelta(days=1)).isoformat()
        return self._matches({"dateFrom": date, "dateTo": next_day})

    def fixtures_between(self, start_date: str, end_date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        """Fetch an inclusive date range (football-data.org dateTo is exclusive)."""
        next_day = (date_type.fromisoformat(end_date) + timedelta(days=1)).isoformat()
        return self._matches({"dateFrom": start_date, "dateTo": next_day})

    def odds_for_date(self, date: str, timezone: str = "Africa/Lagos") -> dict[str, Any]:
        """Odds are not supplied by this adapter; return an honest empty dataset."""
        return {
            "response": [],
            "_veltrix_meta": {
                "provider": "football-data.org",
                "odds_status": "UNAVAILABLE",
                "reason": "The football-data.org integration does not provide bookmaker odds.",
            },
        }

    def leagues(self, current: bool = True) -> dict[str, Any]:
        return self.get("competitions")
