import json
from datetime import datetime, timezone

import pytest

from veltrix_v2.ingestion.providers.five_dollar import (
    ProviderLeagueRedirect,
    ProviderResponseError,
    parse_fixture_batch,
)
from veltrix_v2.ingestion.ports import ProviderRequestSpec


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def request(parameters=None):
    return ProviderRequestSpec(
        request_id="req-1", provider="5DollarFootballAPI",
        endpoint="league_fixtures", data_class="fixtures",
        quota_scope="hourly", quota_units=1, competition_ids=("league-1",),
        history_start_date=None, idempotency_key="req-1",
        parameters=parameters or {"page": 1, "per_page": 100},
    )


def payload():
    return {
        "success": 1,
        "data": [{
            "id": 987, "league": {"id": 55, "name": "Example League"},
            "teams": {
                "home": {"id": 11, "name": "Home FC"},
                "away": {"id": 22, "name": "Away FC"},
            },
            "kickoff_utc": "2026-11-06T15:00:00+00:00",
            "status": "scheduled", "goals": {"home": None, "away": None},
        }],
        "pagination": {"page": 1, "per_page": 100, "count": 1, "has_more": False},
    }


def test_parser_preserves_provider_fixture_competition_and_team_ids():
    raw = json.dumps(payload(), separators=(",", ":")).encode()
    parsed = parse_fixture_batch(
        request(), http_status=200,
        headers={"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "58"},
        raw_body=raw, fetched_at_utc=NOW,
    )
    record = parsed.response.records[0]
    assert record.provider_fixture_id == "987"
    assert record.provider_competition_id == "55"
    assert record.provider_home_team_id == "11"
    assert record.provider_away_team_id == "22"
    assert record.raw_payload == raw
    assert parsed.quota_headers.remaining == 58


def test_parser_retains_pagination_metadata():
    parsed = parse_fixture_batch(
        request(), http_status=200, headers={},
        raw_body=json.dumps(payload()).encode(), fetched_at_utc=NOW,
    )
    assert parsed.pagination_page == 1
    assert parsed.pagination_per_page == 100
    assert parsed.has_more is False


def test_parser_rejects_incomplete_source_identity_instead_of_dropping_row():
    data = payload()
    data["data"][0]["teams"]["away"].pop("id")
    with pytest.raises(ProviderResponseError, match="IDENTITY_INCOMPLETE"):
        parse_fixture_batch(
            request(), http_status=200, headers={},
            raw_body=json.dumps(data).encode(), fetched_at_utc=NOW,
        )


def test_parser_classifies_rate_limit_and_retry_after():
    with pytest.raises(ProviderResponseError) as caught:
        parse_fixture_batch(
            request(), http_status=429, headers={"Retry-After": "30"},
            raw_body=b'{"success":0}', fetched_at_utc=NOW,
        )
    assert caught.value.retryable is True
    assert caught.value.retry_after_seconds == 30


@pytest.mark.parametrize("status", [401, 403])
def test_parser_does_not_mark_auth_or_plan_errors_retryable(status):
    with pytest.raises(ProviderResponseError) as caught:
        parse_fixture_batch(
            request(), http_status=status, headers={},
            raw_body=b'{"success":0}', fetched_at_utc=NOW,
        )
    assert caught.value.retryable is False


def test_parser_marks_server_error_retryable():
    with pytest.raises(ProviderResponseError) as caught:
        parse_fixture_batch(
            request(), http_status=503, headers={},
            raw_body=b"unavailable", fetched_at_utc=NOW,
        )
    assert caught.value.retryable is True


def test_parser_preserves_retired_league_id_and_canonical_redirect():
    body = {"error": {"code": "league_moved", "canonical_id": 99}}
    with pytest.raises(ProviderLeagueRedirect) as caught:
        parse_fixture_batch(
            request({"league_id": 55}), http_status=301, headers={},
            raw_body=json.dumps(body).encode(), fetched_at_utc=NOW,
        )
    assert caught.value.old_provider_competition_id == "55"
    assert caught.value.canonical_provider_competition_id == "99"


def test_parser_rejects_invalid_json():
    with pytest.raises(ProviderResponseError, match="INVALID_JSON"):
        parse_fixture_batch(
            request(), http_status=200, headers={},
            raw_body=b"{", fetched_at_utc=NOW,
        )


def test_parser_rejects_naive_fetch_timestamp():
    with pytest.raises(ProviderResponseError, match="TIMEZONE_AWARE"):
        parse_fixture_batch(
            request(), http_status=200, headers={},
            raw_body=json.dumps(payload()).encode(),
            fetched_at_utc=datetime(2026, 11, 6),
        )
