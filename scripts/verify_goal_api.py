"""Bounded, read-only GOAL API coverage probe.

Requires GOAL_API_KEY in the GitHub Actions environment. Makes at most nineteen GET requests: countries, Argentina/Brazil league lists,
fixtures/results samples for one top-flight league per country, and up to twelve
pages of the global league catalogue so women's competitions are not missed.
Never prints the credential or raw response payloads.
"""
from __future__ import annotations

import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.goal-api.com/v1"
TIMEOUT = 20


class ProbeError(RuntimeError):
    pass


def get(path: str, params: dict[str, object] | None = None):
    url = BASE + path + (("?" + urlencode(params)) if params else "")
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {os.environ['GOAL_API_KEY'].strip()}",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, response.headers, body
    except HTTPError as exc:
        headers = exc.headers or {}
        safe = [f"HTTP {exc.code}"]
        for key, label in (
            ("X-RateLimit-Limit", "limit"),
            ("X-RateLimit-Remaining", "remaining"),
            ("X-RateLimit-Reset", "reset"),
            ("X-RateLimit-Type", "window"),
            ("WWW-Authenticate", "www_authenticate"),
            ("CF-Ray", "cf_ray"),
            ("X-Request-Id", "request_id"),
            ("Content-Type", "content_type"),
            ("Server", "server"),
        ):
            if headers.get(key):
                safe.append(f"{label}={re.sub(r'[^A-Za-z0-9 _./:+-]', '', str(headers[key]))[:100]}")
        # Capture only a bounded, sanitized error description. Never print request
        # headers, credentials, or an arbitrary upstream response payload.
        try:
            raw = exc.read(2048).decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            if isinstance(parsed, dict):
                detail = parsed.get("message") or parsed.get("error") or parsed.get("detail") or parsed.get("code")
            else:
                detail = raw
            if isinstance(detail, (str, int, float)):
                detail = re.sub(r"[^A-Za-z0-9 _.,:;()/-]", "", str(detail))[:240]
                if detail:
                    safe.append(f"detail={detail}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        raise ProbeError("; ".join(safe)) from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("invalid JSON response") from None


def data_of(body):
    if not isinstance(body, dict) or body.get("success") is not True:
        return None
    return body.get("data")


def rate_of(headers) -> str:
    vals = []
    for key, label in (
        ("X-RateLimit-Limit", "limit"),
        ("X-RateLimit-Remaining", "remaining"),
        ("X-RateLimit-Reset", "reset"),
        ("X-RateLimit-Type", "window"),
    ):
        if headers.get(key) is not None:
            vals.append(f"{label}={str(headers[key])[:40]}")
    return ", ".join(vals) or "rate headers not supplied"


def safe(value) -> str:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return re.sub(r"[^A-Za-z0-9 _./+-]", "", str(value))[:80] or "not reported"
    return "not reported"


def rows_of(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("leagues", "countries", "fixtures", "results", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def choose_league(rows, patterns):
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        name = str(row.get("name") or row.get("leagueName") or "")
        low = name.casefold()
        if any(pattern in low for pattern in patterns):
            candidates.append((row, name))
    if not candidates:
        return None
    # Prefer explicitly top-tier naming; stable tie-break by name and opaque id.
    candidates.sort(key=lambda pair: (
        0 if any(x in pair[1].casefold() for x in ("liga profesional", "brasileirão série a", "brasileirao serie a", "serie a")) else 1,
        pair[1].casefold(),
        str(pair[0].get("id")),
    ))
    return candidates[0][0]


def main() -> int:
    if not os.getenv("GOAL_API_KEY", "").strip():
        print("GOAL_API: MISSING_SECRET (GOAL_API_KEY)")
        return 2

    requests = 0

    def call(path, params=None):
        nonlocal requests
        # Count attempted requests, including HTTP/network failures.
        requests += 1
        status, headers, body = get(path, params)
        data = data_of(body)
        if status != 200 or data is None:
            raise ProbeError(f"{path}: unexpected response")
        print(f"GOAL_API {path}: HTTP {status}; {rate_of(headers)}")
        return data, body.get("pagination"), headers

    try:
        countries_data, _, _ = call("/countries")
        countries = rows_of(countries_data)
        print(f"GOAL_API countries returned: {len(countries)}")

        wanted = {
            "Argentina": ("liga profesional", "primera división", "primera division"),
            "Brazil": ("brasileirão série a", "brasileirao serie a", "brasileiro série a", "brasileiro serie a", "serie a"),
        }
        tested = 0
        for country_name, patterns in wanted.items():
            country = next((
                item for item in countries
                if isinstance(item, dict)
                and str(item.get("name") or "").casefold() == country_name.casefold()
                and item.get("id") is not None
            ), None)
            if country is None:
                print(f"GOAL_API {country_name}: COUNTRY_NOT_FOUND")
                continue
            leagues_data, _, _ = call(f"/countries/{country['id']}/leagues")
            league_rows = rows_of(leagues_data)
            league = choose_league(league_rows, patterns)
            print(
                f"GOAL_API {country_name}: leagues_returned={len(league_rows)}; "
                f"target_competition={'found' if league else 'not found'}"
            )
            if not league:
                continue
            league_id = league["id"]
            league_name = safe(league.get("name") or league.get("leagueName"))
            print(f"GOAL_API target competition: {country_name} / {league_name} / id={safe(league_id)}")
            for endpoint in ("fixtures", "results"):
                data, pagination, _ = call(f"/leagues/{league_id}/{endpoint}", {"limit": 1, "offset": 0})
                sample_rows = rows_of(data)
                has_more = pagination.get("hasMore") if isinstance(pagination, dict) else "not reported"
                print(
                    f"GOAL_API {country_name} {endpoint}: sample_records={len(sample_rows)}; "
                    f"has_more={safe(has_more)}"
                )
            tested += 1

        # Walk the public catalogue in bounded 100-row pages. A first-page-only
        # probe can falsely report no women's coverage because the catalogue is
        # popularity-sorted rather than grouped by competition type.
        women_terms = ("women", "women's", "feminine", "femenina", "feminino", "ladies")
        women = set()
        offset = 0
        catalogue_complete = False
        for _ in range(12):
            global_data, pagination, _ = call("/leagues", {"limit": 100, "offset": offset})
            global_rows = rows_of(global_data)
            for item in global_rows:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("leagueName") or "")
                    if any(term in name.casefold() for term in women_terms):
                        women.add(safe(name))
            has_more = pagination.get("hasMore") if isinstance(pagination, dict) else None
            if has_more is False:
                catalogue_complete = True
                break
            if has_more is not True or not global_rows:
                break
            offset += 100
        print(
            f"GOAL_API women's catalogue: matches={'; '.join(sorted(women)[:40]) if women else 'none found'}; "
            f"catalogue_complete={'yes' if catalogue_complete else 'no (bounded scan)'}"
        )
        print(f"GOAL_API_REQUESTS_MADE: {requests} (maximum 19)")
        print("DATABASE_WRITES: 0; IMPORTS: 0")
        print(
            "GOAL_API_PROBE_RESULT: "
            + ("PARTIAL_PASS (Argentina/Brazil targeted samples tested; women's catalogue scan completed or bounded)"
               if tested else "PARTIAL (no target top-flight sample verified)")
        )
        return 0
    except ProbeError as exc:
        print(f"GOAL_API_PROBE_FAILED: {exc}")
        print(f"GOAL_API_REQUESTS_MADE: {requests}")
        print("DATABASE_WRITES: 0; IMPORTS: 0")
        return 1


if __name__ == "__main__":
    sys.exit(main())
