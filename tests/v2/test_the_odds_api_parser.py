import json
from datetime import datetime, timezone

import pytest

from veltrix_v2.ingestion.ports import ProviderRequestSpec
from veltrix_v2.ingestion.providers.the_odds_api import parse_event_odds_batch
from veltrix_v2.ingestion.providers.five_dollar import ProviderResponseError


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def request(quota_units=10):
    return ProviderRequestSpec(
        request_id="odds-1", provider="The Odds API", endpoint="sport_odds",
        data_class="odds", quota_scope="monthly_credits", quota_units=quota_units,
        competition_ids=("soccer_england_premier_league",),
        history_start_date=None, idempotency_key="odds-1", parameters={"regions": "uk", "markets": "h2h,totals"},
    )


def payload():
    return [{
        "id": "event-1", "sport_key": "soccer_england_premier_league",
        "commence_time": "2026-11-06T15:00:00Z",
        "home_team": "Home FC", "away_team": "Away FC",
        "bookmakers": [{
            "key": "book-a", "title": "Book A", "last_update": "2026-11-06T08:59:00Z",
            "markets": [
                {"key": "h2h", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [{"name": "Home FC", "price": 1.9}, {"name": "Draw", "price": 3.2}, {"name": "Away FC", "price": 4.1}]},
                {"key": "totals", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [{"name": "Over", "price": 1.8, "point": 2.5}, {"name": "Under", "price": 2.0, "point": 2.5}]},
            ],
        }],
    }]


def test_parser_preserves_event_id_sport_and_exact_raw_bytes():
    raw = json.dumps(payload(), separators=(",", ":")).encode()
    parsed = parse_event_odds_batch(
        request(), http_status=200,
        headers={"x-requests-last": "10", "x-requests-remaining": "490", "x-requests-used": "10"},
        raw_body=raw, fetched_at_utc=NOW,
    )
    record = parsed.response.records[0]
    assert record.provider_fixture_id == "event-1"
    assert record.provider_competition_id == "soccer_england_premier_league"
    assert record.raw_payload == raw
    assert parsed.response.quota_units_consumed == 10
    assert parsed.quota_headers.cost_observed is True
    assert parsed.market_keys_seen == ("h2h", "totals")


def test_parser_does_not_assume_btts_market_exists():
    parsed = parse_event_odds_batch(
        request(), http_status=200, headers={},
        raw_body=json.dumps(payload()).encode(), fetched_at_utc=NOW,
    )
    assert "btts" not in parsed.market_keys_seen


def test_parser_uses_reserved_estimate_when_cost_header_is_missing():
    parsed = parse_event_odds_batch(
        request(quota_units=12), http_status=200, headers={},
        raw_body=json.dumps(payload()).encode(), fetched_at_utc=NOW,
    )
    assert parsed.response.quota_units_consumed == 12
    assert parsed.quota_headers.cost_observed is False


def test_parser_rejects_event_without_provider_identity():
    invalid = payload()
    invalid[0].pop("id")
    with pytest.raises(ProviderResponseError, match="IDENTITY_INCOMPLETE"):
        parse_event_odds_batch(
            request(), http_status=200, headers={},
            raw_body=json.dumps(invalid).encode(), fetched_at_utc=NOW,
        )


def test_parser_rejects_non_list_response():
    with pytest.raises(ProviderResponseError, match="NOT_LIST"):
        parse_event_odds_batch(
            request(), http_status=200, headers={},
            raw_body=b"{}", fetched_at_utc=NOW,
        )


def test_parser_classifies_credit_rate_limit_and_retry_after():
    with pytest.raises(ProviderResponseError) as caught:
        parse_event_odds_batch(
            request(), http_status=429, headers={"Retry-After": "60"},
            raw_body=b"{}", fetched_at_utc=NOW,
        )
    assert caught.value.retryable is True
    assert caught.value.retry_after_seconds == 60


def test_parser_does_not_retry_auth_or_plan_errors():
    with pytest.raises(ProviderResponseError) as caught:
        parse_event_odds_batch(
            request(), http_status=403, headers={},
            raw_body=b"{}", fetched_at_utc=NOW,
        )
    assert caught.value.retryable is False


def test_parser_rejects_naive_timestamp():
    with pytest.raises(ProviderResponseError, match="TIMEZONE_AWARE"):
        parse_event_odds_batch(
            request(), http_status=200, headers={},
            raw_body=json.dumps(payload()).encode(),
            fetched_at_utc=datetime(2026, 11, 6),
        )
