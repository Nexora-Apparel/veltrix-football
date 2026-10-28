"""Live, bounded verification of provider fixtures and market endpoints.

This script never prints credentials or full request URLs. The Odds API check is
bounded to three soccer sport odds calls plus three event-specific BTTS calls.
InferSports is keyless; its probe checks today's event list and at most three odds boards.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from app.provider_adapters import (
    DEFAULT_SOCCER_SPORTS,
    FiveDollarFootballClient,
    ProviderAPIError,
    TheOddsAPIClient,
    InferSportsClient,
)


def main() -> int:
    results: dict[str, object] = {}
    five = FiveDollarFootballClient()
    if not five.api_key:
        results["five_dollar"] = {"status": "MISSING_SECRET"}
    else:
        try:
            day = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
            fixtures = five.fixtures(day, "Africa/Lagos")
            rows = fixtures.get("response", [])
            scheduled = [
                row for row in rows
                if isinstance(row, dict)
                and ((row.get("fixture") or {}).get("status") or {}).get("short") == "NS"
            ]
            odds_attempts = 0
            odds_markets: set[str] = set()
            for row in scheduled[:3]:
                fixture_id = (row.get("fixture") or {}).get("id")
                if fixture_id is None:
                    continue
                odds_attempts += 1
                payload = five.fixture_odds(fixture_id).get("data") or {}
                for book in payload.get("bookmakers") or []:
                    if isinstance(book, dict):
                        odds_markets.update(str(k) for k in (book.get("odds") or {}).keys())
                if {"btts", "goal_line"} <= odds_markets or "goal_line_fixed" in odds_markets:
                    break
            results["five_dollar"] = {
                "status": "CONNECTED",
                "fixtures_today_lagos": len(rows),
                "scheduled_fixtures": len(scheduled),
                "fixture_odds_calls": odds_attempts,
                "market_keys_seen": sorted(odds_markets),
                "requests_remaining": (fixtures.get("_veltrix_meta") or {}).get("requests_remaining"),
            }
        except (ProviderAPIError, TypeError, ValueError) as exc:
            results["five_dollar"] = {"status": "FAILED", "reason": str(exc)[:160]}

    odds = TheOddsAPIClient()
    if not odds.api_key:
        results["the_odds_api"] = {"status": "MISSING_SECRET"}
    else:
        try:
            sports = odds.soccer_sports()
            active_keys = {str(row.get("key")) for row in sports}
            candidates = [key for key in DEFAULT_SOCCER_SPORTS if key in active_keys][:3]
            sports_checked = []
            sample_event = None
            sample_sport = None
            markets_seen: set[str] = set()
            for sport_key in candidates:
                events = odds.odds_for_sport(sport_key, regions="uk", markets="h2h,totals")
                sports_checked.append({"sport": sport_key, "events": len(events)})
                for event in events:
                    for book in event.get("bookmakers") or []:
                        if isinstance(book, dict):
                            markets_seen.update(
                                str(market.get("key")) for market in (book.get("markets") or [])
                                if isinstance(market, dict)
                            )
                    if sample_event is None and event.get("id"):
                        sample_event, sample_sport = event, sport_key
                if sample_event is not None:
                    break
            btts_status = "NOT_TESTED_NO_EVENT"
            if sample_event is not None and sample_sport:
                btts_events = odds.event_btts(sample_sport, str(sample_event["id"]), regions="uk")
                for event in btts_events:
                    for book in event.get("bookmakers") or []:
                        if isinstance(book, dict):
                            markets_seen.update(
                                str(market.get("key")) for market in (book.get("markets") or [])
                                if isinstance(market, dict)
                            )
                btts_status = "AVAILABLE" if "btts" in markets_seen else "NO_BTTS_PRICE_RETURNED"
            results["the_odds_api"] = {
                "status": "CONNECTED",
                "active_soccer_sports": len(sports),
                "sports_checked": sports_checked,
                "market_keys_seen": sorted(markets_seen),
                "btts_probe": btts_status,
                "quota": dict(odds.last_quota),
            }
        except (ProviderAPIError, TypeError, ValueError) as exc:
            results["the_odds_api"] = {"status": "FAILED", "reason": str(exc)[:160]}

    infer = InferSportsClient()
    try:
        day = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
        events = infer.events_for_date(day, "Africa/Lagos")
        market_keys: set[str] = set()
        odds_probe = "NOT_TESTED_NO_EVENTS"
        odds_requests = 0
        for event in events[:3]:
            event_id = str(event.get("id") or "")
            if not event_id:
                continue
            odds_requests += 1
            odds_block = infer.event_odds(event_id)
            market_keys.update(
                str(row.get("market_type")) for row in (odds_block.get("odds") or [])
                if isinstance(row, dict)
            )
            if market_keys:
                odds_probe = "AVAILABLE"
                break
        if events and not market_keys:
            odds_probe = "NO_CURRENT_QUOTES"
        results["infer_sports"] = {
            "status": "CONNECTED",
            "events_today_lagos": len(events),
            "market_types_seen": sorted(market_keys),
            "odds_requests": odds_requests,
            "odds_probe": odds_probe,
            "note": "Keyless read-only endpoint; only totals and 1X2 are available, not BTTS.",
        }
    except ProviderAPIError as exc:
        results["infer_sports"] = {"status": "FAILED", "reason": str(exc)[:160]}

    connected = sum(
        1 for name in ("five_dollar", "the_odds_api", "infer_sports")
        if isinstance(results.get(name), dict) and results[name].get("status") == "CONNECTED"
    )
    print(json.dumps({
        "checked_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "providers_connected": f"{connected}/3",
        "details": results,
        "note": "Connected means authentication and response schema passed. Market coverage can legitimately be empty for a fixture or competition.",
    }, indent=2, ensure_ascii=False))
    return 0 if connected == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
