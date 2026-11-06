"""Fail-closed ingestion orchestration across capability, rights and quota gates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from veltrix_v2.domain.contracts import DataUsePurpose, RightsDecision, SourceRights
from veltrix_v2.domain.rights import evaluate_source_use
from veltrix_v2.ingestion.budget import QuotaSnapshot
from veltrix_v2.ingestion.persist import (
    BatchPersistenceResult,
    RejectedProviderRecord,
    persist_provider_batch,
)
from veltrix_v2.ingestion.ports import (
    IngestionRunRepository,
    ProviderAdapter,
    ProviderBatchResponse,
    ProviderCapabilityRepository,
    ProviderRecordRepository,
    ProviderRequestSpec,
    QuotaLedger,
    QuotaReservation,
    SourceRightsRepository,
    StoredSourceRecord,
)
from veltrix_v2.ingestion.preflight import (
    IngestionPreflightDecision,
    evaluate_ingestion_preflight,
)
from veltrix_v2.ingestion.providers.errors import ProviderResponseError


@dataclass(frozen=True, slots=True)
class IngestionExecutionResult:
    status: str
    reason_code: str
    preflight: IngestionPreflightDecision
    rights_decisions: tuple[RightsDecision, ...]
    run_id: str | None
    stored_records: tuple[StoredSourceRecord, ...]
    rejected_records: tuple[RejectedProviderRecord, ...]
    quota_units_consumed: int


def execute_ingestion(
    request: ProviderRequestSpec,
    adapter: ProviderAdapter,
    capability_repository: ProviderCapabilityRepository,
    quota_snapshot: QuotaSnapshot | None,
    rights_repository: SourceRightsRepository,
    quota_ledger: QuotaLedger,
    run_repository: IngestionRunRepository,
    record_repository: ProviderRecordRepository,
    *,
    source_id: str,
    purpose: DataUsePurpose,
    now_utc: datetime,
    transport_enabled: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> IngestionExecutionResult:
    """Execute one bounded batch; transport remains disabled unless explicitly enabled.

    Capability, quota and source-rights gates run before quota reservation.
    The ledger reservation is atomic and idempotent. A transport failure after
    dispatch conservatively settles the full reservation because provider-side
    consumption may be unknown. Raw payload plus accepted source envelope must
    be persisted atomically by the repository implementation.
    """
    current_time = clock or (lambda: datetime.now(timezone.utc))
    profile = capability_repository.get_verified_profile(request.provider)
    preflight = evaluate_ingestion_preflight(
        profile, quota_snapshot, request, now_utc=now_utc
    )
    empty_rights: tuple[RightsDecision, ...] = ()

    def result(
        status: str,
        reason: str,
        *,
        rights_decisions: tuple[RightsDecision, ...] = empty_rights,
        run_id: str | None = None,
        stored: tuple[StoredSourceRecord, ...] = (),
        rejected: tuple[RejectedProviderRecord, ...] = (),
        consumed: int = 0,
    ) -> IngestionExecutionResult:
        return IngestionExecutionResult(
            status, reason, preflight, rights_decisions,
            run_id, stored, rejected, consumed,
        )

    if adapter.provider_name != request.provider:
        return result("WITHHELD", "ADAPTER_PROVIDER_MISMATCH")
    if not preflight.allowed:
        return result("WITHHELD", preflight.reason_code)

    rights = rights_repository.get_verified_rights(source_id)
    if rights is None:
        return result("WITHHELD", "SOURCE_RIGHTS_MISSING")
    if rights.source_id != source_id:
        return result("WITHHELD", "SOURCE_RIGHTS_SOURCE_MISMATCH")

    purposes = (purpose,) if purpose is DataUsePurpose.CACHE else (purpose, DataUsePurpose.CACHE)
    rights_decisions = tuple(
        evaluate_source_use(
            rights,
            required_purpose,
            commercial=True,
            public_facing=(required_purpose is DataUsePurpose.PUBLIC_DISPLAY),
        )
        for required_purpose in purposes
    )
    denied = next((decision for decision in rights_decisions if not decision.allowed), None)
    if denied is not None:
        return result("WITHHELD", denied.reason_code, rights_decisions=rights_decisions)

    if not transport_enabled:
        return result("DISABLED", "TRANSPORT_DISABLED", rights_decisions=rights_decisions)

    reserved_at = current_time()
    reservation = quota_ledger.reserve(
        provider=request.provider,
        quota_scope=request.quota_scope,
        units=request.quota_units,
        idempotency_key=request.idempotency_key,
        now_utc=reserved_at,
    )
    if reservation is None:
        return result("WITHHELD", "QUOTA_RESERVATION_FAILED", rights_decisions=rights_decisions)
    if (
        reservation.provider != request.provider
        or reservation.quota_scope != request.quota_scope
        or reservation.units_reserved != request.quota_units
        or reservation.idempotency_key != request.idempotency_key
    ):
        quota_ledger.release(reservation.reservation_id, released_at_utc=current_time())
        return result("WITHHELD", "QUOTA_RESERVATION_MISMATCH", rights_decisions=rights_decisions)

    try:
        run_id = run_repository.start_run(
            provider=request.provider,
            data_class=request.data_class,
            started_at_utc=current_time(),
            request_id=request.request_id,
        )
    except Exception:
        quota_ledger.release(
            reservation.reservation_id, released_at_utc=current_time()
        )
        raise

    try:
        response = adapter.fetch(request)
    except ProviderResponseError as exc:
        quota_ledger.settle(
            reservation.reservation_id,
            actual_units=reservation.units_reserved,
            settled_at_utc=current_time(),
        )
        run_repository.fail_run(
            run_id, failed_at_utc=current_time(), reason_code=exc.reason_code
        )
        return result(
            "FAILED", exc.reason_code, rights_decisions=rights_decisions,
            run_id=run_id, consumed=reservation.units_reserved,
        )
    except Exception:
        quota_ledger.settle(
            reservation.reservation_id,
            actual_units=reservation.units_reserved,
            settled_at_utc=current_time(),
        )
        run_repository.fail_run(
            run_id, failed_at_utc=current_time(),
            reason_code="UNEXPECTED_PROVIDER_ADAPTER_ERROR",
        )
        raise

    actual_units = response.quota_units_consumed
    quota_ledger.settle(
        reservation.reservation_id,
        actual_units=actual_units,
        settled_at_utc=current_time(),
    )
    if response.request_id != request.request_id or response.provider != request.provider:
        run_repository.fail_run(
            run_id, failed_at_utc=current_time(),
            reason_code="PROVIDER_RESPONSE_IDENTITY_MISMATCH",
        )
        return result(
            "FAILED", "PROVIDER_RESPONSE_IDENTITY_MISMATCH",
            rights_decisions=rights_decisions, run_id=run_id,
            consumed=actual_units,
        )
    if actual_units > reservation.units_reserved:
        run_repository.fail_run(
            run_id, failed_at_utc=current_time(),
            reason_code="QUOTA_COST_EXCEEDED_RESERVATION",
        )
        return result(
            "FAILED", "QUOTA_COST_EXCEEDED_RESERVATION",
            rights_decisions=rights_decisions, run_id=run_id,
            consumed=actual_units,
        )

    try:
        persisted: BatchPersistenceResult = persist_provider_batch(
            request,
            response,
            {source_id: rights},
            record_repository,
            ingestion_run_id=run_id,
            ingested_at_utc=current_time(),
            purpose=purpose,
        )
    except Exception:
        run_repository.fail_run(
            run_id, failed_at_utc=current_time(),
            reason_code="SOURCE_RECORD_PERSISTENCE_FAILED",
        )
        raise

    run_repository.complete_run(
        run_id,
        completed_at_utc=current_time(),
        fetched_count=len(response.records),
        accepted_count=len(persisted.accepted),
        rejected_count=len(persisted.rejected),
        quota_units_consumed=actual_units,
    )
    status = "PARTIAL" if persisted.rejected else "COMPLETED"
    reason = "RECORDS_REJECTED" if persisted.rejected else "INGESTION_COMPLETED"
    return result(
        status, reason, rights_decisions=rights_decisions, run_id=run_id,
        stored=persisted.accepted, rejected=persisted.rejected,
        consumed=actual_units,
    )
