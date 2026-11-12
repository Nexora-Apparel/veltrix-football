"""Phase 2 historical data contracts; provider- and model-independent."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Mapping


class ApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    PROVISIONAL = "PROVISIONAL"
    REVOKED = "REVOKED"


class DataUsePurpose(StrEnum):
    COLLECTION = "COLLECTION"
    STORAGE = "STORAGE"
    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"
    MODEL_TRAINING = "MODEL_TRAINING"
    BENCHMARKING = "BENCHMARKING"
    CACHE = "CACHE"
    PUBLIC_DISPLAY = "PUBLIC_DISPLAY"
    RAW_REDISTRIBUTION = "RAW_REDISTRIBUTION"


class FixtureStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"
    UNKNOWN = "UNKNOWN"


class ImportOutcomeStatus(StrEnum):
    IMPORTABLE = "IMPORTABLE"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceApproval:
    approval_id: str
    provider: str
    source_id: str
    competition_scope: str
    data_type: str
    status: ApprovalStatus
    permitted_uses: frozenset[DataUsePurpose]
    commercial_use_allowed: bool
    terms_url: str | None
    terms_version: str | None
    evidence_uri: str | None
    evidence_sha256: str | None
    rights_basis: str | None
    reviewed_at_utc: datetime | None
    reviewer_id: str | None
    valid_from_utc: datetime
    valid_until_utc: datetime | None = None
    attribution_required: bool = False
    attribution_text: str | None = None
    attribution_url: str | None = None
    raw_redistribution_allowed: bool = False

    def __post_init__(self) -> None:
        required = (self.approval_id, self.provider, self.source_id,
                    self.competition_scope, self.data_type)
        if any(not value or not value.strip() for value in required):
            raise ValueError("SOURCE_APPROVAL_IDENTITY_REQUIRED")
        _aware(self.valid_from_utc, "valid_from_utc")
        if self.valid_until_utc is not None:
            _aware(self.valid_until_utc, "valid_until_utc")
            if self.valid_until_utc <= self.valid_from_utc:
                raise ValueError("SOURCE_APPROVAL_VALIDITY_EMPTY")
        if self.reviewed_at_utc is not None:
            _aware(self.reviewed_at_utc, "reviewed_at_utc")
        if self.status is ApprovalStatus.APPROVED:
            digest = self.evidence_sha256 or ""
            if not (
                self.terms_url and self.terms_version and self.evidence_uri
                and self.reviewer_id and self.rights_basis in {
                    "TERMS", "WRITTEN_PERMISSION", "OPEN_LICENSE", "CONTRACT"
                }
                and self.reviewed_at_utc is not None
                and len(digest) == 64
                and all(ch in "0123456789abcdef" for ch in digest.casefold())
                and self.permitted_uses
            ):
                raise ValueError("APPROVED_SOURCE_REQUIRES_COMPLETE_RIGHTS_EVIDENCE")
            if self.attribution_required and not (
                self.attribution_text and self.attribution_url
            ):
                raise ValueError("APPROVED_SOURCE_ATTRIBUTION_INCOMPLETE")


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    provider: str
    source_id: str
    endpoint: str
    request_id: str
    request_params: Mapping[str, object]
    http_status: int
    raw_body: bytes
    response_headers: Mapping[str, str]
    fetched_at_utc: datetime

    def __post_init__(self) -> None:
        if any(not value or not value.strip() for value in (
            self.provider, self.source_id, self.endpoint, self.request_id
        )):
            raise ValueError("PROVIDER_RESPONSE_IDENTITY_REQUIRED")
        if self.http_status != 200:
            raise ValueError("ONLY_SUCCESSFUL_PROVIDER_RESPONSES_ARE_STORABLE")
        if not isinstance(self.raw_body, bytes) or not self.raw_body:
            raise ValueError("PROVIDER_RESPONSE_RAW_BODY_REQUIRED")
        _aware(self.fetched_at_utc, "fetched_at_utc")

    @property
    def response_sha256(self) -> str:
        return sha256(self.raw_body).hexdigest()


@dataclass(frozen=True, slots=True)
class HistoricalFixture:
    provider: str
    source_id: str
    provider_fixture_id: str
    provider_competition_id: str
    provider_home_team_id: str
    provider_away_team_id: str
    competition_name: str
    home_team_name: str
    away_team_name: str
    kickoff_at_utc: datetime
    season_key: str | None
    status: FixtureStatus
    home_score: int | None
    away_score: int | None
    payload: Mapping[str, object]
    payload_sha256: str
    retrieved_at_utc: datetime
    source_event_time_utc: datetime
    available_at_utc: datetime | None
    availability_basis: str
    point_in_time_certifiable: bool
    rights_approval_id: str

    def __post_init__(self) -> None:
        if any(not value or not value.strip() for value in (
            self.provider, self.source_id, self.provider_fixture_id,
            self.provider_competition_id, self.provider_home_team_id,
            self.provider_away_team_id, self.rights_approval_id
        )):
            raise ValueError("HISTORICAL_FIXTURE_SOURCE_IDENTITY_REQUIRED")
        if self.provider_home_team_id == self.provider_away_team_id:
            raise ValueError("HISTORICAL_FIXTURE_HOME_AWAY_ID_COLLISION")
        for field, value in (
            ("kickoff_at_utc", self.kickoff_at_utc),
            ("retrieved_at_utc", self.retrieved_at_utc),
            ("source_event_time_utc", self.source_event_time_utc),
        ):
            _aware(value, field)
        if self.available_at_utc is not None:
            _aware(self.available_at_utc, "available_at_utc")
            if self.available_at_utc < self.kickoff_at_utc:
                raise ValueError("FIXTURE_RESULT_AVAILABILITY_PRECEDES_KICKOFF")
        if self.source_event_time_utc != self.kickoff_at_utc:
            raise ValueError("FIXTURE_SOURCE_EVENT_TIME_MUST_MATCH_KICKOFF")
        if len(self.payload_sha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.payload_sha256.casefold()
        ):
            raise ValueError("HISTORICAL_FIXTURE_PAYLOAD_HASH_INVALID")
        if self.status is FixtureStatus.FINISHED:
            if type(self.home_score) is not int or type(self.away_score) is not int:
                raise ValueError("FINISHED_FIXTURE_REQUIRES_INTEGER_SCORES")
            if self.home_score < 0 or self.away_score < 0:
                raise ValueError("FINISHED_FIXTURE_SCORE_NEGATIVE")
            if self.available_at_utc is None or not self.availability_basis:
                raise ValueError("FINISHED_FIXTURE_AVAILABILITY_PROVENANCE_REQUIRED")
        elif self.home_score is not None or self.away_score is not None:
            raise ValueError("UNSETTLED_FIXTURE_CANNOT_HAVE_FINAL_SCORE")


@dataclass(frozen=True, slots=True)
class RightsDecision:
    allowed: bool
    reason_code: str
    approval_id: str
    attribution_text: str | None = None
    attribution_url: str | None = None


@dataclass(frozen=True, slots=True)
class FixtureImportDecision:
    status: ImportOutcomeStatus
    reason_code: str
    provider_fixture_id: str
    rights_decisions: tuple[RightsDecision, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportBatchReport:
    status: str
    total_records: int
    importable_count: int
    rejected_count: int
    quarantined_count: int
    duplicate_provider_fixture_ids: tuple[str, ...]
    first_kickoff_utc: str | None
    last_kickoff_utc: str | None
    counts_by_competition: tuple[tuple[str, int], ...]
    source_manifest_sha256: str
    request_count: int
    request_budget: int

    def __post_init__(self) -> None:
        if min(self.total_records, self.importable_count, self.rejected_count,
               self.quarantined_count, self.request_count, self.request_budget) < 0:
            raise ValueError("IMPORT_BATCH_COUNTS_CANNOT_BE_NEGATIVE")
        if self.importable_count + self.rejected_count + self.quarantined_count != self.total_records:
            raise ValueError("IMPORT_BATCH_TERMINAL_COUNTS_MISMATCH")
        if self.request_count > self.request_budget:
            raise ValueError("IMPORT_BATCH_REQUEST_BUDGET_EXCEEDED")
