"""Credential-safe smoke checks for the 5DollarFootballAPI and The Odds API.

Only prints provider status, market availability, and quota headers; never prints keys or request URLs.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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
        status, _, account_payload = request_json(base + "/status", headers)
        account_data = account_payload.get("data") if isinstance(account_payload, dict) else None
        plan = account_data.get("plan") if isinstance(account_data, dict) else None
        required_plan = os.getenv("FIVEDOLLAR_REQUIRED_PLAN", "").strip().casefold()
        if (
            status != 200
            or not isinstance(account_payload, dict)
            or account_payload.get("success") != 1
            or not isinstance(plan, str)
            or not plan.strip()
        ):
            print("5DollarFootballAPI: ACCOUNT_STATUS_UNAVAILABLE")
            return "FAILED"
        if required_plan and plan.strip().casefold() != required_plan:
            print(
                "5DollarFootballAPI: PLAN_MISMATCH "
                f"(expected={required_plan}; actual={plan.strip().casefold()})"
            )
            return "PLAN_MISMATCH"
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
        top_five_country_codes = {"GB-ENG", "ES", "IT", "DE", "FR"}
        def league_country_code(item):
            country = item.get("country") if isinstance(item, dict) else None
            code = country.get("code") if isinstance(country, dict) else None
            return str(code).strip().upper() if code else ""
        country_pack_leagues = [
            item for item in leagues
            if league_country_code(item)
            and league_country_code(item) not in top_five_country_codes
            and league_country_code(item) not in {"WORLD", "EUROPE", "AFRICA", "ASIA", "AMERICAS", "OCEANIA"}
        ]
        required_country_code = os.getenv("FIVEDOLLAR_REQUIRED_COUNTRY_CODE", "").strip().upper()
        try:
            minimum_leagues = int(os.getenv("FIVEDOLLAR_MIN_ACCESSIBLE_LEAGUES", "6"))
        except ValueError:
            print("5DollarFootballAPI: MIN_ACCESSIBLE_LEAGUES_CONFIGURATION_INVALID")
            return "FAILED"
        if required_plan and (minimum_leagues < 6 or len(league_names) < minimum_leagues):
            print(
                "5DollarFootballAPI: COMPETITION_COVERAGE_INCOMPLETE "
                f"(minimum={minimum_leagues}; actual={len(league_names)})"
            )
            return "COMPETITION_COVERAGE_INCOMPLETE"
        if required_plan and not country_pack_leagues:
            print("5DollarFootballAPI: COUNTRY_PACK_NOT_VERIFIED")
            return "COUNTRY_PACK_NOT_VERIFIED"
        if required_country_code and not any(
            league_country_code(item) == required_country_code for item in country_pack_leagues
        ):
            print(
                "5DollarFootballAPI: REQUIRED_COUNTRY_PACK_MISSING "
                f"(expected={required_country_code})"
            )
            return "REQUIRED_COUNTRY_PACK_MISSING"
        remaining = response_headers.get("X-RateLimit-Remaining", "not supplied")
        print(
            f"5DollarFootballAPI: AUTH_OK; plan={plan.strip().casefold()}; "
            f"accessible_leagues={len(league_names)}; leagues={'; '.join(league_names[:12])}; "
            f"country_pack_codes={';'.join(sorted({league_country_code(item) for item in country_pack_leagues}))}; "
            f"requests_remaining={remaining}"
        )
        # One scheduled fixture per accessible league verifies both the top-five
        # and any activated country pack without exceeding the 20/minute burst.
        selected_fixtures = []
        ordered_leagues = sorted(
            (item for item in leagues if isinstance(item, dict)),
            key=lambda item: (
                0 if league_country_code(item) in top_five_country_codes else
                1 if item in country_pack_leagues else 2,
                str(item.get("name") or ""),
            ),
        )
        for league in ordered_leagues[:8]:
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
                selected_fixtures.append((league, fixture_rows[0]))
        if not selected_fixtures:
            print("5DollarFootballAPI ODDS_SAMPLE: SKIPPED_NO_SCHEDULED_FIXTURE_IN_ACCESSIBLE_LEAGUES")
            return "AUTH_OK"
        coverage = {"1X2": 0, "BTTS": 0, "TOTALS_2_5": 0}
        samples = 0
        odds_headers = {}
        for selected_league, fixture in selected_fixtures:
            fixture_id = fixture.get("id") or fixture.get("fixture_id")
            if fixture_id is None:
                continue
            odds_url = base + f"/fixtures/{quote(str(fixture_id), safe='')}/odds"
            try:
                _, odds_headers, odds_payload = request_json(odds_url, headers)
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
                for market, present in available.items():
                    coverage[market] += int(present)
                samples += 1
            except ProviderCheckError as exc:
                print(f"5DollarFootballAPI ODDS_SAMPLE: fixture_id={safe_id(fixture_id)} failed ({exc})")
        print(
            "5DollarFootballAPI ODDS_SAMPLE: "
            f"leagues_probed={len(selected_fixtures)}; fixtures={samples}; "
            + "; ".join(f"{market}={count}/{samples}" for market, count in coverage.items())
            + f"; requests_remaining={odds_headers.get('X-RateLimit-Remaining', 'not supplied')}"
        )
        return "AUTH_OK"
    except ProviderCheckError as exc:
        if str(exc) == "HTTP 429":
            print("5DollarFootballAPI: RATE_LIMITED_RETRYABLE (HTTP 429)")
            return "RATE_LIMITED"
        print(f"5DollarFootballAPI: FAILED ({exc})")
        return "FAILED"



def probe_odds_api_btts(soccer_sports: list[dict], api_key: str) -> None:
    """Optional bounded BTTS spot-check, one upcoming event per selected league (max eight credits)."""
    from veltrix_v2.providers.the_odds_api import (
        TheOddsProviderError, fetch_event_btts_odds,
    )

    target_keys = (
        "soccer_england_premier_league",
        "soccer_france_ligue_one",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_spain_la_liga",
        "soccer_argentina_primera_division",
        "soccer_brazil_campeonato",
        "soccer_brazil_serie_b",
    )
    available = {
        str(item.get("key")): item
        for item in soccer_sports
        if isinstance(item, dict) and item.get("key")
    }
    base = "https://api.the-odds-api.com/v4"
    probed = 0
    quoted = 0
    for sport_key in target_keys:
        if sport_key not in available:
            print(f"The Odds API BTTS_PROBE: sport={sport_key}; status=NOT_IN_PLAN")
            continue
        events_url = base + f"/sports/{quote(sport_key, safe='')}/events/?" + urlencode({"apiKey": api_key})
        try:
            _, _, events = request_json(events_url)
        except ProviderCheckError as exc:
            print(f"The Odds API BTTS_PROBE: sport={sport_key}; events_lookup=FAILED ({exc})")
            continue
        if not isinstance(events, list):
            print(f"The Odds API BTTS_PROBE: sport={sport_key}; events_lookup=INVALID_RESPONSE")
            continue
        now = datetime.now(timezone.utc)
        upcoming = []
        for event in events:
            if not isinstance(event, dict) or not event.get("id"):
                continue
            value = event.get("commence_time")
            if not isinstance(value, str):
                continue
            try:
                kickoff = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if kickoff.tzinfo is None or kickoff.utcoffset() is None or kickoff <= now:
                continue
            upcoming.append((kickoff.astimezone(timezone.utc), event))
        if not upcoming:
            print(f"The Odds API BTTS_PROBE: sport={sport_key}; status=NO_UPCOMING_EVENT")
            continue
        kickoff, event = min(upcoming, key=lambda item: item[0])
        captured = datetime.now(timezone.utc)
        try:
            result = fetch_event_btts_odds(
                api_key=api_key,
                sport_key=sport_key,
                event_id=str(event["id"]),
                fixture_id=f"provider-probe:{sport_key}:{event['id']}",
                kickoff_at=kickoff,
                captured_at=captured,
                regions="uk",
                source_observation_id=(
                    f"provider-probe:{sport_key}:{event['id']}:{captured.isoformat()}"
                ),
            )
        except (TheOddsProviderError, ValueError) as exc:
            print(f"The Odds API BTTS_PROBE: sport={sport_key}; odds_lookup=FAILED ({getattr(exc, 'code', str(exc))})")
            continue
        bookmaker_quotes = len(result.snapshots) // 2
        probed += 1
        quoted += bookmaker_quotes
        print(
            f"The Odds API BTTS_PROBE: sport={sport_key}; event_found=1; "
            f"bookmakers_with_complete_btts={bookmaker_quotes}; "
            f"missing_bookmakers={len(result.missing_bookmakers)}; "
            f"requests_remaining={result.requests_remaining if result.requests_remaining is not None else 'not supplied'}"
        )
    print(f"The Odds API BTTS_PROBE_SUMMARY: leagues_probed={probed}; complete_bookmaker_quotes={quoted}; maximum_odds_credits=8")


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
        if os.getenv("PROBE_THE_ODDS_API_MARKETS", "false").strip().casefold() in {"1", "true", "yes"}:
            probe_odds_api_btts(
                [item for item in payload if isinstance(item, dict) and str(item.get("key", "")).startswith("soccer_")],
                key,
            )
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
