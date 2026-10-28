"""Credential-safe smoke checks for the 5DollarFootballAPI and The Odds API.

Only prints provider status, market availability, and quota headers; never prints keys or request URLs.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
        # Do not print URL or provider response body: either can contain sensitive material.
        raise ProviderCheckError(f"HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderCheckError("network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderCheckError("invalid JSON response") from None


def check_fivedollar() -> bool:
    key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key:
        print("5DollarFootballAPI: MISSING_SECRET (FIVEDOLLARFOOTBALL_API_KEY)")
        return False
    url = "https://api.5dollarfootballapi.com/v1/fixtures?" + urlencode(
        {"status": "scheduled", "per_page": 1}
    )
    try:
        status, headers, payload = request_json(
            url, {"Authorization": f"Bearer {key}"}
        )
        if status != 200 or not isinstance(payload, dict) or payload.get("success") != 1:
            print("5DollarFootballAPI: UNEXPECTED_RESPONSE")
            return False
        data = payload.get("data")
        if not isinstance(data, list):
            print("5DollarFootballAPI: AUTH_OK_BUT_SCHEMA_UNEXPECTED")
            return False
        remaining = headers.get("X-RateLimit-Remaining", "not supplied")
        print(f"5DollarFootballAPI: AUTH_OK; scheduled fixture sample={len(data)}; requests_remaining={remaining}")
        return True
    except ProviderCheckError as exc:
        print(f"5DollarFootballAPI: FAILED ({exc})")
        return False


def check_odds_api() -> bool:
    key = os.getenv("THE_ODDS_API_KEY", "").strip()
    if not key:
        print("The Odds API: MISSING_SECRET (THE_ODDS_API_KEY)")
        return False
    # /v4/sports does not consume odds quota. The key is required by this provider's API in the query string.
    url = "https://api.the-odds-api.com/v4/sports/?" + urlencode({"apiKey": key})
    try:
        status, headers, payload = request_json(url)
        if status != 200 or not isinstance(payload, list):
            print("The Odds API: AUTH_OR_SCHEMA_FAILED")
            return False
        soccer = [
            str(item.get("key")) for item in payload
            if isinstance(item, dict)
            and str(item.get("key", "")).startswith("soccer_")
            and item.get("active", True)
        ]
        remaining = headers.get("x-requests-remaining", "not supplied")
        if not soccer:
            print(f"The Odds API: KEY_ACCEPTED; NO_SOCCER_SPORTS_IN_PLAN; requests_remaining={remaining}")
            return False
        print(f"The Odds API: KEY_ACCEPTED; soccer_sports={len(soccer)}; examples={','.join(soccer[:8])}; requests_remaining={remaining}")
        return True
    except ProviderCheckError as exc:
        print(f"The Odds API: FAILED ({exc})")
        return False


def main() -> int:
    results = [check_fivedollar(), check_odds_api()]
    print(f"PROVIDER_SMOKE_SUMMARY: {sum(results)}/2 provider checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
