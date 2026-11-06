import json
from datetime import datetime, timezone

import pytest

from veltrix_v2.odds.normalization import normalize_event_odds


FETCHED = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def event_payload():
    return [{
        "id": "event-1", "sport_key": "soccer_england_premier_league",
        "commence_time": "2026-11-06T15:00:00Z",
        "home_team": "Home FC", "away_team": "Away FC",
        "bookmakers": [{
            "key": "book-a", "title": "Book A",
            "markets": [
                {"key": "h2h", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [
                     {"name": "Home FC", "price": 1.91},
                     {"name": "Draw", "price": 3.4},
                     {"name": "Away FC", "price": 4.2},
                 ]},
                {"key": "totals", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [
                     {"name": "Over", "price": 1.8, "point": 2.5},
                     {"name": "Under", "price": 2.0, "point": 2.5},
                 ]},
                {"key": "btts", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [
                     {"name": "Yes", "price": 1.72},
                     {"name": "No", "price": 2.1},
                 ]},
            ],
        }],
    }]


def normalize(payload=None):
    return normalize_event_odds(
        json.dumps(payload if payload is not None else event_payload()).encode(),
        provider="The Odds API", source_id="the-odds-api",
        provider_event_id="event-1",
        provider_competition_id="soccer_england_premier_league",
        source_record_id="source-record-1",
        fetched_at_utc=FETCHED,
    )


def test_extracts_all_market_quotes_without_collapsing_market_keys():
    result = normalize()
    assert len(result.quotes) == 7
    assert {quote.provider_market_key for quote in result.quotes} == {"h2h", "totals", "btts"}
    assert result.quotes[3].point == result.quotes[4].point


def test_preserves_bookmaker_event_source_and_raw_response_hash():
    result = normalize()
    quote = result.quotes[0]
    assert quote.provider_event_id == "event-1"
    assert quote.bookmaker_key == "book-a"
    assert quote.source_record_id == "source-record-1"
    assert len(quote.raw_response_sha256) == 64


def test_invalid_odds_price_is_rejected_not_coerced():
    payload = event_payload()
    payload[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = "NaN"
    result = normalize(payload)
    assert len(result.quotes) == 6
    assert result.rejected[0].reason_code == "ODDS_VALUE_NOT_FINITE"


def test_decimal_odds_at_or_below_one_are_rejected():
    payload = event_payload()
    payload[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = 1
    result = normalize(payload)
    assert any(item.reason_code == "DECIMAL_ODDS_NOT_GREATER_THAN_ONE" for item in result.rejected)


def test_future_quote_timestamp_is_rejected():
    payload = event_payload()
    payload[0]["bookmakers"][0]["markets"][0]["last_update"] = "2026-11-06T10:00:00Z"
    result = normalize(payload)
    assert any(item.reason_code == "QUOTE_TIMESTAMP_AFTER_FETCH" for item in result.rejected)


def test_provider_event_identity_must_match_requested_event():
    with pytest.raises(ValueError, match="NOT_FOUND"):
        normalize_event_odds(
            json.dumps(event_payload()).encode(),
            provider="The Odds API", source_id="the-odds-api",
            provider_event_id="wrong-event",
            provider_competition_id="soccer_england_premier_league",
            source_record_id="source-record-1", fetched_at_utc=FETCHED,
        )


def test_provider_competition_identity_must_match():
    with pytest.raises(ValueError, match="COMPETITION_ID_MISMATCH"):
        normalize_event_odds(
            json.dumps(event_payload()).encode(),
            provider="The Odds API", source_id="the-odds-api",
            provider_event_id="event-1", provider_competition_id="wrong-sport",
            source_record_id="source-record-1", fetched_at_utc=FETCHED,
        )


def test_missing_bookmaker_is_reported():
    payload = event_payload()
    payload[0]["bookmakers"][0].pop("key")
    result = normalize(payload)
    assert len(result.quotes) == 0
    assert result.rejected[0].reason_code == "BOOKMAKER_KEY_MISSING"


def test_naive_fetch_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_event_odds(
            json.dumps(event_payload()).encode(),
            provider="The Odds API", source_id="the-odds-api",
            provider_event_id="event-1",
            provider_competition_id="soccer_england_premier_league",
            source_record_id="source-record-1",
            fetched_at_utc=datetime(2026, 11, 6),
        )


def test_quote_retains_provider_event_kickoff_timestamp():
    result = normalize()
    assert result.quotes[0].kickoff_at_utc == datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)


def test_missing_event_kickoff_is_rejected():
    payload = event_payload()
    payload[0].pop("commence_time")
    with pytest.raises(ValueError, match="QUOTE_TIMESTAMP_MISSING"):
        normalize(payload)
