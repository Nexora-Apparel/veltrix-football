"""Typed domain contracts for VELTRIX FOOTBALL 2.0.

This module is deliberately provider- and framework-independent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping


class HistoryState(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    QUERY_FAILED = "QUERY_FAILED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


class IdentityState(StrEnum):
    VERIFIED = "VERIFIED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class ForecastStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    UNSUPPORTED_COMPETITION = "UNSUPPORTED_COMPETITION"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    HISTORY_NOT_FOUND = "HISTORY_NOT_FOUND"
    HISTORY_QUERY_FAILED = "HISTORY_QUERY_FAILED"
    HISTORY_IDENTITY_MISMATCH = "HISTORY_IDENTITY_MISMATCH"
    AMBIGUOUS_FIXTURE_IDENTITY = "AMBIGUOUS_FIXTURE_IDENTITY"
    INVALID_FEATURES = "INVALID_FEATURES"
    MODEL_ERROR = "MODEL_ERROR"
    CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"
    PAST_KICKOFF = "PAST_KICKOFF"


@dataclass(frozen=True, slots=True)
class TeamHistoryEvidence:
    state: HistoryState
    match_count: int
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FixtureEligibilityInput:
    fixture_id: str
    competition_supported: bool
    identity_state: IdentityState
    home_history: TeamHistoryEvidence
    away_history: TeamHistoryEvidence
    kickoff_at_utc: datetime
    evaluated_at_utc: datetime


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    fixture_id: str
    status: ForecastStatus
    reason_code: str
    publishable: bool
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ForecastCandidate:
    fixture_id: str
    market: str
    probabilities: Mapping[str, float]
    model_version: str
    feature_snapshot_id: str
    generated_at_utc: datetime
    evidence_ids: tuple[str, ...]
    origin: str


class RightsStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class DataUsePurpose(StrEnum):
    HISTORICAL_IMPORT = "HISTORICAL_IMPORT"
    MODEL_TRAINING = "MODEL_TRAINING"
    CALIBRATION = "CALIBRATION"
    INFERENCE = "INFERENCE"
    PUBLIC_DISPLAY = "PUBLIC_DISPLAY"
    CACHE = "CACHE"
    PAPER_EVALUATION = "PAPER_EVALUATION"
    RAW_REDISTRIBUTION = "RAW_REDISTRIBUTION"


@dataclass(frozen=True, slots=True)
class SourceRights:
    """Versioned permission evidence for one provider/source and intended use."""

    source_id: str
    rights_status: RightsStatus
    commercial_use_allowed: bool
    permitted_uses: frozenset[DataUsePurpose]
    terms_url: str | None = None
    terms_version: str | None = None
    verified_at_utc: datetime | None = None
    evidence_sha256: str | None = None
    attribution_required: bool = False
    attribution_text: str | None = None
    attribution_url: str | None = None
    terms_url: str | None = None
    terms_version: str | None = None
    evidence_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class RightsDecision:
    source_id: str
    purpose: DataUsePurpose
    allowed: bool
    reason_code: str
    attribution_text: str | None = None
    attribution_url: str | None = None
