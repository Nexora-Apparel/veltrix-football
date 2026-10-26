"""APIFootball.com bookmaker odds adapter (separate from API-Sports)."""
from __future__ import annotations

import math
import os
from datetime import date
from typing import Any

import requests


class BookmakerOddsError(RuntimeError):
    """Safe provider/configuration error; never includes the secret API key."""


_MARKETS = {
    "1x2": {"home": ("odd_1", "1"), "draw": ("odd_x", "x"), "away": ("odd_2", "2")},
    "btts": {"yes": ("bts_yes", "btts_yes", "odd_bts_yes"), "no": ("bts_no", "btts_no", "odd_bts_no")},
    "over_under": {
        "over_0_5": ("o+0.5", "over_0.5", "odd_over_0.5"),
        "under_0_5": ("u+0.5", "under_0.5", "odd_under_0.5"),
        "over_1_5": ("o+1.5", "over_1.5", "odd_over_1.5"),
        "under_1_5": ("u+1.5", "under_1.5", "odd_under_1.5"),
        "over_2_5": ("o+2.5", "over_2.5", "odd_over_2.5"),
        "under_2_5": ("u+2.5", "under_2.5", "odd_under_2.5"),
        "over_3_5": ("o+3.5", "over_3.5", "odd_over_3.5"),
        "under_3_5": ("u+3.5", "under_3.5", "odd_under_3.5"),
        "over_4_5": ("o+4.5", "over_4.5", "odd_over_4.5"),
        "under_4_5": ("u+4.5", "under_4.5", "odd_under_4.5"),
    },
}


def _decimal(value: Any) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and 1.0 < result < 1000.0 else None


def _first_price(row: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    for name in aliases:
        price = _decimal(row.get(name))
        if price is not None:
            return price
    return None


def normalize_odds_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize provider rows while preserving each bookmaker's prices."""
    if isinstance(payload, dict):
        if payload.get("error"):
            # APIfootball often reports auth/plan/coverage failures in a HTTP-200
            # JSON body. Map known messages to safe actionable diagnostics; do not
            # echo arbitrary provider text or anything that could contain secrets.
            provider_error = str(payload.get("error", "")).strip().casefold()
            if "authentification failed" in provider_error or "authentication failed" in provider_error:
                reason = "API key rejected by APIFootball.com. Check that APIFOOTBALL_API_KEY is the correct APIfootball.com key."
            elif "no odd found" in provider_error or "no odds found" in provider_error or "no data" in provider_error:
                reason = "No odds available for this date, or odds are not enabled on this APIfootball.com plan. Check plan coverage and odds entitlement."
            elif any(term in provider_error for term in ("invalid api", "invalid key", "wrong api", "api key", "apikey")):
                reason = "APIFootball.com rejected the API key. Confirm the key belongs to APIfootball.com (not API-Football/API-Sports) and that it is active."
            elif any(term in provider_error for term in ("limit", "quota", "too many", "rate")):
                reason = "APIFootball.com reports a quota or rate limit. Check the account usage limits and retry after they reset."
            elif provider_error in {"404", "http 404", "not found", "404 not found"}:
                reason = "APIFootball.com returned its generic 404 error for get_odds. The key was accepted far enough to reach the provider, but the response does not identify whether the endpoint/action or account access is responsible. Next diagnostic: test get_countries with the same key, then get_odds for a date and supported competition."
            elif any(term in provider_error for term in ("upgrade", "subscription", "plan", "permission", "not allowed", "access denied")):
                reason = "APIFootball.com reports an access or subscription restriction for odds. Confirm get_odds is included in the current plan."
            else:
                # Return a short, sanitized provider diagnostic so the next Telegram
                # reply can identify the actual failure without leaking credentials.
                import re
                diagnostic = str(payload.get("error", "")).strip()
                diagnostic = re.sub(r"(?i)(apikey|api_key|api key|token|secret)(\s*[=:]\s*)[^\s&,;]+", r"\1\2[REDACTED]", diagnostic)
                diagnostic = re.sub(r"https?://\S+", "[URL REDACTED]", diagnostic)
                diagnostic = re.sub(r"[^\w .,:;()/'-]", " ", diagnostic)
                diagnostic = " ".join(diagnostic.split())[:140]
                reason = "APIFootball.com provider message: " + (diagnostic or "unrecognized error; message was empty.")
            raise BookmakerOddsError(reason)
        rows = payload.get("data", payload.get("response", []))
    else:
        rows = payload
    if not isinstance(rows, list):
        raise BookmakerOddsError("APIFootball.com odds response has an unexpected shape.")

    normalized: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        match_id = str(raw.get("match_id") or raw.get("fixture_id") or "").strip()
        home = str(raw.get("match_hometeam_name") or raw.get("home_team") or "").strip()
        away = str(raw.get("match_awayteam_name") or raw.get("away_team") or "").strip()
        match_date = str(raw.get("match_date") or raw.get("date") or "").strip()
        match_time = str(raw.get("match_time") or raw.get("time") or "").strip()
        bookmaker = str(raw.get("odd_bookmakers") or raw.get("bookmaker") or "Unknown bookmaker").strip()
        prices: dict[str, float] = {}
        for market in _MARKETS.values():
            for name, aliases in market.items():
                price = _first_price(raw, aliases)
                if price is not None:
                    prices[name] = price
        # Require fixture identity; don't publish anonymous prices.
        if not (match_id and home and away and match_date):
            continue
        normalized.append({
            "provider": "APIFootball.com",
            "match_id": match_id,
            "home_team": home,
            "away_team": away,
            "date": match_date,
            "time": match_time,
            "bookmaker": bookmaker,
            "odd_date": str(raw.get("odd_date") or raw.get("updated_at") or "").strip() or None,
            "odds": prices,
        })
    return normalized


class APIFootballOddsClient:
    """Small date-scoped client. Never logs or returns the key-bearing request URL."""

    base_url = "https://apiv3.apifootball.com/"

    def __init__(self, api_key: str | None = None, timeout: int = 15, session: Any = None):
        self.api_key = (api_key if api_key is not None else os.getenv("APIFOOTBALL_API_KEY", "")).strip()
        self.timeout = timeout
        self.session = session or requests.Session()

    def odds_for_date(self, day: str) -> dict[str, Any]:
        if not self.api_key:
            raise BookmakerOddsError("APIFOOTBALL_API_KEY is not configured.")
        try:
            parsed_day = date.fromisoformat(day)
        except (TypeError, ValueError):
            raise BookmakerOddsError("Date must use YYYY-MM-DD format.") from None
        try:
            response = self.session.get(
                self.base_url,
                params={"action": "get_odds", "from": parsed_day.isoformat(),
                        "to": parsed_day.isoformat(), "APIkey": self.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise BookmakerOddsError(f"APIFootball.com network error: {exc.__class__.__name__}.") from None
        try:
            payload = response.json()
        except ValueError:
            raise BookmakerOddsError(f"APIFootball.com returned non-JSON data (HTTP {response.status_code}).") from None
        if response.status_code >= 400:
            if response.status_code in (401, 403):
                reason = "API key rejected or subscription does not permit this request."
            elif response.status_code == 429:
                reason = "provider quota or rate limit reached."
            else:
                reason = f"HTTP {response.status_code}."
            raise BookmakerOddsError(f"APIFootball.com request failed: {reason}")
        rows = normalize_odds_rows(payload)
        return {
            "response": rows,
            "results": len(rows),
            "_veltrix_meta": {
                "provider": "APIFootball.com",
                "status": "AVAILABLE" if rows else "NO_ODDS_RETURNED",
                "date": parsed_day.isoformat(),
                "markets_supported": ["1X2", "BTTS", "Over/Under 0.5–4.5"],
            },
        }
