"""Low-quota, credential-safe read-only verification for 5DollarFootballAPI.

Makes at most four GET requests: status, countries (one page), leagues (one page),
and one scheduled fixture. Never prints credentials, request URLs, or raw payloads.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.5dollarfootballapi.com/v1"
TIMEOUT = 20


class ProviderCheckError(RuntimeError):
    pass


def request_json(path: str, params: dict[str, object] | None = None):
    query = "?" + urlencode(params or {}) if params else ""
    req = Request(
        BASE + path + query,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {os.environ['FIVEDOLLARFOOTBALL_API_KEY'].strip()}",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, response.headers, payload
    except HTTPError as exc:
        safe = [f"HTTP {exc.code}"]
        for header, label in (
            ("X-RateLimit-Limit", "limit"),
            ("X-RateLimit-Remaining", "remaining"),
            ("X-RateLimit-Reset", "reset"),
            ("Retry-After", "retry_after"),
        ):
            value = (exc.headers or {}).get(header)
            if value:
                safe.append(f"{label}={str(value)[:40]}")
        raise ProviderCheckError("; ".join(safe)) from None
    except (URLError, TimeoutError, OSError):
        raise ProviderCheckError("network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderCheckError("invalid JSON response") from None


def envelope(payload):
    if not isinstance(payload, dict):
        return None
    if payload.get("success") not in (1, True, "1", "true"):
        return None
    return payload.get("data")


def rate_summary(headers) -> str:
    values = []
    for name, label in (
        ("X-RateLimit-Limit", "limit"),
        ("X-RateLimit-Remaining", "remaining"),
        ("X-RateLimit-Reset", "reset"),
    ):
        value = headers.get(name)
        if value is not None:
            values.append(f"{label}={str(value)[:40]}")
    return ", ".join(values) if values else "rate-limit headers not supplied"


def safe_scalar(value) -> str:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return re.sub(r"[^A-Za-z0-9 _./+-]", "", str(value))[:60] or "not reported"
    return "not reported"


def main() -> int:
    key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key:
        print("5DollarFootballAPI: MISSING_SECRET (FIVEDOLLARFOOTBALL_API_KEY)")
        return 2

    checks = (
        ("/status", None, "account status"),
        ("/countries", {"per_page": 100}, "country coverage"),
        ("/leagues", {"per_page": 100}, "competition coverage"),
        ("/fixtures", {"status": "scheduled", "per_page": 1}, "single scheduled fixture"),
    )
    results = {}
    for path, params, label in checks:
        try:
            status, headers, payload = request_json(path, params)
            data = envelope(payload)
            if status != 200 or data is None:
                print(f"5DollarFootballAPI {label}: UNEXPECTED_RESPONSE")
                return 1
            results[path] = (data, headers)
            print(f"5DollarFootballAPI {label}: HTTP {status}; {rate_summary(headers)}")
        except ProviderCheckError as exc:
            print(f"5DollarFootballAPI {label}: FAILED ({exc})")
            return 1

    status_data = results["/status"][0]
    if isinstance(status_data, dict):
        plan = status_data.get("plan") or status_data.get("subscription") or status_data.get("tier")
        usage = status_data.get("requests_used") or status_data.get("used")
        limit = status_data.get("requests_limit") or status_data.get("limit")
        print(
            "5DollarFootballAPI entitlement: "
            f"plan={safe_scalar(plan)}; usage={safe_scalar(usage)}; limit={safe_scalar(limit)}"
        )
    else:
        print("5DollarFootballAPI entitlement: status endpoint returned an unexpected data shape")
        return 1

    countries = results["/countries"][0]
    leagues = results["/leagues"][0]
    fixtures = results["/fixtures"][0]
    if not isinstance(countries, list) or not isinstance(leagues, list) or not isinstance(fixtures, list):
        print("5DollarFootballAPI coverage: UNEXPECTED_DATA_SHAPE")
        return 1

    print(f"5DollarFootballAPI coverage: countries_on_page={len(countries)}; competitions_on_page={len(leagues)}")
    print(f"5DollarFootballAPI fixture sample: scheduled_fixtures={len(fixtures)} (maximum requested: 1)")
    print("PROVIDER_READONLY_SUMMARY: PASS (four read-only requests; no database writes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
