"""Fail-closed provider rights, data-type and freshness eligibility checks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from veltrix_v2.contracts import ForecastCutoff, ProviderObservation


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class SourceApproval:
    approval_id: str
    provider: str
    competition_key: str
    data_type: str
    status: str
    valid_from_utc: datetime
    valid_until_utc: datetime | None = None

    def __post_init__(self) -> None:
        if not all((self.approval_id, self.provider, self.competition_key, self.data_type)):
            raise ValueError("approval identifiers and scope are required")
        if self.status not in {"approved", "provisional", "revoked"}:
            raise ValueError("invalid approval status")
        object.__setattr__(self, "valid_from_utc", _utc(self.valid_from_utc, "valid_from_utc"))
        if self.valid_until_utc is not None:
            object.__setattr__(self, "valid_until_utc", _utc(self.valid_until_utc, "valid_until_utc"))
            if self.valid_until_utc <= self.valid_from_utc:
                raise ValueError("approval validity interval is empty")


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    eligible: bool
    reason: str
    approval_id: str | None


def evaluate_observation(
    observation: ProviderObservation,
    *,
    data_type: str,
    cutoff: ForecastCutoff,
    approvals: tuple[SourceApproval, ...],
    max_age: timedelta,
) -> EligibilityDecision:
    candidates = [
        item for item in approvals
        if item.approval_id == observation.rights_approval_id
        and item.provider == observation.provider
        and item.competition_key == observation.competition_key
        and item.data_type == data_type
        and item.status == "approved"
    ]
    if len(candidates) != 1:
        return EligibilityDecision(False, "no_unique_active_approval_for_provider_competition_data_type", None)
    approval = candidates[0]
    if cutoff.cutoff_utc < approval.valid_from_utc:
        return EligibilityDecision(False, "approval_not_yet_valid_at_cutoff", approval.approval_id)
    if approval.valid_until_utc and cutoff.cutoff_utc >= approval.valid_until_utc:
        return EligibilityDecision(False, "approval_expired_at_cutoff", approval.approval_id)
    if not cutoff.permits(observation) or observation.retrieved_at_utc > cutoff.cutoff_utc:
        return EligibilityDecision(False, "observation_not_available_at_forecast_cutoff", approval.approval_id)
    if cutoff.cutoff_utc - observation.retrieved_at_utc > max_age:
        return EligibilityDecision(False, "observation_stale_at_forecast_cutoff", approval.approval_id)
    return EligibilityDecision(True, "approved_and_point_in_time_valid", approval.approval_id)
