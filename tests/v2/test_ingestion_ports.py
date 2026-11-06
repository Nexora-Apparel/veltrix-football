from datetime import datetime, timezone
from hashlib import sha256

import pytest

from veltrix_v2.ingestion.ports import (
    ProviderBatchResponse,
    ProviderRequestSpec,
    QuotaReservation,
    RawProviderRecord,
    StoredSourceRecord,
)


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def raw_record(payload=b'{"fixture":1}'):
    return RawProviderRecord(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_record_id="record-1", provider_fixture_id="fixture-1",
        provider_competition_id="league-1", data_class="fixtures",
        raw_payload=payload,
    )


def test_request_contract_requires_bounded_cost_and_idempotency():
    request = ProviderRequestSpec(
        request_id="req-1", provider="5DollarFootballAPI", endpoint="fixtures",
        data_class="fixtures", quota_scope="daily", quota_units=1,
        competition_ids=("league-1",), history_start_date=None,
        idempotency_key="req-1", parameters={"date": "2026-11-06"},
    )
    assert request.quota_units == 1
    assert request.idempotency_key == "req-1"


@pytest.mark.parametrize("units", [0, -1])
def test_request_rejects_non_positive_quota_cost(units):
    with pytest.raises(ValueError, match="quota_units"):
        ProviderRequestSpec(
            request_id="r", provider="p", endpoint="e", data_class="fixtures",
            quota_scope="daily", quota_units=units, competition_ids=(),
            history_start_date=None, idempotency_key="r", parameters={},
        )


def test_request_rejects_duplicate_competitions():
    with pytest.raises(ValueError, match="unique"):
        ProviderRequestSpec(
            request_id="r", provider="p", endpoint="e", data_class="fixtures",
            quota_scope="daily", quota_units=1, competition_ids=("l1", "l1"),
            history_start_date=None, idempotency_key="r", parameters={},
        )


def test_request_parameters_are_immutable_and_scalar_only():
    request = ProviderRequestSpec(
        request_id="r", provider="p", endpoint="e", data_class="fixtures",
        quota_scope="daily", quota_units=1, competition_ids=(),
        history_start_date=None, idempotency_key="r", parameters={"limit": 10},
    )
    with pytest.raises(TypeError):
        request.parameters["limit"] = 20
    with pytest.raises(ValueError, match="scalar"):
        ProviderRequestSpec(
            request_id="r", provider="p", endpoint="e", data_class="fixtures",
            quota_scope="daily", quota_units=1, competition_ids=(),
            history_start_date=None, idempotency_key="r", parameters={"ids": [1, 2]},
        )


def test_raw_record_hash_is_computed_from_exact_provider_bytes():
    payload = b'{"fixture":1}'
    assert raw_record(payload).raw_payload_sha256 == sha256(payload).hexdigest()


def test_raw_record_rejects_empty_payload():
    with pytest.raises(ValueError, match="non-empty"):
        raw_record(b"")


def test_batch_response_preserves_provider_and_fetch_timestamp():
    response = ProviderBatchResponse(
        request_id="req-1", provider="5DollarFootballAPI",
        fetched_at_utc=NOW, records=(raw_record(),), quota_units_consumed=1,
    )
    assert response.records[0].provider_fixture_id == "fixture-1"


def test_batch_response_rejects_cross_provider_record():
    other = RawProviderRecord(
        provider="other", source_id="other", provider_record_id="r2",
        provider_fixture_id=None, provider_competition_id=None,
        data_class="fixtures", raw_payload=b"{}",
    )
    with pytest.raises(ValueError, match="response provider"):
        ProviderBatchResponse(
            request_id="req-1", provider="5DollarFootballAPI",
            fetched_at_utc=NOW, records=(other,), quota_units_consumed=1,
        )


def test_batch_response_rejects_naive_fetch_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderBatchResponse(
            request_id="req-1", provider="p",
            fetched_at_utc=datetime(2026, 11, 6), records=(), quota_units_consumed=0,
        )


def test_quota_reservation_requires_idempotency_and_positive_units():
    with pytest.raises(ValueError, match="positive"):
        QuotaReservation(
            reservation_id="q1", provider="p", quota_scope="daily",
            units_reserved=0, idempotency_key="q1", reserved_at_utc=NOW,
        )


def test_stored_record_requires_payload_hash_and_reference():
    with pytest.raises(ValueError, match="payload reference"):
        StoredSourceRecord(
            source_record_id="s1", payload_reference="",
            raw_payload_sha256="a" * 64, duplicate=False,
        )
