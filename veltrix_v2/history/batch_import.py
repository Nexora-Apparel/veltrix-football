"""Bounded, resumable historical import with per-record audit outcomes."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol, Sequence
from veltrix_v2.domain.contracts import SourceRights
from veltrix_v2.history.contracts import HistoricalMatch
from veltrix_v2.history.importer import build_training_history_match, HistoricalMatchImportDecision
from veltrix_v2.identity.registry import MappingResolutionStatus, ResolvedProviderFixture
from veltrix_v2.ingestion.providers.five_dollar_fixture import FiveDollarFixtureRecord


class HistoricalMatchWriter(Protocol):
    def persist_historical_match(self, match: HistoricalMatch, *, imported_at_utc: datetime) -> bool: ...


@dataclass(frozen=True, slots=True)
class HistoryImportCandidate:
    fixture: FiveDollarFixtureRecord
    resolved_identity: ResolvedProviderFixture
    source_record_id: str
    rights: SourceRights
    canonical_fixture_id: str | None


@dataclass(frozen=True, slots=True)
class HistoryImportRowResult:
    source_record_id: str
    provider_fixture_id: str
    status: str
    reason_code: str
    canonical_fixture_id: str | None


@dataclass(frozen=True, slots=True)
class HistoryImportBatchReport:
    status: str
    total_candidates: int
    imported_count: int
    rejected_count: int
    quarantined_count: int
    source_manifest_sha256: str
    rows: tuple[HistoryImportRowResult, ...]


def import_history_batch(candidates: Sequence[HistoryImportCandidate],
                         repository: HistoricalMatchWriter, *,
                         imported_at_utc: datetime, evaluated_at_utc: datetime,
                         max_batch_size: int = 100) -> HistoryImportBatchReport:
    """Import a bounded chunk; every candidate receives an explicit outcome.

    This function does not advance provider watermarks. The caller may advance
    only after all chunks are persisted and reconciliation reports are clean.
    """
    if max_batch_size<1:
        raise ValueError("max_batch_size must be positive")
    if len(candidates)>max_batch_size:
        raise ValueError("HISTORY_IMPORT_BATCH_LIMIT_EXCEEDED")
    if imported_at_utc.tzinfo is None or imported_at_utc.utcoffset() is None:
        raise ValueError("imported_at_utc must be timezone-aware")
    if evaluated_at_utc.tzinfo is None or evaluated_at_utc.utcoffset() is None:
        raise ValueError("evaluated_at_utc must be timezone-aware")
    source_ids=[item.source_record_id for item in candidates]
    if any(not value or not value.strip() for value in source_ids):
        raise ValueError("source_record_id is required for every candidate")
    if len(set(source_ids))!=len(source_ids):
        raise ValueError("DUPLICATE_SOURCE_RECORD_IN_IMPORT_BATCH")

    rows=[]
    imported=rejected=quarantined=0
    manifest_parts=[]
    for item in candidates:
        source=item.fixture.source_identity
        manifest_parts.append("|".join((item.source_record_id,source.provider,source.source_id,
                                        source.provider_fixture_id,item.fixture.raw_payload_sha256)))
        if item.resolved_identity.status is not MappingResolutionStatus.VERIFIED:
            rows.append(HistoryImportRowResult(item.source_record_id,source.provider_fixture_id,
                "QUARANTINED",item.resolved_identity.reason_code,None))
            quarantined+=1
            continue
        if not item.canonical_fixture_id:
            rows.append(HistoryImportRowResult(item.source_record_id,source.provider_fixture_id,
                "QUARANTINED","CANONICAL_FIXTURE_RECONCILIATION_PENDING",None))
            quarantined+=1
            continue
        decision: HistoricalMatchImportDecision=build_training_history_match(
            item.fixture,item.resolved_identity,item.source_record_id,item.rights,
            item.canonical_fixture_id,evaluated_at_utc=evaluated_at_utc)
        if not decision.allowed or decision.historical_match is None:
            rows.append(HistoryImportRowResult(item.source_record_id,source.provider_fixture_id,
                "REJECTED",decision.reason_code,item.canonical_fixture_id))
            rejected+=1
            continue
        repository.persist_historical_match(decision.historical_match,imported_at_utc=imported_at_utc)
        rows.append(HistoryImportRowResult(item.source_record_id,source.provider_fixture_id,
            "IMPORTED",decision.reason_code,item.canonical_fixture_id))
        imported+=1

    manifest=sha256("\n".join(sorted(manifest_parts)).encode("utf-8")).hexdigest()
    status="COMPLETED" if not rejected and not quarantined else "PARTIAL"
    return HistoryImportBatchReport(status,len(candidates),imported,rejected,quarantined,
                                    manifest,tuple(rows))
