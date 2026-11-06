"""Provider-neutral ingestion ports and immutable transport contracts.

These interfaces describe the boundary only. They do not perform network I/O,
reserve real quota, or select a persistence backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from types import MappingProxyType
from typing import Mapping, Protocol

from veltrix_v2.domain.contracts import SourceRights
from veltrix_v2.ingestion.acceptance import AcceptedSourceRecord
from veltrix_v2.ingestion.provider_access import ProviderAccessProfile


ScalarParameter = str | int | float | bool


@dataclass(frozen=True, slots=True)
class ProviderRequestSpec:
    """One bounded provider request, priced before transport is invoked."""

    request_id: str
    provider: str
    endpoint: str
    data_class: str
    quota_scope: str
    quota_units: int
    competition_ids: tuple[str, ...]
    history_start_date: date | None
    idempotency_key: str
    parameters: Mapping[str, ScalarParameter]

    def __post_init__(self) -> None:
        required = (
            self.request_id, self.provider, self.endpoint, self.data_class,
            self.quota_scope, self.idempotency_key,
        )
        if any(not value or not value.strip() for value in required):
            raise ValueError("request identity, provider, endpoint, data class, quota scope and idempotency key are required")
        if self.quota_units < 1:
            raise ValueError("quota_units must be positive")
        if any(not item or not item.strip() for item in self.competition_ids):
            raise ValueError("competition_ids cannot contain blank values")
        if len(set(self.competition_ids)) != len(self.competition_ids):
            raise ValueError("competition_ids must be unique")
        if any(not key or not key.strip() for key in self.parameters):
            raise ValueError("parameter names cannot be blank")
        if any(not isinstance(value, (str, int, float, bool)) for value in self.parameters.values()):
            raise ValueError("provider parameters must be scalar values")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class RawProviderRecord:
    """Provider response record before canonical identity or rights acceptance."""

    provider: str
    source_id: str
    provider_record_id: str
    provider_fixture_id: str | None
    provider_competition_id: str | None
    data_class: str
    raw_payload: bytes
    source_updated_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        required = (self.provider, self.source_id, self.provider_record_id, self.data_class)
        if any(not value or not value.strip() for value in required):
            raise ValueError("raw provider record identity fields are required")
        if not isinstance(self.raw_payload, bytes) or not self.raw_payload:
            raise ValueError("raw_payload must contain the exact non-empty provider bytes")
        if self.source_updated_at_utc is not None:
            _require_aware(self.source_updated_at_utc, "source_updated_at_utc")

    @property
    def raw_payload_sha256(self) -> str:
        """Digest the exact provider bytes; never hash a re-serialized object."""
        return sha256(self.raw_payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderBatchResponse:
    """One provider response with explicit request and fetch-time provenance."""

    request_id: str
    provider: str
    fetched_at_utc: datetime
    records: tuple[RawProviderRecord, ...]
    quota_units_consumed: int

    def __post_init__(self) -> None:
        if not self.request_id or not self.provider:
            raise ValueError("request_id and provider are required")
        _require_aware(self.fetched_at_utc, "fetched_at_utc")
        if self.quota_units_consumed < 0:
            raise ValueError("quota_units_consumed cannot be negative")
        if any(record.provider != self.provider for record in self.records):
            raise ValueError("every record must belong to the response provider")


@dataclass(frozen=True, slots=True)
class QuotaReservation:
    reservation_id: str
    provider: str
    quota_scope: str
    units_reserved: int
    idempotency_key: str
    reserved_at_utc: datetime

    def __post_init__(self) -> None:
        required = (self.reservation_id, self.provider, self.quota_scope, self.idempotency_key)
        if any(not value or not value.strip() for value in required):
            raise ValueError("quota reservation identity fields are required")
        if self.units_reserved < 1:
            raise ValueError("units_reserved must be positive")
        _require_aware(self.reserved_at_utc, "reserved_at_utc")


@dataclass(frozen=True, slots=True)
class StoredSourceRecord:
    source_record_id: str
    payload_reference: str
    raw_payload_sha256: str
    duplicate: bool

    def __post_init__(self) -> None:
        if not self.source_record_id or not self.source_record_id.strip():
            raise ValueError("source_record_id is required")
        if not self.payload_reference or not self.payload_reference.strip():
            raise ValueError("payload reference is required")
        if len(self.raw_payload_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.raw_payload_sha256.lower()
        ):
            raise ValueError("raw_payload_sha256 must be a SHA-256 hex digest")


class ProviderAdapter(Protocol):
    """Provider transport. Implementations must not normalize canonical identity."""

    @property
    def provider_name(self) -> str: ...

    def fetch(self, request: ProviderRequestSpec) -> ProviderBatchResponse: ...


class ProviderCapabilityRepository(Protocol):
    def get_verified_profile(self, provider: str) -> ProviderAccessProfile | None: ...


class QuotaLedger(Protocol):
    """Implement reserve atomically; idempotency_key prevents duplicate charging."""

    def reserve(
        self, *, provider: str, quota_scope: str, units: int,
        idempotency_key: str, now_utc: datetime,
    ) -> QuotaReservation | None: ...

    def settle(
        self, reservation_id: str, *, actual_units: int, settled_at_utc: datetime,
    ) -> None: ...

    def release(self, reservation_id: str, *, released_at_utc: datetime) -> None: ...


class SourceRightsRepository(Protocol):
    def get_verified_rights(self, source_id: str) -> SourceRights | None: ...


class ProviderRecordRepository(Protocol):
    """Persist raw bytes, accepted envelope and rights evidence as one atomic unit."""

    def persist_accepted_record(
        self, accepted: AcceptedSourceRecord, *, raw_payload: bytes,
        ingestion_run_id: str, idempotency_key: str,
    ) -> StoredSourceRecord: ...


class IngestionRunRepository(Protocol):
    def start_run(
        self, *, provider: str, data_class: str,
        started_at_utc: datetime, request_id: str,
    ) -> str: ...

    def complete_run(
        self, run_id: str, *, completed_at_utc: datetime,
        fetched_count: int, accepted_count: int, rejected_count: int,
        quota_units_consumed: int,
    ) -> None: ...

    def fail_run(
        self, run_id: str, *, failed_at_utc: datetime, reason_code: str,
    ) -> None: ...


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
