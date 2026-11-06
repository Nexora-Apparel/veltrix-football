"""Verified provider-account capability profile.

A profile is an evidence-backed snapshot of the account's actual plan and
endpoint coverage. Published marketing pages or another user's plan do not
constitute an account profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum


class ProviderAccessStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    PROFILE_MISSING = "PROFILE_MISSING"
    PROFILE_STALE = "PROFILE_STALE"
    PROFILE_INVALID = "PROFILE_INVALID"
    COMPETITION_UNSUPPORTED = "COMPETITION_UNSUPPORTED"
    DATA_CLASS_UNAVAILABLE = "DATA_CLASS_UNAVAILABLE"
    HISTORY_WINDOW_INSUFFICIENT = "HISTORY_WINDOW_INSUFFICIENT"
    QUOTA_SNAPSHOT_MISSING = "QUOTA_SNAPSHOT_MISSING"


@dataclass(frozen=True, slots=True)
class ProviderAccessProfile:
    provider: str
    account_plan: str
    verified_at_utc: datetime
    verification_evidence_ref: str
    supported_competition_ids: frozenset[str]
    available_data_classes: frozenset[str]
    history_start_date: date | None
    quota_snapshot_id: str | None


@dataclass(frozen=True, slots=True)
class ProviderAccessDecision:
    provider: str
    status: ProviderAccessStatus
    reason_code: str
    missing_competition_ids: tuple[str, ...] = ()


def evaluate_provider_access(
    profile: ProviderAccessProfile | None,
    *,
    required_competition_ids: frozenset[str],
    required_data_class: str,
    required_history_start: date | None,
    now_utc: datetime,
    max_profile_age: timedelta = timedelta(days=7),
) -> ProviderAccessDecision:
    """Fail closed unless the verified account profile covers this workload."""
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    if max_profile_age < timedelta(0):
        raise ValueError("max_profile_age cannot be negative")

    if profile is None:
        return ProviderAccessDecision(
            "unknown", ProviderAccessStatus.PROFILE_MISSING, "ACCOUNT_PROFILE_MISSING"
        )

    now = now_utc.astimezone(timezone.utc)
    if profile.verified_at_utc.tzinfo is None or profile.verified_at_utc.utcoffset() is None:
        return ProviderAccessDecision(
            profile.provider, ProviderAccessStatus.PROFILE_INVALID, "PROFILE_TIMESTAMP_INVALID"
        )
    verified = profile.verified_at_utc.astimezone(timezone.utc)
    if verified > now:
        return ProviderAccessDecision(
            profile.provider, ProviderAccessStatus.PROFILE_INVALID, "PROFILE_VERIFIED_IN_FUTURE"
        )
    if now - verified > max_profile_age:
        return ProviderAccessDecision(
            profile.provider, ProviderAccessStatus.PROFILE_STALE, "ACCOUNT_PROFILE_STALE"
        )

    required_fields = (
        profile.provider,
        profile.account_plan,
        profile.verification_evidence_ref,
    )
    if any(not value or not value.strip() for value in required_fields):
        return ProviderAccessDecision(
            profile.provider or "unknown",
            ProviderAccessStatus.PROFILE_INVALID,
            "PROFILE_EVIDENCE_INCOMPLETE",
        )
    if not profile.quota_snapshot_id:
        return ProviderAccessDecision(
            profile.provider,
            ProviderAccessStatus.QUOTA_SNAPSHOT_MISSING,
            "QUOTA_SNAPSHOT_NOT_LINKED",
        )

    missing = tuple(sorted(required_competition_ids - profile.supported_competition_ids))
    if missing:
        return ProviderAccessDecision(
            profile.provider,
            ProviderAccessStatus.COMPETITION_UNSUPPORTED,
            "REQUIRED_COMPETITIONS_NOT_IN_ACCOUNT_PLAN",
            missing,
        )
    if required_data_class not in profile.available_data_classes:
        return ProviderAccessDecision(
            profile.provider,
            ProviderAccessStatus.DATA_CLASS_UNAVAILABLE,
            "REQUIRED_DATA_CLASS_NOT_IN_ACCOUNT_PLAN",
        )
    if required_history_start is not None:
        if profile.history_start_date is None or profile.history_start_date > required_history_start:
            return ProviderAccessDecision(
                profile.provider,
                ProviderAccessStatus.HISTORY_WINDOW_INSUFFICIENT,
                "REQUIRED_HISTORY_START_OUTSIDE_ACCOUNT_WINDOW",
            )

    return ProviderAccessDecision(
        profile.provider, ProviderAccessStatus.AVAILABLE, "ACCOUNT_PLAN_COVERS_REQUEST"
    )
