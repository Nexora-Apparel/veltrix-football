"""API-Football (API-Sports v3) adapter for live account and prematch-odds checks.

This is distinct from Highlightly and from APIFootball.com. It reads
API_FOOTBALL_KEY and sends it only in the x-apisports-key request header.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests


class APIFootballError(RuntimeError):
    """Sanitized provider/configuration error; never includes the API key."""


class APIFootballClient:
    base_url = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str | None = None, timeout: int = 15, session: Any = None):
        self.api_key = (api_key if api_key is not None else os.getenv("API_FOOTBALL_KEY", "")).strip()
        self.timeout = timeout
        self.session = session or requests.Session()
        if self.api_key:
            self.session.headers.update({
                "x-apisports-key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "VeltrixFootball/1.0",
            })

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise APIFootballError("API_FOOTBALL_KEY is not configured in the deployment environment.")
        try:
            response = self.session.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=params or {},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise APIFootballError(f"API-Football network error: {exc.__class__.__name__}.") from None
        try:
            payload = response.json()
        except ValueError:
            raise APIFootballError(f"API-Football returned non-JSON data (HTTP {response.status_code}).") from None

        if response.status_code >= 400:
            if response.status_code in (401, 403):
                reason = "API key rejected or account/subscription does not permit this request."
            elif response.status_code == 429:
                reason = "API-Football request quota or rate limit reached."
            else:
                reason = f"HTTP {response.status_code}."
            raise APIFootballError(f"API-Football request failed: {reason}")
        if not isinstance(payload, dict):
            raise APIFootballError("API-Football response had an unexpected JSON shape.")

        errors = payload.get("errors")
        if errors:
            # Provider errors can include arbitrary text; do not echo it or any request URL.
            if isinstance(errors, dict):
                keys = ", ".join(str(key) for key in list(errors)[:5])
                detail = f"Provider reported an error in: {keys or 'request parameters'}."
            elif isinstance(errors, list):
                detail = "Provider rejected the request parameters or account access."
            else:
                detail = "Provider rejected the request."
            raise APIFootballError(detail)
        payload["_veltrix_meta"] = {
            "provider": "API-Football (API-Sports)",
            "http_status": response.status_code,
            "requests_limit": response.headers.get("x-ratelimit-requests-limit"),
            "requests_remaining": response.headers.get("x-ratelimit-requests-remaining"),
        }
        return payload

    def status(self) -> dict[str, Any]:
        """Check key/account/subscription using the provider's quota-exempt status endpoint."""
        payload = self._get("status")
        response = payload.get("response")
        if not isinstance(response, dict):
            raise APIFootballError("API-Football status response is missing account/subscription details.")
        subscription = response.get("subscription") or {}
        account = response.get("account") or {}
        requests_info = response.get("requests") or {}
        return {
            "provider": "API-Football (API-Sports)",
            "authenticated": True,
            "account": {
                "name_available": bool(account.get("firstname") or account.get("name")),
                "email_available": bool(account.get("email")),
            },
            "subscription": {
                "active": subscription.get("active"),
                "plan": subscription.get("plan"),
                "end": subscription.get("end"),
            },
            "requests": {
                "current": requests_info.get("current"),
                "daily_limit": requests_info.get("limit_day"),
            },
            "_veltrix_meta": payload.get("_veltrix_meta", {}),
        }

    def odds_for_date(self, day: str, *, timezone: str = "Africa/Lagos", page: int = 1) -> dict[str, Any]:
        """Fetch one page of pre-match odds for a date; no odds are invented.

        API-Football exposes 10 odds records per page. Availability depends on
        fixture timing, league coverage, bookmaker, and subscription. Odds are
        normally published 1–14 days before a fixture and historical retention
        is limited, so an empty response is not by itself an authentication failure.
        """
        try:
            parsed_day = date.fromisoformat(day)
        except (TypeError, ValueError):
            raise APIFootballError("Date must use YYYY-MM-DD format.") from None
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise APIFootballError("Page must be a positive integer.")
        payload = self._get("odds", {"date": parsed_day.isoformat(), "timezone": timezone, "page": page})
        rows = payload.get("response")
        if not isinstance(rows, list):
            raise APIFootballError("API-Football odds response is missing its response list.")
        return {
            "provider": "API-Football (API-Sports)",
            "date": parsed_day.isoformat(),
            "timezone": timezone,
            "results": len(rows),
            "paging": payload.get("paging") or {},
            "response": rows,
            "_veltrix_meta": payload.get("_veltrix_meta", {}),
        }
