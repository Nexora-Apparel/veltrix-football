"""Storage-neutral historical evidence and incremental-sync contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from veltrix_v2.domain.contracts import HistoryState


@dataclass(frozen=True, slots=True)
class HistoricalMatch:
    """Canonical result with explicit source-record-to-provider-ID provenance."""
    historical_match_id: str
    canonical_fixture_id: str
    canonical_competition_id: str
    squad_category: str
    home_team_id: str
    away_team_id: str
    kickoff_at_utc: datetime
    home_goals: int
    away_goals: int
    source_record_ids: tuple[str, ...]
    provider_fixture_refs: tuple[tuple[str, str, str], ...]
    provider_source_record_refs: tuple[tuple[str, str, str, str], ...] = ()

    def __post_init__(self) -> None:
        required = (self.historical_match_id,self.canonical_fixture_id,self.canonical_competition_id,
                    self.squad_category,self.home_team_id,self.away_team_id)
        if any(not value or not value.strip() for value in required):
            raise ValueError("canonical match identity fields are required")
        _require_aware(self.kickoff_at_utc,"kickoff_at_utc")
        if self.home_team_id == self.away_team_id:
            raise ValueError("home and away canonical team IDs must differ")
        if self.home_goals < 0 or self.away_goals < 0:
            raise ValueError("goals cannot be negative")
        if not self.source_record_ids or len(set(self.source_record_ids)) != len(self.source_record_ids):
            raise ValueError("historical matches require unique source-record provenance")
        if not self.provider_fixture_refs:
            raise ValueError("provider fixture provenance is required")
        if any(len(ref)!=3 or any(not part.strip() for part in ref) for ref in self.provider_fixture_refs):
            raise ValueError("provider fixture refs must contain provider, source and fixture IDs")
        for ref in self.provider_source_record_refs:
            if len(ref)!=4 or any(not part.strip() for part in ref):
                raise ValueError("provider source refs must contain record, provider, source and fixture IDs")
            if ref[0] not in self.source_record_ids or ref[1:] not in self.provider_fixture_refs:
                raise ValueError("provider source ref must link declared source record and provider fixture")


@dataclass(frozen=True, slots=True)
class TeamHistoryQuery:
    canonical_team_id: str
    squad_category: str
    cutoff_at_utc: datetime
    window_start_date: date
    competition_ids: tuple[str, ...]
    max_matches: int
    minimum_matches: int = 5

    def __post_init__(self) -> None:
        if not self.canonical_team_id or not self.canonical_team_id.strip():
            raise ValueError("canonical_team_id is required")
        if not self.squad_category or not self.squad_category.strip():
            raise ValueError("squad_category is required")
        _require_aware(self.cutoff_at_utc,"cutoff_at_utc")
        if self.window_start_date >= self.cutoff_at_utc.date():
            raise ValueError("history window must begin before the cutoff date")
        if self.max_matches < 1:
            raise ValueError("max_matches must be positive")
        if self.minimum_matches < 1 or self.minimum_matches > self.max_matches:
            raise ValueError("minimum_matches must be positive and no greater than max_matches")
        if any(not value or not value.strip() for value in self.competition_ids):
            raise ValueError("competition_ids cannot contain blank values")
        if len(set(self.competition_ids)) != len(self.competition_ids):
            raise ValueError("competition_ids must be unique")


@dataclass(frozen=True, slots=True)
class HistoryEvidenceResult:
    canonical_team_id: str
    state: HistoryState
    matches: tuple[HistoricalMatch, ...]
    total_match_count: int
    evidence_ids: tuple[str, ...]
    reason_code: str

    def __post_init__(self) -> None:
        if not self.canonical_team_id or not self.canonical_team_id.strip():
            raise ValueError("canonical_team_id is required")
        if self.total_match_count < 0 or self.total_match_count < len(self.matches):
            raise ValueError("invalid total_match_count")
        if self.state is HistoryState.FOUND and self.total_match_count == 0:
            raise ValueError("FOUND evidence must contain at least one match")
        if self.state is HistoryState.NOT_FOUND and (self.total_match_count != 0 or self.matches):
            raise ValueError("NOT_FOUND evidence cannot contain match rows")
        if not self.reason_code or not self.reason_code.strip():
            raise ValueError("history evidence requires an explicit reason code")


@dataclass(frozen=True, slots=True)
class SyncWatermark:
    provider: str
    data_class: str
    scope: str
    cursor: str | None
    updated_at_utc: datetime
    version: int

    def __post_init__(self) -> None:
        if any(not value or not value.strip() for value in (self.provider,self.data_class,self.scope)):
            raise ValueError("watermark provider, data class and scope are required")
        _require_aware(self.updated_at_utc,"updated_at_utc")
        if self.version < 0:
            raise ValueError("watermark version cannot be negative")


@dataclass(frozen=True, slots=True)
class IncrementalSyncPlan:
    provider: str
    data_class: str
    scope: str
    lower_bound_utc: datetime
    upper_bound_utc: datetime
    max_pages: int
    page_size: int
    expected_watermark_version: int

    def __post_init__(self) -> None:
        if any(not value or not value.strip() for value in (self.provider,self.data_class,self.scope)):
            raise ValueError("sync plan provider, data class and scope are required")
        _require_aware(self.lower_bound_utc,"lower_bound_utc")
        _require_aware(self.upper_bound_utc,"upper_bound_utc")
        if self.lower_bound_utc >= self.upper_bound_utc:
            raise ValueError("sync window must have positive duration")
        if self.max_pages < 1 or self.page_size < 1:
            raise ValueError("sync page limits must be positive")
        if self.expected_watermark_version < 0:
            raise ValueError("watermark version cannot be negative")


class HistoricalMatchRepository(Protocol):
    def get_team_history(self, query: TeamHistoryQuery) -> HistoryEvidenceResult: ...


class SyncWatermarkRepository(Protocol):
    def read(self, *, provider: str, data_class: str, scope: str) -> SyncWatermark | None: ...
    def advance(self, watermark: SyncWatermark, *, expected_version: int) -> bool: ...


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
