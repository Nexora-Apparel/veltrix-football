"""Rights-aware, idempotent persistence of provider batch records."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from veltrix_v2.domain.contracts import DataUsePurpose, SourceRights
from veltrix_v2.domain.rights import evaluate_source_use
from veltrix_v2.ingestion.acceptance import (
    IngestionRejected,
    ProviderSourceRecord,
    accept_provider_record,
)
from veltrix_v2.ingestion.ports import (
    ProviderBatchResponse,
    ProviderRecordRepository,
    ProviderRequestSpec,
    StoredSourceRecord,
)


@dataclass(frozen=True, slots=True)
class RejectedProviderRecord:
    provider_record_id: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class BatchPersistenceResult:
    accepted: tuple[StoredSourceRecord, ...]
    rejected: tuple[RejectedProviderRecord, ...]
    quota_units_consumed: int


def persist_provider_batch(
    request: ProviderRequestSpec,
    response: ProviderBatchResponse,
    rights_by_source: Mapping[str, SourceRights],
    repository: ProviderRecordRepository,
    *,
    ingestion_run_id: str,
    ingested_at_utc: datetime,
    purpose: DataUsePurpose,
) -> BatchPersistenceResult:
    """Validate and persist records without network access or identity merging.

    Each accepted source record, its exact raw bytes and its rights decisions
    must be committed atomically by the repository. Retries use a deterministic
    per-record idempotency key. Canonical fixture matching is deliberately
    outside this function.
    """
    if response.request_id != request.request_id:
        raise IngestionRejected("provider response request_id does not match request")
    if response.provider != request.provider:
        raise IngestionRejected("provider response provider does not match request")
    if response.quota_units_consumed > request.quota_units:
        raise IngestionRejected("provider response consumed more quota than reserved request cost")
    if not ingestion_run_id or not ingestion_run_id.strip():
        raise IngestionRejected("ingestion_run_id is required")
    if ingested_at_utc.tzinfo is None or ingested_at_utc.utcoffset() is None:
        raise IngestionRejected("ingested_at_utc must be timezone-aware")

    accepted: list[StoredSourceRecord] = []
    rejected: list[RejectedProviderRecord] = []

    for raw in response.records:
        if raw.data_class != request.data_class:
            rejected.append(RejectedProviderRecord(raw.provider_record_id, "DATA_CLASS_MISMATCH"))
            continue
        if request.competition_ids and raw.provider_competition_id not in request.competition_ids:
            rejected.append(RejectedProviderRecord(raw.provider_record_id, "COMPETITION_OUTSIDE_REQUEST_SCOPE"))
            continue

        rights = rights_by_source.get(raw.source_id)
        if rights is None:
            rejected.append(RejectedProviderRecord(raw.provider_record_id, "SOURCE_RIGHTS_MISSING"))
            continue
        if rights.source_id != raw.source_id:
            rejected.append(RejectedProviderRecord(raw.provider_record_id, "SOURCE_RIGHTS_SOURCE_MISMATCH"))
            continue

        purposes = (purpose,) if purpose is DataUsePurpose.CACHE else (purpose, DataUsePurpose.CACHE)
        decisions = tuple(
            evaluate_source_use(
                rights,
                requested,
                commercial=True,
                public_facing=(requested is DataUsePurpose.PUBLIC_DISPLAY),
            )
            for requested in purposes
        )
        denied = next((decision for decision in decisions if not decision.allowed), None)
        if denied is not None:
            rejected.append(RejectedProviderRecord(raw.provider_record_id, denied.reason_code))
            continue

        payload_reference = (
            f"provider-response://{request.request_id}/{raw.provider_record_id}"
        )
        source_record = ProviderSourceRecord(
            provider=raw.provider,
            source_id=raw.source_id,
            provider_record_id=raw.provider_record_id,
            provider_fixture_id=raw.provider_fixture_id,
            provider_competition_id=raw.provider_competition_id,
            data_class=raw.data_class,
            raw_payload_sha256=raw.raw_payload_sha256,
            payload_reference=payload_reference,
            fetched_at_utc=response.fetched_at_utc,
            ingested_at_utc=ingested_at_utc,
            source_updated_at_utc=raw.source_updated_at_utc,
            provider_home_team_id=raw.provider_home_team_id,
            provider_away_team_id=raw.provider_away_team_id,
        )
        try:
            accepted_record = accept_provider_record(
                source_record, rights, purpose=purpose, commercial=True
            )
        except IngestionRejected as exc:
            rejected.append(RejectedProviderRecord(raw.provider_record_id, str(exc)))
            continue

        stored = repository.persist_accepted_record(
            accepted_record,
            raw_payload=raw.raw_payload,
            ingestion_run_id=ingestion_run_id,
            idempotency_key=f"{request.idempotency_key}:{raw.provider_record_id}",
        )
        if stored.raw_payload_sha256 != raw.raw_payload_sha256:
            raise IngestionRejected("repository payload digest differs from exact provider bytes")
        accepted.append(stored)

    return BatchPersistenceResult(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        quota_units_consumed=response.quota_units_consumed,
    )
