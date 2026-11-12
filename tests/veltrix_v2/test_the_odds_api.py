from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from email.message import Message
from urllib.error import HTTPError
import json

import pytest

from veltrix_v2.providers.the_odds_api import (
    TheOddsProviderError,
    fetch_event_btts_odds,
    parse_event_btts_odds,
)

UTC = timezone.utc
CAPTURE = datetime(2026, 11, 12, 5, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)
EVENT = {
    "id": "event-123",
    "commence_time": "2026-11-12T19:00:00Z",
    "bookmakers": [
        {
            "key": "bet365",
            "markets": [{
                "key": "btts",
                "last_update": "2026-11-12T04:58:00Z",
                "outcomes": [{"name": "Yes", "price": 1.85}, {"name": "No", "price": 1.95}],
            }],
        },
        {
            "key": "pinnacle",
            "markets": [{
                "key": "btts",
                "last_update": "2026-11-12T04:59:00Z",
                "outcomes": [{"name": "Yes", "price": 1.90}, {"name": "No", "price": 1.90}],
            }],
        },
    ],
}


def test_parser_emits_complete_btts_quotes_with_provider_timestamps():
    result = parse_event_btts_odds(
        [EVENT], fixture_id="fixture-1", provider_event_id="event-123",
        sport_key="soccer_epl", kickoff_at=KICKOFF, captured_at=CAPTURE,
    )
    assert len(result.snapshots) == 4
    assert {row.bookmaker_id for row in result.snapshots} == {"bet365", "pinnacle"}
    assert {row.selection for row in result.snapshots} == {"YES", "NO"}
    assert all(row.market == "BTTS" for row in result.snapshots)
    assert all(row.provider_event_id == "event-123" for row in result.snapshots)
    assert all(row.provider_quote_at is not None for row in result.snapshots)


def test_parser_skips_incomplete_bookmaker_market():
    body = dict(EVENT)
    body["bookmakers"] = [{
        "key": "bet365",
        "markets": [{
            "key": "btts",
            "last_update": "2026-11-12T04:58:00Z",
            "outcomes": [{"name": "Yes", "price": 1.85}],
        }],
    }]
    result = parse_event_btts_odds(
        body, fixture_id="fixture-1", provider_event_id="event-123",
        sport_key="soccer_epl", kickoff_at=KICKOFF, captured_at=CAPTURE,
    )
    assert result.snapshots == ()
    assert result.missing_bookmakers == ("bet365",)


def test_parser_rejects_wrong_event_and_kickoff():
    with pytest.raises(ValueError, match="EVENT_NOT_FOUND"):
        parse_event_btts_odds(
            [], fixture_id="fixture-1", provider_event_id="event-123",
            sport_key="soccer_epl", kickoff_at=KICKOFF, captured_at=CAPTURE,
        )
    wrong = dict(EVENT, commence_time="2026-11-12T20:00:00Z")
    with pytest.raises(ValueError, match="KICKOFF_MISMATCH"):
        parse_event_btts_odds(
            wrong, fixture_id="fixture-1", provider_event_id="event-123",
            sport_key="soccer_epl", kickoff_at=KICKOFF, captured_at=CAPTURE,
        )


class FakeResponse:
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


def test_client_uses_event_btts_endpoint_and_records_quota_headers():
    seen = {}
    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        headers = Message()
        headers["x-requests-remaining"] = "297"
        headers["x-requests-used"] = "203"
        headers["x-requests-last"] = "1"
        return FakeResponse(json.dumps(EVENT).encode(), headers)
    result = fetch_event_btts_odds(
        api_key="secret",
        sport_key="soccer_epl",
        event_id="event-123",
        fixture_id="fixture-1",
        kickoff_at=KICKOFF,
        captured_at=CAPTURE,
        opener=opener,
    )
    assert "/sports/soccer_epl/events/event-123/odds" in seen["url"]
    assert "apiKey=secret" in seen["url"]
    assert result.requests_remaining == 297
    assert result.last_request_cost == 1
    assert len(result.snapshots) == 4


def test_client_maps_quota_limit_without_retrying():
    headers = Message()
    headers["Retry-After"] = "60"
    def opener(request, timeout):
        raise HTTPError(request.full_url, 429, "quota", headers, BytesIO(b""))
    with pytest.raises(TheOddsProviderError) as caught:
        fetch_event_btts_odds(
            api_key="key", sport_key="soccer_epl", event_id="event-123",
            fixture_id="fixture-1", kickoff_at=KICKOFF,
            captured_at=CAPTURE, opener=opener,
        )
    assert caught.value.status_code == 429
    assert caught.value.code == "THE_ODDS_QUOTA_OR_RATE_LIMIT"
    assert caught.value.retry_after == "60"



def test_parser_rejects_missing_or_mismatched_event_identity_and_kickoff():
    missing_id = dict(EVENT)
    missing_id.pop("id")
    with pytest.raises(ValueError, match="EVENT_NOT_FOUND"):
        parse_event_btts_odds(
            missing_id, fixture_id="fixture-1", provider_event_id="event-123",
            sport_key="soccer_epl", kickoff_at=KICKOFF, captured_at=CAPTURE,
        )
    missing_kickoff = dict(EVENT)
    missing_kickoff.pop("commence_time")
    with pytest.raises(ValueError, match="KICKOFF_TIMESTAMP_MISSING"):
        parse_event_btts_odds(
            missing_kickoff, fixture_id="fixture-1", provider_event_id="event-123",
            sport_key="soccer_epl", kickoff_at=KICKOFF, captured_at=CAPTURE,
        )


def test_parser_rejects_quote_timestamp_after_capture():
    future_quote = {
        **EVENT,
        "bookmakers": [{
            "key": "bet365",
            "markets": [{
                "key": "btts",
                "last_update": "2026-11-12T05:01:00Z",
                "outcomes": [{"name": "Yes", "price": 1.85}, {"name": "No", "price": 1.95}],
            }],
        }],
    }
    with pytest.raises(ValueError, match="QUOTE_TIMESTAMP_AFTER_CAPTURE"):
        parse_event_btts_odds(
            future_quote, fixture_id="fixture-1", provider_event_id="event-123",
            sport_key="soccer_epl", kickoff_at=KICKOFF, captured_at=CAPTURE,
        )



def test_parser_propagates_source_observation_identity_to_each_quote():
    result = parse_event_btts_odds(
        [EVENT],
        fixture_id="fixture-1",
        provider_event_id="event-123",
        sport_key="soccer_epl",
        kickoff_at=KICKOFF,
        captured_at=CAPTURE,
        source_observation_id="obs-odds-api-event-123",
    )
    assert len(result.snapshots) == 4
    assert {
        row.source_observation_id for row in result.snapshots
    } == {"obs-odds-api-event-123"}


def test_parser_rejects_blank_source_observation_identity():
    with pytest.raises(ValueError, match="SOURCE_OBSERVATION_ID_INVALID"):
        parse_event_btts_odds(
            [EVENT],
            fixture_id="fixture-1",
            provider_event_id="event-123",
            sport_key="soccer_epl",
            kickoff_at=KICKOFF,
            captured_at=CAPTURE,
            source_observation_id=" ",
        )
