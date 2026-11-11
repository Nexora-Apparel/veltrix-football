"""Credential-safe smoke checks for the 5DollarFootballAPI and The Odds API.

Only prints provider status, market availability, and quota headers; never prints keys or request URLs.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

TIMEOUT = 20


class ProviderCheckError(RuntimeError):
    pass


def request_json(url: str, headers: dict[str, str] | None = None):
    req = Request(url, headers={"Accept": "application/json", **(headers or {})})
    try:
        with urlopen(req, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8")
            return response.status, response.headers, json.loads(body)
    except HTTPError as exc:
        # Do not print the URL or raw body; expose only safe quota metadata.
        headers = exc.headers or {}
        details = [f"HTTP {exc.code}"]
        for source, label in (
            ("Retry-After", "retry_after"),
            ("X-RateLimit-Remaining", "remaining"),
            ("X-RateLimit-Reset", "reset"),
        ):
            value = headers.get(source)
            if value is not None and str(value).strip():
                details.append(f"{label}={str(value).strip()[:40]}")
        try:
            body = exc.read(1024).decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else {}
            reason = (parsed.get("error") or parsed.get("message")) if isinstance(parsed, dict) else None
            if reason:
                safe_reason = re.sub(r"[^A-Za-z0-9 _-]", "", str(reason))[:80]
                if safe_reason:
                    details.append(f"reason={safe_reason}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        raise ProviderCheckError("; ".join(details)) from None
    except (URLError, TimeoutError, OSError):
        raise ProviderCheckError("network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderCheckError("invalid JSON response") from None


def safe_id(value: object) -> str:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        return str(value)[:48]
    return "not reported"


def check_fivedollar() -> str:
    key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key:
        print("5DollarFootballAPI: MISSING_SECRET (FIVEDOLLARFOOTBALL_API_KEY)")
        return "MISSING_SECRET"
    headers = {"Authorization": f"Bearer {key}"}
    base = "https://api.5dollarfootballapi.com/v1"
    try:
        status, response_headers, payload = request_json(base + "/leagues?per_page=100", headers)
        if status != 200 or not isinstance(payload, dict) or payload.get("success") != 1:
            print("5DollarFootballAPI: UNEXPECTED_RESPONSE")
            return "FAILED"
        leagues = payload.get("data")
        if not isinstance(leagues, list):
            print("5DollarFootballAPI: AUTH_OK_BUT_SCHEMA_UNEXPECTED")
            return "FAILED"
        league_names = [
            str(item.get("name") or item.get("short_name") or "unknown")
            for item in leagues if isinstance(item, dict)
        ]
        remaining = response_headers.get("X-RateLimit-Remaining", "not supplied")
        print(
            f"5DollarFootballAPI: AUTH_OK; accessible_leagues={len(league_names)}; "
            f"leagues={'; '.join(league_names[:12])}; requests_remaining={remaining}"
        )
        selected_fixture = None
        selected_league = None
        for league in leagues[:8]:
            if not isinstance(league, dict) or league.get("id") is None:
                continue
            league_id = quote(str(league["id"]), safe="")
            fixtures_url = base + f"/leagues/{league_id}/fixtures?" + urlencode({
                "status": "scheduled", "per_page": 1,
            })
            try:
                _, _, fixture_payload = request_json(fixtures_url, headers)
            except ProviderCheckError:
                continue
            fixture_rows = fixture_payload.get("data") if isinstance(fixture_payload, dict) else None
            if isinstance(fixture_rows, list) and fixture_rows:
                selected_fixture = fixture_rows[0]
                selected_league = league
                break
        if selected_fixture is None:
            print("5DollarFootballAPI ODDS_SAMPLE: SKIPPED_NO_SCHEDULED_FIXTURE_IN_ACCESSIBLE_LEAGUES")
            return "AUTH_OK"
        fixture_id = selected_fixture.get("id") or selected_fixture.get("fixture_id")
        if fixture_id is None:
            print("5DollarFootballAPI ODDS_SAMPLE: FIXTURE_ID_MISSING")
            return "AUTH_OK"
        odds_url = base + f"/fixtures/{quote(str(fixture_id), safe='')}/odds"
        try:
            odds_status, odds_headers, odds_payload = request_json(odds_url, headers)
            odds_data = odds_payload.get("data") if isinstance(odds_payload, dict) else None
            bookmakers = odds_data.get("bookmakers") if isinstance(odds_data, dict) else None
            bet365 = next(
                (item for item in bookmakers or [] if isinstance(item, dict) and item.get("slug") == "bet365"),
                None,
            )
            markets = bet365.get("odds") if isinstance(bet365, dict) else None
            markets = markets if isinstance(markets, dict) else {}
            one_x_two = markets.get("1x2")
            btts = markets.get("btts")
            fixed_lines = markets.get("goal_line_fixed")
            total25 = next(
                (item for item in fixed_lines or [] if isinstance(item, dict) and str(item.get("line")) == "2.5"),
                None,
            )
            def complete(stage, keys):
                return isinstance(stage, dict) and all(stage.get(key) not in (None, "", 0, "0") for key in keys)
            available = {
                "1X2": complete(one_x_two.get("closing") if isinstance(one_x_two, dict) else None, ("home", "draw", "away")),
                "BTTS": complete(btts.get("closing") if isinstance(btts, dict) else None, ("yes", "no")),
                "TOTALS_2_5": complete(total25.get("closing") if isinstance(total25, dict) else None, ("over", "under")),
            }
            print(
                "5DollarFootballAPI ODDS_SAMPLE: "
                f"league={safe_id(selected_league.get('id'))}; fixture_id={safe_id(fixture_id)}; "
                + "; ".join(f"{market}={'available' if present else 'missing'}" for market, present in available.items())
                + f"; requests_remaining={odds_headers.get('X-RateLimit-Remaining', 'not supplied')}"
            )
        except ProviderCheckError as exc:
            print(f"5DollarFootballAPI ODDS_SAMPLE: FAILED ({exc})")
        return "AUTH_OK"
    except ProviderCheckError as exc:
        if str(exc) == "HTTP 429":
            print("5DollarFootballAPI: RATE_LIMITED_RETRYABLE (HTTP 429)")
            return "RATE_LIMITED"
        print(f"5DollarFootballAPI: FAILED ({exc})")
        return "FAILED"


def check_odds_api() -> str:
    key = os.getenv("THE_ODDS_API_KEY", "").strip()
    if not key:
        print("The Odds API: MISSING_SECRET (THE_ODDS_API_KEY)")
        return "MISSING_SECRET"
    # /v4/sports does not consume odds quota. The key is required by this provider's API in the query string.
    url = "https://api.the-odds-api.com/v4/sports/?" + urlencode({"apiKey": key})
    try:
        status, headers, payload = request_json(url)
        if status != 200 or not isinstance(payload, list):
            print("The Odds API: AUTH_OR_SCHEMA_FAILED")
            return "FAILED"
        soccer = [
            str(item.get("key")) for item in payload
            if isinstance(item, dict)
            and str(item.get("key", "")).startswith("soccer_")
            and item.get("active", True)
        ]
        remaining = headers.get("x-requests-remaining", "not supplied")
        if not soccer:
            print(f"The Odds API: KEY_ACCEPTED; NO_SOCCER_SPORTS_IN_PLAN; requests_remaining={remaining}")
            return "NO_SOCCER_SPORTS"
        print(f"The Odds API: KEY_ACCEPTED; soccer_sports={len(soccer)}; examples={','.join(soccer[:8])}; requests_remaining={remaining}")
        return "KEY_ACCEPTED"
    except ProviderCheckError as exc:
        print(f"The Odds API: FAILED ({exc})")
        return "FAILED"


def main() -> int:
    primary = check_fivedollar()
    secondary = check_odds_api()
    if primary == "AUTH_OK" and secondary == "KEY_ACCEPTED":
        print("PROVIDER_SMOKE_SUMMARY: HEALTHY (primary and supplemental providers authenticated)")
        return 0
    if primary == "RATE_LIMITED" and secondary == "KEY_ACCEPTED":
        print("PROVIDER_SMOKE_SUMMARY: DEGRADED_FALLBACK_READY (primary HTTP 429; The Odds API authenticated)")
        return 0
    print(f"PROVIDER_SMOKE_SUMMARY: FAILED (primary={primary}; supplemental={secondary})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
