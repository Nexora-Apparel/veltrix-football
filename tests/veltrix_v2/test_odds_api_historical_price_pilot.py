from __future__ import annotations

from datetime import datetime, timezone

from scripts.veltrix_v2.capture_odds_api_historical_price_pilot import (
    MARKET, SPORT, _market_summary, _normalize, _utc,
)


def test_pilot_uses_only_approved_la_liga_sport_key_and_three_way_market():
    assert SPORT == "soccer_spain_la_liga"
    assert MARKET == "h2h_3_way"


def test_market_summary_never_emits_prices_and_validates_three_way_outcomes():
    data = {
        "bookmakers": [
            {"key": "pinnacle", "title": "Pinnacle", "markets": [{
                "key": "h2h_3_way", "last_update": "2026-11-08T19:50:00Z",
                "outcomes": [
                    {"name": "Atletico Madrid", "price": 2.1},
                    {"name": "Draw", "price": 3.4},
                    {"name": "Barcelona", "price": 3.2},
                ],
            }]},
            {"key": "betfair_ex_eu", "title": "Betfair", "markets": [{
                "key": "h2h_3_way", "last_update": "2026-11-08T19:50:30Z",
                "outcomes": [
                    {"name": "Atletico Madrid", "price": 2.2},
                    {"name": "Draw", "price": 3.5},
                    {"name": "Barcelona", "price": 3.1},
                ],
            }]},
        ]
    }
    result = _market_summary(data, _utc("2026-11-08T20:00:00Z"), "Atletico Madrid", "Barcelona")
    assert result["bookmaker_count"] == 2
    assert result["sportsbook_count"] == 1
    assert result["exchange_count"] == 1
    assert result["complete_three_way_sportsbooks"] == 1
    assert result["post_kickoff_quote_count"] == 0
    assert result["raw_prices_in_summary"] is False
    assert all("price" not in str(item) for item in result["bookmaker_market_rows"])


def test_market_summary_flags_post_kickoff_quote_time():
    data = {"bookmakers": [{"key": "pinnacle", "title": "Pinnacle", "markets": [{
        "key": "h2h_3_way", "last_update": "2026-11-08T20:01:00Z",
        "outcomes": [
            {"name": "Atletico Madrid", "price": 2.1},
            {"name": "Draw", "price": 3.4},
            {"name": "Barcelona", "price": 3.2},
        ],
    }]}]}
    result = _market_summary(data, _utc("2026-11-08T20:00:00Z"), "Atletico Madrid", "Barcelona")
    assert result["post_kickoff_quote_count"] == 1
    assert result["complete_three_way_sportsbooks"] == 1


def test_utc_parser_requires_offset():
    assert _utc("2026-11-08T20:00:00Z").tzinfo == timezone.utc
    try:
        _utc("2026-11-08T20:00:00")
    except ValueError as exc:
        assert str(exc) == "TIMESTAMP_MUST_BE_TIMEZONE_AWARE"
    else:
        raise AssertionError("naive timestamp accepted")
