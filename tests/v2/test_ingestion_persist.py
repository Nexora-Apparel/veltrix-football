from datetime import datetime, timezone

from veltrix_v2.domain.contracts import DataUsePurpose, RightsStatus, SourceRights
from veltrix_v2.ingestion.persist import persist_provider_batch
from veltrix_v2.ingestion.ports import (
    ProviderBatchResponse,
    ProviderRequestSpec,
    RawProviderRecord,
    StoredSourceRecord,
)


FETCHED = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
INGESTED = datetime(2026, 11, 6, 9, 1, tzinfo=timezone.utc)


class MemoryRecordRepository:
    def __init__(self):
        self.calls = []

    def persist_accepted_record(self, accepted, *, raw_payload, ingestion_run_id, idempotency_key):
        self.calls.append((accepted, raw_payload, ingestion_run_id, idempotency_key))
        record = accepted.record
        return StoredSourceRecord(
            source_record_id=record.provider_record_id,
            payload_reference=record.payload_reference,
            raw_payload_sha256=record.raw_payload_sha256,
            duplicate=False,
        )


def request(quota_units=2, competitions=("league-1",)):
    return ProviderRequestSpec(
        request_id="request-1", provider="5DollarFootballAPI", endpoint="fixtures",
        data_class="fixtures", quota_scope="hourly", quota_units=quota_units,
        competition_ids=competitions, history_start_date=None,
        idempotency_key="sync-2026-11-06-league-1", parameters={},
    )


def raw(record_id="record-1", data_class="fixtures", competition="league-1"):
    return RawProviderRecord(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_record_id=record_id, provider_fixture_id="fixture-1",
        provider_competition_id=competition, data_class=data_class,
        raw_payload=b'{"id":1}',
    )


def response(records=(raw(),), quota_units=1):
    return ProviderBatchResponse(
        request_id="request-1", provider="5DollarFootballAPI",
        fetched_at_utc=FETCHED, records=records,
        quota_units_consumed=quota_units,
    )


def rights(uses=None):
    permitted = uses or {DataUsePurpose.INFERENCE, DataUsePurpose.CACHE}
    return SourceRights(
        source_id="five-dollar", rights_status=RightsStatus.VERIFIED,
        commercial_use_allowed=True, permitted_uses=frozenset(permitted),
        terms_url="https://provider.example/terms", terms_version="2026-11",
        verified_at_utc=FETCHED, evidence_sha256="b" * 64,
    )


def test_batch_persists_exact_bytes_and_original_provider_ids():
    repository = MemoryRecordRepository()
    result = persist_provider_batch(
        request(), response(), {"five-dollar": rights()}, repository,
        ingestion_run_id="run-1", ingested_at_utc=INGESTED,
        purpose=DataUsePurpose.INFERENCE,
    )
    assert len(result.accepted) == 1
    accepted = repository.calls[0][0]
    assert accepted.record.provider_fixture_id == "fixture-1"
    assert repository.calls[0][1] == b'{"id":1}'
    assert repository.calls[0][3] == "sync-2026-11-06-league-1:record-1"


def test_batch_rejects_missing_rights_without_persisting():
    repository = MemoryRecordRepository()
    result = persist_provider_batch(
        request(), response(), {}, repository,
        ingestion_run_id="run-1", ingested_at_utc=INGESTED,
        purpose=DataUsePurpose.INFERENCE,
    )
    assert result.rejected[0].reason_code == "SOURCE_RIGHTS_MISSING"
    assert repository.calls == []


def test_batch_rejects_unpermitted_cache_use():
    repository = MemoryRecordRepository()
    result = persist_provider_batch(
        request(), response(), {"five-dollar": rights({DataUsePurpose.INFERENCE})},
        repository, ingestion_run_id="run-1", ingested_at_utc=INGESTED,
        purpose=DataUsePurpose.INFERENCE,
    )
    assert result.rejected[0].reason_code == "PURPOSE_NOT_PERMITTED"
    assert repository.calls == []


def test_batch_rejects_data_class_outside_request():
    repository = MemoryRecordRepository()
    result = persist_provider_batch(
        request(), response((raw(data_class="odds"),)), {"five-dollar": rights()},
        repository, ingestion_run_id="run-1", ingested_at_utc=INGESTED,
        purpose=DataUsePurpose.INFERENCE,
    )
    assert result.rejected[0].reason_code == "DATA_CLASS_MISMATCH"


def test_batch_rejects_competition_outside_request():
    repository = MemoryRecordRepository()
    result = persist_provider_batch(
        request(), response((raw(competition="league-2"),)), {"five-dollar": rights()},
        repository, ingestion_run_id="run-1", ingested_at_utc=INGESTED,
        purpose=DataUsePurpose.INFERENCE,
    )
    assert result.rejected[0].reason_code == "COMPETITION_OUTSIDE_REQUEST_SCOPE"


def test_batch_rejects_request_id_mismatch():
    repository = MemoryRecordRepository()
    wrong = ProviderBatchResponse(
        request_id="other", provider="5DollarFootballAPI",
        fetched_at_utc=FETCHED, records=(raw(),), quota_units_consumed=1,
    )
    try:
        persist_provider_batch(
            request(), wrong, {"five-dollar": rights()}, repository,
            ingestion_run_id="run-1", ingested_at_utc=INGESTED,
            purpose=DataUsePurpose.INFERENCE,
        )
    except ValueError as exc:
        assert "request_id" in str(exc)
    else:
        raise AssertionError("mismatched request ID must be rejected")


def test_batch_rejects_quota_cost_above_reserved_units():
    repository = MemoryRecordRepository()
    try:
        persist_provider_batch(
            request(quota_units=1), response(quota_units=2),
            {"five-dollar": rights()}, repository,
            ingestion_run_id="run-1", ingested_at_utc=INGESTED,
            purpose=DataUsePurpose.INFERENCE,
        )
    except ValueError as exc:
        assert "quota" in str(exc)
    else:
        raise AssertionError("quota overrun must be rejected")


def test_batch_rejects_naive_ingestion_timestamp():
    repository = MemoryRecordRepository()
    try:
        persist_provider_batch(
            request(), response(), {"five-dollar": rights()}, repository,
            ingestion_run_id="run-1", ingested_at_utc=datetime(2026, 11, 6),
            purpose=DataUsePurpose.INFERENCE,
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive timestamp must be rejected")


def test_batch_continues_after_a_record_level_scope_rejection():
    repository = MemoryRecordRepository()
    result = persist_provider_batch(
        request(), response((raw("bad", competition="wrong"), raw("good"))),
        {"five-dollar": rights()}, repository,
        ingestion_run_id="run-1", ingested_at_utc=INGESTED,
        purpose=DataUsePurpose.INFERENCE,
    )
    assert len(result.accepted) == 1
    assert len(result.rejected) == 1
    assert result.accepted[0].source_record_id == "good"
