from datetime import datetime, timezone
import hashlib
import json

import pytest

from veltrix_v2.providers.odds_api_v4.parser import parse_bulk_odds, parse_event_odds


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def body(markets):
    return json.dumps([{
        "id": "event-1", "bookmakers": [{
            "key": "book-a", "title": "Book A", "last_update": "deprecated",
            "markets": markets,
        }]
    }]).encode()


def test_h2h_preserves_all_outcomes_and_uses_market_timestamp():
    raw = body([{"key": "h2h", "last_update": "2026-11-13T11:00:00Z",
                 "outcomes": [{"name": "Away", "price": 3.2},
                              {"name": "Draw", "price": 3.1},
                              {"name": "Home", "price": 2.2}]}])
    result = parse_bulk_odds(raw, sport_key="soccer_test", retrieved_at=NOW)
    assert [x.selection_name for x in result.observations] == ["Away", "Draw", "Home"]
    assert all(x.source_published_at.isoformat() == "2026-11-13T11:00:00+00:00" for x in result.observations)
    assert all(x.response_sha256 == hashlib.sha256(raw).hexdigest() for x in result.observations)


def test_totals_preserves_each_line_and_selection():
    raw = body([{"key": "totals", "last_update": "2026-11-13T11:00:00Z",
                 "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5},
                              {"name": "Under", "price": 1.9, "point": 2.5},
                              {"name": "Over", "price": 2.1, "point": 3.5}]}])
    parsed = parse_bulk_odds(raw, sport_key="soccer_test", retrieved_at=NOW)
    assert [(x.selection_name, x.point) for x in parsed.observations] == [
        ("Over", 2.5), ("Under", 2.5), ("Over", 3.5)]


def test_invalid_timestamp_is_not_replaced_with_retrieval_time():
    parsed = parse_bulk_odds(body([{"key": "h2h", "last_update": "2026-11-13T11:00:00",
                                    "outcomes": [{"name": "Home", "price": 2}]}]),
                             sport_key="soccer_test", retrieved_at=NOW)
    assert parsed.observations[0].source_published_at is None
    assert not parsed.observations[0].eligible_timestamp
    assert parsed.observations[0].retrieved_at == NOW
    assert parsed.diagnostics[0].code == "MARKET_TIMESTAMP_MISSING_OR_UNTRUSTED"


def test_bad_prices_and_totals_points_are_rejected():
    raw = body([{"key": "totals", "last_update": "2026-11-13T11:00:00Z",
                 "outcomes": [{"name": "Over", "price": float("nan"), "point": 2.5},
                              {"name": "Under", "price": 1.8, "point": None}]}])
    parsed = parse_bulk_odds(raw, sport_key="soccer_test", retrieved_at=NOW)
    assert not parsed.observations
    assert {d.code for d in parsed.diagnostics} == {"PRICE_INVALID", "TOTALS_POINT_INVALID"}


def test_event_btts_requires_exact_event_id_and_preserves_yes_no():
    raw = body([{"key": "btts", "last_update": "2026-11-13T11:00:00Z",
                 "outcomes": [{"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.0}]}])
    parsed = parse_event_odds(raw, sport_key="soccer_test", event_id="event-1", retrieved_at=NOW)
    assert [x.selection_name for x in parsed.observations] == ["Yes", "No"]
    mismatch = parse_event_odds(raw, sport_key="soccer_test", event_id="other", retrieved_at=NOW)
    assert not mismatch.observations
    assert mismatch.diagnostics[0].code == "EVENT_ID_MISMATCH"


def test_malformed_json_and_naive_retrieval_fail_closed():
    with pytest.raises(ValueError, match="ODDS_RESPONSE_INVALID_JSON"):
        parse_bulk_odds(b"{", sport_key="soccer", retrieved_at=NOW)
    with pytest.raises(ValueError, match="RETRIEVED_AT_MUST_BE_TIMEZONE_AWARE"):
        parse_bulk_odds(b"[]", sport_key="soccer", retrieved_at=datetime(2026, 1, 1))


def test_duplicate_identical_rows_are_diagnosed():
    market = {"key": "h2h", "last_update": "2026-11-13T11:00:00Z",
              "outcomes": [{"name": "Home", "price": 2.0}, {"name": "Home", "price": 2.0}]}
    parsed = parse_bulk_odds(body([market]), sport_key="soccer", retrieved_at=NOW)
    assert len(parsed.observations) == 2
    assert "DUPLICATE_QUOTE_ROW" in {d.code for d in parsed.diagnostics}
