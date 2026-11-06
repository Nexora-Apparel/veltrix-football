"""Rights-aware, provenance-preserving provider record acceptance."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from string import hexdigits

from veltrix_v2.domain.contracts import (
    DataUsePurpose,
    RightsDecision,
    SourceRights,
)
from veltrix_v2.domain.rights import require_source_use


@dataclass(frozen=True, slots=True)
class ProviderSourceRecord:
    """A normalized envelope around one immutable provider response record."""

    provider: str
    source_id: str
    provider_record_id: str
    provider_fixture_id: str | None
    provider_competition_id: str | None
    data_class: str
    raw_payload_sha256: str
    payload_reference: str
    fetched_at_utc: datetime
    ingested_at_utc: datetime
    source_updated_at_utc: datetime | None = None
    provider_home_team_id: str | None = None
    provider_away_team_id: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptedSourceRecord:
    record: ProviderSourceRecord
    rights_decisions: tuple[RightsDecision, ...]


class IngestionRejected(ValueError):
    """A provider record failed provenance, timestamp or rights validation."""


def _require_utc_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IngestionRejected(f"{field_name} must be timezone-aware")


def _validate_record(record: ProviderSourceRecord, rights: SourceRights) -> None:
    required = {
        "provider": record.provider,
        "source_id": record.source_id,
        "provider_record_id": record.provider_record_id,
        "data_class": record.data_class,
        "payload_reference": record.payload_reference,
    }
    missing = [name for name, value in required.items() if not value or not value.strip()]
    if missing:
        raise IngestionRejected("required provenance fields missing: " + ",".join(missing))

    if record.source_id != rights.source_id:
        raise IngestionRejected("record source_id does not match rights source_id")

    digest = record.raw_payload_sha256 or ""
    if len(digest) != 64 or any(ch not in hexdigits for ch in digest):
        raise IngestionRejected("raw_payload_sha256 must be a 64-character SHA-256 hex digest")

    _require_utc_aware(record.fetched_at_utc, "fetched_at_utc")
    _require_utc_aware(record.ingested_at_utc, "ingested_at_utc")
    if record.source_updated_at_utc is not None:
        _require_utc_aware(record.source_updated_at_utc, "source_updated_at_utc")

    if record.ingested_at_utc.astimezone(timezone.utc) < record.fetched_at_utc.astimezone(timezone.utc):
        raise IngestionRejected("ingested_at_utc cannot precede fetched_at_utc")


def accept_provider_record(
    record: ProviderSourceRecord,
    rights: SourceRights,
    *,
    purpose: DataUsePurpose,
    commercial: bool = True,
) -> AcceptedSourceRecord:
    """Validate provenance and enforce both requested use and cache permission.

    The returned envelope is suitable for a repository adapter. This function
    performs no network call and writes no data. A caller must persist the
    accepted envelope and its rights decisions atomically with the raw payload
    reference or reject the write.
    """
    _validate_record(record, rights)

    purposes = (purpose,) if purpose is DataUsePurpose.CACHE else (purpose, DataUsePurpose.CACHE)
    decisions = tuple(
        require_source_use(rights, requested, commercial=commercial)
        for requested in purposes
    )
    return AcceptedSourceRecord(record=record, rights_decisions=decisions)
