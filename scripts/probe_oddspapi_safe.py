#!/usr/bin/env python3
"""Credential-safe, bounded OddsPapi soccer quote probe for Phase 1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.oddspapi_odds import OddsPapiClient, OddsPapiError


def _hash(report: dict) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def probe(client, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    requests = 0
    sports = client.get("sports")
    requests += 1
    if not isinstance(sports, list):
        raise OddsPapiError("OddsPapi sports response has an unexpected shape.")
    soccer = [
        row for row in sports
        if isinstance(row, dict) and (
            str(row.get("sportId")) == "10"
            or "soccer" in str(row.get("sportName", "")).casefold()
            or "football" in str(row.get("sportName", "")).casefold()
        )
    ]

    markets = client.get("markets", {"language": "en"})
    requests += 1
    if not isinstance(markets, list):
        raise OddsPapiError("OddsPapi markets response has an unexpected shape.")
    soccer_markets = [
        row for row in markets
        if isinstance(row, dict) and str(row.get("sportId")) == "10"
    ]
    btts_ids = {
        str(row.get("marketId")) for row in soccer_markets
        if "both teams to score" in str(row.get("marketName", "")).casefold()
        and row.get("marketId") is not None
    }
    ou_ids = {
        str(row.get("marketId")) for row in soccer_markets
        if "over under" in str(row.get("marketName", "")).casefold().replace("/", " ")
        and not row.get("playerProp", False)
        and str(row.get("period", "")).casefold() in {"", "fulltime", "ft", "full_time"}
        and row.get("marketId") is not None
    }

    fixtures = client.get("fixtures", {
        "sportId": 10,
        "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": (now + timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "statusId": 0,
        "hasOdds": "true",
    })
    requests += 1
    if not isinstance(fixtures, list):
        raise OddsPapiError("OddsPapi fixtures response has an unexpected shape.")
    candidates = [
        row for row in fixtures
        if isinstance(row, dict) and str(row.get("sportId")) == "10"
        and row.get("fixtureId") is not None and row.get("hasOdds")
    ]

    checked = []
    btts_quotes = 0
    ou_quotes = 0
    bookmakers_seen = set()
    market_ids_seen = set()
    for fixture in candidates[:1]:
        odds = client.get("odds", {"fixtureId": fixture["fixtureId"], "verbosity": 3})
        requests += 1
        boards = odds.get("bookmakerOdds", {}) if isinstance(odds, dict) else {}
        fixture_btts = 0
        fixture_ou = 0
        if isinstance(boards, dict):
            for bookmaker, board in boards.items():
                if not isinstance(board, dict):
                    continue
                bookmakers_seen.add(str(bookmaker)[:80])
                market_map = board.get("markets", {})
                if not isinstance(market_map, dict):
                    continue
                for market_id, market in market_map.items():
                    if not isinstance(market, dict):
                        continue
                    active_prices = []
                    outcomes = market.get("outcomes") or {}
                    if isinstance(outcomes, list):
                        outcomes = {str(i): value for i, value in enumerate(outcomes)}
                    if isinstance(outcomes, dict):
                        for outcome in outcomes.values():
                            if not isinstance(outcome, dict):
                                continue
                            players = outcome.get("players") or {}
                            if isinstance(players, list):
                                players = {str(i): value for i, value in enumerate(players)}
                            if isinstance(players, dict):
                                for player in players.values():
                                    if isinstance(player, dict) and player.get("active"):
                                        try:
                                            price_value = float(player.get("price"))
                                        except (TypeError, ValueError, OverflowError):
                                            continue
                                        if 1 < price_value < 1000:
                                            active_prices.append(price_value)
                    if active_prices:
                        market_ids_seen.add(str(market_id))
                        if str(market_id) in btts_ids:
                            fixture_btts += len(active_prices)
                        if str(market_id) in ou_ids:
                            fixture_ou += len(active_prices)
        btts_quotes += fixture_btts
        ou_quotes += fixture_ou
        checked.append({
            "fixture_id": str(fixture.get("fixtureId")),
            "competition": str(fixture.get("tournamentName") or "not_reported")[:100],
            "btts_active_prices": fixture_btts,
            "over_under_active_prices": fixture_ou,
        })

    # One bounded historical sample verifies whether this account can retrieve
    # stored prices with source-created timestamps. The API documents a 5s
    # endpoint cooldown; this workflow makes at most one historical-odds call.
    historical_status = "NO_FINISHED_FIXTURE_SAMPLE"
    historical_rows = 0
    historical_timestamped_rows = 0
    historical_bookmakers = 0
    historical_created_at_min = None
    historical_created_at_max = None
    try:
        history_fixtures = client.get("fixtures", {
            "sportId": 10,
            "from": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hasOdds": "true",
        })
        requests += 1
    except OddsPapiError:
        requests += 1
        history_fixtures = []
        historical_status = "HISTORICAL_FIXTURE_LOOKUP_ERROR"
    if isinstance(history_fixtures, list):
        past = []
        for row in history_fixtures:
            if not isinstance(row, dict) or row.get("fixtureId") is None:
                continue
            raw_start = str(row.get("startTime") or "")
            try:
                kickoff = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
            except ValueError:
                continue
            if kickoff.tzinfo is not None and kickoff <= now:
                past.append((kickoff, row))
        past.sort(key=lambda item: item[0], reverse=True)
        if past:
            historical_fixture = past[0][1]
            try:
                bookmaker_filter = ",".join(sorted(bookmakers_seen)[:3]) or "pinnacle,bet365"
                historical = client.get("historical-odds", {
                    "fixtureId": historical_fixture["fixtureId"],
                    "bookmakers": bookmaker_filter,
                })
                requests += 1
                books = historical.get("bookmakers", {}) if isinstance(historical, dict) else {}
                if isinstance(books, dict):
                    historical_bookmakers = len(books)
                    for board in books.values():
                        if not isinstance(board, dict):
                            continue
                        market_map = board.get("markets") or {}
                        if not isinstance(market_map, dict):
                            continue
                        for market in market_map.values():
                            if not isinstance(market, dict):
                                continue
                            outcomes = market.get("outcomes") or {}
                            if not isinstance(outcomes, dict):
                                continue
                            for outcome in outcomes.values():
                                if not isinstance(outcome, dict):
                                    continue
                                players = outcome.get("players") or {}
                                if not isinstance(players, dict):
                                    continue
                                for player_rows in players.values():
                                    rows = player_rows if isinstance(player_rows, list) else [player_rows]
                                    for item in rows:
                                        if not isinstance(item, dict):
                                            continue
                                        price = item.get("price")
                                        if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 1:
                                            historical_rows += 1
                                            created = item.get("createdAt")
                                            if isinstance(created, str) and created.strip():
                                                try:
                                                    parsed_created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                                                except ValueError:
                                                    parsed_created = None
                                                if parsed_created is not None and parsed_created.tzinfo is not None:
                                                    historical_timestamped_rows += 1
                                                    historical_created_at_min = min(historical_created_at_min, created) if historical_created_at_min else created
                                                    historical_created_at_max = max(historical_created_at_max, created) if historical_created_at_max else created
                    historical_status = "OK_WITH_TIMESTAMPED_ROWS" if historical_timestamped_rows else ("OK_NO_TIMESTAMPED_ROWS" if historical_rows else "OK_EMPTY")
                else:
                    historical_status = "INVALID_RESPONSE_SHAPE"
            except OddsPapiError:
                requests += 1
                historical_status = "HISTORICAL_ENDPOINT_ERROR"

    report = {
        "schema_version": 1,
        "provider": "OddsPapi",
        "mode": "read_only_soccer_quote_probe",
        "checked_at_utc": now.isoformat(),
        "status": "AUTH_OK_WITH_QUOTES" if (btts_quotes or ou_quotes) else "AUTH_OK_NO_QUOTES_IN_SAMPLE",
        "soccer_sport_entries": len(soccer),
        "soccer_market_definitions": len(soccer_markets),
        "btts_market_definitions": len(btts_ids),
        "over_under_market_definitions": len(ou_ids),
        "soccer_fixtures_next_36h": len(fixtures),
        "upcoming_fixtures_flagged_with_odds": len(candidates),
        "fixtures_checked": checked,
        "btts_active_price_count": btts_quotes,
        "over_under_active_price_count": ou_quotes,
        "bookmakers_seen": sorted(bookmakers_seen),
        "market_ids_with_prices": sorted(market_ids_seen),
        "historical_odds": {
            "status": historical_status,
            "fixture_id": str(past[0][1].get("fixtureId")) if isinstance(history_fixtures, list) and past else None,
            "bookmaker_count": historical_bookmakers,
            "price_rows": historical_rows,
            "timestamped_price_rows": historical_timestamped_rows,
            "created_at_min": historical_created_at_min,
            "created_at_max": historical_created_at_max,
        },
        "request_count": requests,
        "side_effects": {
            "database_writes": 0,
            "imports": 0,
            "prediction_changes": 0,
            "telegram_messages": 0,
            "deployments": 0,
        },
    }
    report["report_sha256"] = _hash(report)
    return report


def validate_report(report: dict) -> None:
    if report.get("provider") != "OddsPapi" or report.get("mode") != "read_only_soccer_quote_probe":
        raise ValueError("scope_invalid")
    if not 3 <= report.get("request_count", 0) <= 6:
        raise ValueError("request_budget_invalid")
    if report.get("side_effects", {}).get("database_writes") != 0:
        raise ValueError("side_effects_invalid")
    if report.get("report_sha256") != _hash(report):
        raise ValueError("report_hash_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase1_oddspapi.json")
    args = parser.parse_args()
    if not os.getenv("ODDSPAPI_API_KEY", "").strip():
        print("ODDSPAPI_PROBE: MISSING_SECRET")
        return 2
    try:
        report = probe(OddsPapiClient())
        validate_report(report)
    except OddsPapiError as exc:
        print(f"ODDSPAPI_PROBE: FAILED ({str(exc)[:160]})")
        return 2
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "ODDSPAPI_PROBE: "
        f"status={report['status']} "
        f"soccer_fixtures={report['soccer_fixtures_next_36h']} "
        f"btts_prices={report['btts_active_price_count']} "
        f"ou_prices={report['over_under_active_price_count']} "
        f"historical={report['historical_odds']['status']} "
        f"historical_timestamped={report['historical_odds']['timestamped_price_rows']} "
        f"requests={report['request_count']} "
        f"sha256={report['report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
