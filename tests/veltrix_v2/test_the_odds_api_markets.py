from datetime import datetime, timezone
from decimal import Decimal
from email.message import Message
import json

import pytest

from veltrix_v2.providers.the_odds_api_markets import (
    fetch_event_1x2_odds,
    fetch_event_totals_odds,
    parse_event_1x2_odds,
    parse_event_totals_odds,
)

UTC = timezone.utc
CAPTURE = datetime(2026, 11, 12, 5, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)
COMMON = {
    "id": "event-123",
    "commence_time": "2026-11-12T19:00:00Z",
    "home_team": "Arsenal",
    "away_team": "Chelsea",
}
SOURCE_OBSERVATION = "obs-the-odds-api-event-123"


def test_parse_complete_1x2_quotes_maps_home_draw_away_and_preserves_lineage():
    event = {
        **COMMON,
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "h2h",
                "last_update": "2026-11-12T04:59:00Z",
                "outcomes": [
                    {"name": "Arsenal", "price": 2.1},
                    {"name": "Draw", "price": 3.4},
                    {"name": "Chelsea", "price": 3.6},
                ],
            }],
        }],
    }
    rows = parse_event_1x2_odds(
        event, fixture_id="fixture-1", provider_event_id="event-123",
        kickoff_at=KICKOFF, captured_at=CAPTURE,
        source_observation_id=SOURCE_OBSERVATION,
    )
    assert len(rows) == 3
    assert {row.selection for row in rows} == {"HOME", "DRAW", "AWAY"}
    assert {row.market for row in rows} == {"1X2"}
    assert all(row.line is None for row in rows)
    assert all(row.provider_quote_at == datetime(2026, 11, 12, 4, 59, tzinfo=UTC) for row in rows)
    assert {row.source_observation_id for row in rows} == {SOURCE_OBSERVATION}
    assert len({row.snapshot_id for row in rows}) == 3


def test_1x2_parser_rejects_incomplete_or_ambiguous_selection_groups():
    incomplete = {
        **COMMON,
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "h2h",
                "last_update": "2026-11-12T04:59:00Z",
                "outcomes": [
                    {"name": "Arsenal", "price": 2.1},
                    {"name": "Draw", "price": 3.4},
                ],
            }],
        }],
    }
    assert parse_event_1x2_odds(
        incomplete, fixture_id="fixture-1", provider_event_id="event-123",
        kickoff_at=KICKOFF, captured_at=CAPTURE,
        source_observation_id=SOURCE_OBSERVATION,
    ) == ()

    duplicate = {
        **COMMON,
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "h2h",
                "last_update": "2026-11-12T04:59:00Z",
                "outcomes": [
                    {"name": "Arsenal", "price": 2.1},
                    {"name": "Arsenal", "price": 2.2},
                    {"name": "Draw", "price": 3.4},
                    {"name": "Chelsea", "price": 3.6},
                ],
            }],
        }],
    }
    with pytest.raises(ValueError, match="DUPLICATE_SELECTION"):
        parse_event_1x2_odds(
            duplicate, fixture_id="fixture-1", provider_event_id="event-123",
            kickoff_at=KICKOFF, captured_at=CAPTURE,
            source_observation_id=SOURCE_OBSERVATION,
        )


def test_totals_parser_keeps_complete_over_under_pairs_by_exact_line():
    event = {
        **COMMON,
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "totals",
                "last_update": "2026-11-12T04:58:00Z",
                "outcomes": [
                    {"name": "Over", "point": 2.5, "price": 1.91},
                    {"name": "Under", "point": 2.5, "price": 1.95},
                    {"name": "Over", "point": 3.5, "price": 2.6},
                    {"name": "Under", "point": 3.5, "price": 1.5},
                    {"name": "Over", "point": 4.5, "price": 4.0},
                ],
            }],
        }],
    }
    rows = parse_event_totals_odds(
        event, fixture_id="fixture-1", provider_event_id="event-123",
        kickoff_at=KICKOFF, captured_at=CAPTURE,
        source_observation_id=SOURCE_OBSERVATION,
    )
    assert len(rows) == 4
    assert {row.line for row in rows} == {Decimal("2.5"), Decimal("3.5")}
    assert {(row.line, row.selection) for row in rows} == {
        (Decimal("2.5"), "OVER"), (Decimal("2.5"), "UNDER"),
        (Decimal("3.5"), "OVER"), (Decimal("3.5"), "UNDER"),
    }
    assert all(row.market == "TOTALS" for row in rows)
    assert all(row.source_observation_id == SOURCE_OBSERVATION for row in rows)


def test_totals_parser_rejects_duplicate_selection_for_a_line():
    event = {
        **COMMON,
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "totals",
                "last_update": "2026-11-12T04:58:00Z",
                "outcomes": [
                    {"name": "Over", "point": 2.5, "price": 1.91},
                    {"name": "Over", "point": 2.5, "price": 1.92},
                    {"name": "Under", "point": 2.5, "price": 1.95},
                ],
            }],
        }],
    }
    with pytest.raises(ValueError, match="TOTALS_DUPLICATE_SELECTION"):
        parse_event_totals_odds(
            event, fixture_id="fixture-1", provider_event_id="event-123",
            kickoff_at=KICKOFF, captured_at=CAPTURE,
            source_observation_id=SOURCE_OBSERVATION,
        )


@pytest.mark.parametrize(
    ("function", "payload", "kwargs", "message"),
    [
        (
            parse_event_1x2_odds,
            COMMON,
            {"source_observation_id": " "},
            "SOURCE_OBSERVATION_ID_REQUIRED",
        ),
        (
            parse_event_totals_odds,
            COMMON,
            {"source_observation_id": SOURCE_OBSERVATION},
            "EVENT_KICKOFF_TIMESTAMP_MISSING",
        ),
    ],
)
def test_parsers_fail_closed_on_missing_provenance_or_event_time(function, payload, kwargs, message):
    args = {
        "fixture_id": "fixture-1",
        "provider_event_id": "event-123",
        "kickoff_at": KICKOFF,
        "captured_at": CAPTURE,
        "source_observation_id": SOURCE_OBSERVATION,
    }
    args.update(kwargs)
    with pytest.raises(ValueError, match=message):
        function(payload, **args)


def test_parsers_reject_provider_quote_timestamp_after_capture():
    event = {
        **COMMON,
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "h2h",
                "last_update": "2026-11-12T05:01:00Z",
                "outcomes": [
                    {"name": "Arsenal", "price": 2.1},
                    {"name": "Draw", "price": 3.4},
                    {"name": "Chelsea", "price": 3.6},
                ],
            }],
        }],
    }
    with pytest.raises(ValueError, match="QUOTE_TIMESTAMP_OUT_OF_RANGE"):
        parse_event_1x2_odds(
            event, fixture_id="fixture-1", provider_event_id="event-123",
            kickoff_at=KICKOFF, captured_at=CAPTURE,
            source_observation_id=SOURCE_OBSERVATION,
        )



class FakeResponse:
    def __init__(self, body, headers):
        self.body = body
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


@pytest.mark.parametrize(
    ("fetcher", "market_key", "payload", "expected_market", "expected_rows"),
    [
        (
            fetch_event_1x2_odds,
            "h2h",
            {
                **COMMON,
                "bookmakers": [{
                    "key": "pinnacle",
                    "markets": [{
                        "key": "h2h",
                        "last_update": "2026-11-12T04:59:00Z",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Draw", "price": 3.4},
                            {"name": "Chelsea", "price": 3.6},
                        ],
                    }],
                }],
            },
            "1X2",
            3,
        ),
        (
            fetch_event_totals_odds,
            "totals",
            {
                **COMMON,
                "bookmakers": [{
                    "key": "pinnacle",
                    "markets": [{
                        "key": "totals",
                        "last_update": "2026-11-12T04:59:00Z",
                        "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 1.9},
                            {"name": "Under", "point": 2.5, "price": 1.9},
                        ],
                    }],
                }],
            },
            "TOTALS",
            2,
        ),
    ],
)
def test_fetcher_requests_one_market_and_records_quota_headers(
    fetcher, market_key, payload, expected_market, expected_rows
):
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        headers = Message()
        headers["x-requests-remaining"] = "298"
        headers["x-requests-used"] = "202"
        headers["x-requests-last"] = "1"
        return FakeResponse(json.dumps(payload).encode("utf-8"), headers)

    result = fetcher(
        api_key="secret",
        sport_key="soccer_epl",
        event_id="event-123",
        fixture_id="fixture-1",
        kickoff_at=KICKOFF,
        captured_at=CAPTURE,
        source_observation_id=SOURCE_OBSERVATION,
        opener=opener,
    )
    assert f"markets={market_key}" in seen["url"]
    assert "apiKey=secret" in seen["url"]
    assert result.market == expected_market
    assert len(result.snapshots) == expected_rows
    assert result.requests_remaining == 298
    assert result.requests_used == 202
    assert result.last_request_cost == 1
    assert all(row.source_observation_id == SOURCE_OBSERVATION for row in result.snapshots)
