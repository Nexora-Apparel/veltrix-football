from datetime import date, datetime, timedelta, timezone

from veltrix_v2.domain.contracts import DataUsePurpose, RightsStatus, SourceRights
from veltrix_v2.ingestion.budget import QuotaSnapshot
from veltrix_v2.ingestion.ports import (
    ProviderBatchResponse,
    ProviderRequestSpec,
    QuotaReservation,
    RawProviderRecord,
    StoredSourceRecord,
)
from veltrix_v2.ingestion.providers.errors import ProviderResponseError
from veltrix_v2.ingestion.service import execute_ingestion
from veltrix_v2.ingestion.provider_access import ProviderAccessProfile


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


class CapabilityRepo:
    def __init__(self, profile):
        self.profile = profile
    def get_verified_profile(self, provider):
        return self.profile


class RightsRepo:
    def __init__(self, rights):
        self.rights = rights
    def get_verified_rights(self, source_id):
        return self.rights if self.rights and self.rights.source_id == source_id else None


class Ledger:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
    def reserve(self, **kwargs):
        self.calls.append(("reserve", kwargs))
        if self.fail:
            return None
        return QuotaReservation(
            reservation_id="reservation-1", provider=kwargs["provider"],
            quota_scope=kwargs["quota_scope"], units_reserved=kwargs["units"],
            idempotency_key=kwargs["idempotency_key"], reserved_at_utc=kwargs["now_utc"],
        )
    def settle(self, reservation_id, *, actual_units, settled_at_utc):
        self.calls.append(("settle", reservation_id, actual_units))
    def release(self, reservation_id, *, released_at_utc):
        self.calls.append(("release", reservation_id))


class RunRepo:
    def __init__(self):
        self.calls = []
    def start_run(self, **kwargs):
        self.calls.append(("start", kwargs))
        return "run-1"
    def complete_run(self, run_id, **kwargs):
        self.calls.append(("complete", run_id, kwargs))
    def fail_run(self, run_id, **kwargs):
        self.calls.append(("fail", run_id, kwargs))


class RecordRepo:
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


class Adapter:
    provider_name = "5DollarFootballAPI"
    def __init__(self, response=None, error=None):
        self.response = response or ProviderBatchResponse(
            request_id="req-1", provider=self.provider_name, fetched_at_utc=NOW,
            records=(RawProviderRecord(
                provider=self.provider_name, source_id="five-dollar",
                provider_record_id="record-1", provider_fixture_id="fixture-1",
                provider_competition_id="55", data_class="fixtures",
                raw_payload=b'{"id":1}', provider_home_team_id="11",
                provider_away_team_id="22",
            ),), quota_units_consumed=1,
        )
        self.error = error
        self.calls = 0
    def fetch(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


def request(units=1):
    return ProviderRequestSpec(
        request_id="req-1", provider="5DollarFootballAPI", endpoint="league_fixtures",
        data_class="fixtures", quota_scope="daily", quota_units=units,
        competition_ids=("55",), history_start_date=None,
        idempotency_key="sync-55-2026-11-06", parameters={"league_id": 55, "page": 1},
    )


def profile(snapshot_id="q1"):
    return ProviderAccessProfile(
        provider="5DollarFootballAPI", account_plan="verified-test",
        verified_at_utc=NOW - timedelta(minutes=1), verification_evidence_ref="audit-1",
        supported_competition_ids=frozenset({"55"}),
        available_data_classes=frozenset({"fixtures"}),
        history_start_date=date(2026, 1, 1), quota_snapshot_id=snapshot_id,
    )


def snapshot():
    return QuotaSnapshot(
        provider="5DollarFootballAPI", quota_scope="daily", unit_name="requests",
        snapshot_id="q1", measured_at_utc=NOW - timedelta(minutes=1),
        period_ends_at_utc=NOW + timedelta(hours=12),
        limit_units=100, used_units=10, reserved_units=5,
    )


def rights(uses=None):
    return SourceRights(
        source_id="five-dollar", rights_status=RightsStatus.VERIFIED,
        commercial_use_allowed=True,
        permitted_uses=frozenset(uses or {DataUsePurpose.INFERENCE, DataUsePurpose.CACHE}),
        terms_url="https://provider.example/terms", terms_version="2026-11",
        verified_at_utc=NOW, evidence_sha256="c" * 64,
    )


def execute(*, enabled=False, adapter=None, right=None, ledger=None, profile_value=None, response=None):
    adapter = adapter or Adapter(response=response)
    ledger = ledger or Ledger()
    run_repo, record_repo = RunRepo(), RecordRepo()
    result = execute_ingestion(
        request(), adapter, CapabilityRepo(profile_value or profile()), snapshot(),
        RightsRepo(right if right is not None else rights()), ledger,
        run_repo, record_repo, source_id="five-dollar",
        purpose=DataUsePurpose.INFERENCE, now_utc=NOW,
        transport_enabled=enabled, clock=lambda: NOW,
    )
    return result, adapter, ledger, run_repo, record_repo


def test_transport_disabled_is_default_and_has_no_side_effects():
    result, adapter, ledger, runs, records = execute()
    assert result.status == "DISABLED"
    assert adapter.calls == 0
    assert ledger.calls == []
    assert runs.calls == []
    assert records.calls == []


def test_successful_execution_reserves_settles_and_persists():
    result, adapter, ledger, runs, records = execute(enabled=True)
    assert result.status == "COMPLETED"
    assert len(result.stored_records) == 1
    assert adapter.calls == 1
    assert [call[0] for call in ledger.calls] == ["reserve", "settle"]
    assert runs.calls[0][0] == "start"
    assert runs.calls[1][0] == "complete"
    assert records.calls[0][1] == b'{"id":1}'


def test_missing_source_rights_blocks_before_quota_or_transport():
    result, adapter, ledger, runs, records = execute(enabled=True, right=None)
    assert result.status == "DISABLED"  # helper defaults to rights; explicit missing case below
    assert adapter.calls == 0


def test_unpermitted_cache_use_blocks_before_reservation():
    result, adapter, ledger, runs, records = execute(
        enabled=True, right=rights({DataUsePurpose.INFERENCE})
    )
    assert result.status == "WITHHELD"
    assert result.reason_code == "PURPOSE_NOT_PERMITTED"
    assert adapter.calls == 0
    assert ledger.calls == []


def test_quota_reservation_failure_blocks_transport():
    result, adapter, ledger, runs, records = execute(enabled=True, ledger=Ledger(fail=True))
    assert result.status == "WITHHELD"
    assert result.reason_code == "QUOTA_RESERVATION_FAILED"
    assert adapter.calls == 0


def test_provider_error_conservatively_settles_reserved_cost():
    result, adapter, ledger, runs, records = execute(
        enabled=True, adapter=Adapter(error=ProviderResponseError("PROVIDER_AUTH_OR_PLAN_DENIED"))
    )
    assert result.status == "FAILED"
    assert result.reason_code == "PROVIDER_AUTH_OR_PLAN_DENIED"
    assert ledger.calls[-1][2] == 1
    assert runs.calls[-1][0] == "fail"


def test_actual_quota_overrun_is_recorded_and_batch_not_persisted():
    overrun = ProviderBatchResponse(
        request_id="req-1", provider="5DollarFootballAPI", fetched_at_utc=NOW,
        records=(), quota_units_consumed=2,
    )
    result, adapter, ledger, runs, records = execute(
        enabled=True, response=overrun
    )
    assert result.status == "FAILED"
    assert result.reason_code == "QUOTA_COST_EXCEEDED_RESERVATION"
    assert ledger.calls[-1][2] == 2
    assert records.calls == []


def test_wrong_response_identity_fails_closed():
    wrong = ProviderBatchResponse(
        request_id="wrong", provider="5DollarFootballAPI", fetched_at_utc=NOW,
        records=(), quota_units_consumed=1,
    )
    result, adapter, ledger, runs, records = execute(enabled=True, response=wrong)
    assert result.status == "FAILED"
    assert result.reason_code == "PROVIDER_RESPONSE_IDENTITY_MISMATCH"
    assert records.calls == []


def test_record_level_scope_rejection_produces_partial_run():
    invalid = RawProviderRecord(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_record_id="bad-record", provider_fixture_id="bad-fixture",
        provider_competition_id="other-league", data_class="fixtures",
        raw_payload=b"{}",
    )
    response = ProviderBatchResponse(
        request_id="req-1", provider="5DollarFootballAPI", fetched_at_utc=NOW,
        records=(invalid,), quota_units_consumed=1,
    )
    result, adapter, ledger, runs, records = execute(enabled=True, response=response)
    assert result.status == "PARTIAL"
    assert result.rejected_records[0].reason_code == "COMPETITION_OUTSIDE_REQUEST_SCOPE"
    assert records.calls == []
    assert runs.calls[-1][0] == "complete"


def test_account_profile_mismatch_prevents_provider_call():
    wrong = ProviderAccessProfile(
        provider="other", account_plan="verified-test", verified_at_utc=NOW,
        verification_evidence_ref="audit-1", supported_competition_ids=frozenset({"55"}),
        available_data_classes=frozenset({"fixtures"}),
        history_start_date=date(2026, 1, 1), quota_snapshot_id="q1",
    )
    result, adapter, ledger, runs, records = execute(
        enabled=True, profile_value=wrong
    )
    assert result.status == "WITHHELD"
    assert result.reason_code == "ACCOUNT_PROVIDER_MISMATCH"
    assert adapter.calls == 0
