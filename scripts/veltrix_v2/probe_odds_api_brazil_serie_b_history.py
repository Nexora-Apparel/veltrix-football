#!/usr/bin/env python3
"""Capped two-credit historical event/market discovery sample for Brazil Serie B.

This script never calls an odds/price endpoint and never writes to Neon.
It uses one 1-credit historical events discovery request and, only when the
target event is found uniquely, one 1-credit historical markets discovery
request. A no-credit /sports preflight must show at least 100 credits remain.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.phase4_odds_account_probe import _fetch_sports

API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "soccer_brazil_serie_b"
SNAPSHOT_AT = "2026-11-11T21:55:00Z"
TARGET_KICKOFF = "2026-11-11T22:00:00Z"
TARGET_HOME = "Londrina"
TARGET_AWAY = "Náutico"
REGION = "eu"
MIN_REMAINING_BEFORE_SPEND = 100
MAX_CREDITS = 2
USER_AGENT = "VELTRIX-FOOTBALL-2.0-HISTORICAL-COVERAGE-DISCOVERY/1.0"


def normalize_team(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold().strip()


def _request_json(path: str, api_key: str) -> tuple[dict | list, dict]:
    request = Request(
        API_BASE + path,
        headers={"x-api-key": api_key, "Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read(2_000_001)
            headers = {key.lower(): value for key, value in response.headers.items()}
            status = int(response.status)
    except HTTPError as exc:
        raise RuntimeError(f"HISTORICAL_DISCOVERY_HTTP_{exc.code}_NO_RETRY") from None
    except URLError:
        raise RuntimeError("HISTORICAL_DISCOVERY_NETWORK_ERROR_NO_RETRY") from None
    if status != 200:
        raise RuntimeError(f"HISTORICAL_DISCOVERY_HTTP_{status}_NO_RETRY")
    if len(body) > 2_000_000:
        raise RuntimeError("HISTORICAL_DISCOVERY_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("HISTORICAL_DISCOVERY_INVALID_JSON") from None
    quota = {}
    for name in ("x-requests-used", "x-requests-remaining", "x-requests-last"):
        raw = headers.get(name)
        if raw is None:
            raise RuntimeError("HISTORICAL_DISCOVERY_QUOTA_HEADER_MISSING:" + name)
        try:
            quota[name] = int(raw)
        except ValueError:
            raise RuntimeError("HISTORICAL_DISCOVERY_QUOTA_HEADER_INVALID:" + name) from None
    quota["response_sha256"] = hashlib.sha256(body).hexdigest()
    return payload, quota


def _payload_data(payload):
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"], payload.get("timestamp")
    return payload, None


def discover(api_key: str, sports_fetcher=_fetch_sports, request_json=_request_json, *, snapshot_at: str = SNAPSHOT_AT, target_kickoff: str = TARGET_KICKOFF, target_home: str = TARGET_HOME, target_away: str = TARGET_AWAY, region: str = REGION) -> dict:
    if not api_key.strip():
        raise RuntimeError("THE_ODDS_API_KEY_MISSING")
    requested_at, retrieved_at, sports_body, _, envelope, sports = sports_fetcher(api_key)
    quota = envelope.quota_evidence
    if SPORT not in sports:
        raise RuntimeError("BRAZIL_SERIE_B_SPORT_NOT_AVAILABLE")
    if not quota.complete or quota.requests_last != 0 or quota.requests_remaining is None:
        raise RuntimeError("ODDS_API_NO_CREDIT_PREFLIGHT_UNVERIFIED")
    if quota.requests_remaining < MIN_REMAINING_BEFORE_SPEND:
        return {
            "status": "SKIPPED_LOW_QUOTA",
            "quota_requests_remaining": quota.requests_remaining,
            "minimum_remaining_required": MIN_REMAINING_BEFORE_SPEND,
            "credits_spent": 0,
            "historical_price_calls": 0,
            "database_writes": 0,
        }

    events_path = "/historical/sports/" + SPORT + "/events?" + urlencode({"date": snapshot_at})
    events_payload, events_quota = request_json(events_path, api_key)
    if events_quota["x-requests-last"] != 1:
        raise RuntimeError("HISTORICAL_EVENTS_COST_NOT_ONE_CREDIT")
    if events_quota["x-requests-remaining"] > quota.requests_remaining:
        raise RuntimeError("HISTORICAL_EVENTS_QUOTA_INCREASED_UNEXPECTEDLY")
    events_data, events_timestamp = _payload_data(events_payload)
    if not isinstance(events_data, list):
        raise RuntimeError("HISTORICAL_EVENTS_DATA_NOT_LIST")
    matches = [
        event for event in events_data
        if isinstance(event, dict)
        and normalize_team(event.get("home_team", "")) == normalize_team(target_home)
        and normalize_team(event.get("away_team", "")) == normalize_team(target_away)
    ]
    base = {
        "provider": "the_odds_api",
        "sport_key": SPORT,
        "target_fixture": {"home": target_home, "away": target_away, "kickoff": target_kickoff},
        "requested_snapshot_at": snapshot_at,
        "event_discovery_snapshot_timestamp": events_timestamp,
        "event_discovery_response_sha256": events_quota["response_sha256"],
        "event_discovery_requests_used": events_quota["x-requests-used"],
        "event_discovery_requests_remaining": events_quota["x-requests-remaining"],
        "event_discovery_request_cost": events_quota["x-requests-last"],
        "events_returned_at_snapshot": len(events_data),
        "target_event_candidates": len(matches),
        "historical_price_calls": 0,
        "database_writes": 0,
        "api_key_emitted": False,
        "raw_response_uploaded": False,
    }
    if len(matches) == 0:
        return {**base, "status": "EVENT_NOT_FOUND_AT_SNAPSHOT", "credits_spent": 1, "bookmakers": []}
    if len(matches) != 1:
        return {**base, "status": "AMBIGUOUS_EVENT_MATCH", "credits_spent": 1, "bookmakers": []}

    event = matches[0]
    if event.get("commence_time") != target_kickoff:
        return {
            **base,
            "status": "EVENT_KICKOFF_MISMATCH",
            "credits_spent": 1,
            "event_id": event.get("id"),
            "event_commence_time": event.get("commence_time"),
            "bookmakers": [],
        }
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise RuntimeError("HISTORICAL_EVENT_ID_MISSING")

    if events_quota["x-requests-remaining"] < MIN_REMAINING_BEFORE_SPEND:
        return {
            **base,
            "status": "EVENT_FOUND_MARKET_DISCOVERY_SKIPPED_LOW_QUOTA",
            "credits_spent": 1,
            "event_id": event_id,
            "event_commence_time": event.get("commence_time"),
            "bookmakers": [],
        }
    markets_path = (
        "/historical/sports/" + SPORT + "/events/" + event_id + "/markets?"
        + urlencode({"regions": region, "date": snapshot_at})
    )
    markets_payload, markets_quota = request_json(markets_path, api_key)
    if markets_quota["x-requests-last"] != 1:
        raise RuntimeError("HISTORICAL_MARKETS_COST_NOT_ONE_CREDIT")
    if markets_quota["x-requests-remaining"] != events_quota["x-requests-remaining"] - 1:
        raise RuntimeError("HISTORICAL_MARKETS_QUOTA_DELTA_UNEXPECTED")
    markets_data, markets_timestamp = _payload_data(markets_payload)
    if isinstance(markets_data, dict):
        market_bookmakers = markets_data.get("bookmakers", [])
    elif isinstance(markets_data, list):
        market_bookmakers = markets_data
    else:
        raise RuntimeError("HISTORICAL_MARKETS_DATA_SHAPE_INVALID")
    if not isinstance(market_bookmakers, list):
        raise RuntimeError("HISTORICAL_MARKETS_BOOKMAKERS_NOT_LIST")
    bookmakers = []
    for item in market_bookmakers:
        if not isinstance(item, dict):
            continue
        market_items = item.get("markets", [])
        if not isinstance(market_items, list):
            market_items = []
        markets = []
        for market in market_items:
            if isinstance(market, dict) and market.get("key"):
                markets.append({
                    "market_key": str(market["key"]),
                    "last_update": market.get("last_update"),
                })
            elif isinstance(market, str):
                markets.append({"market_key": market, "last_update": None})
        bookmakers.append({
            "bookmaker_key": item.get("key"),
            "bookmaker_title": item.get("title"),
            "markets": sorted(markets, key=lambda value: value["market_key"]),
        })
    return {
        **base,
        "status": "EVENT_AND_MARKETS_DISCOVERED",
        "event_id": event_id,
        "event_commence_time": event.get("commence_time"),
        "event_home_team": event.get("home_team"),
        "event_away_team": event.get("away_team"),
        "market_discovery_snapshot_timestamp": markets_timestamp,
        "market_discovery_response_sha256": markets_quota["response_sha256"],
        "market_discovery_requests_used": markets_quota["x-requests-used"],
        "market_discovery_requests_remaining": markets_quota["x-requests-remaining"],
        "market_discovery_request_cost": markets_quota["x-requests-last"],
        "bookmakers": bookmakers,
        "bookmaker_count": len(bookmakers),
        "market_keys": sorted({market["market_key"] for book in bookmakers for market in book["markets"]}),
        "credits_spent": 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--snapshot-at", default=SNAPSHOT_AT)
    parser.add_argument("--kickoff", default=TARGET_KICKOFF)
    parser.add_argument("--home", default=TARGET_HOME)
    parser.add_argument("--away", default=TARGET_AWAY)
    parser.add_argument("--region", default=REGION)
    args = parser.parse_args()
    result = discover(
        os.environ.get("THE_ODDS_API_KEY", ""),
        snapshot_at=args.snapshot_at,
        target_kickoff=args.kickoff,
        target_home=args.home,
        target_away=args.away,
        region=args.region,
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"EVENT_AND_MARKETS_DISCOVERED", "EVENT_NOT_FOUND_AT_SNAPSHOT", "EVENT_FOUND_MARKET_DISCOVERY_SKIPPED_LOW_QUOTA"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
