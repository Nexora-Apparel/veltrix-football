"""Combined offline provider-account and quota preflight gate."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from veltrix_v2.ingestion.budget import (
    QuotaDecision,
    QuotaSnapshot,
    evaluate_quota_request,
)
from veltrix_v2.ingestion.ports import ProviderRequestSpec
from veltrix_v2.ingestion.provider_access import (
    ProviderAccessDecision,
    ProviderAccessProfile,
    ProviderAccessStatus,
    evaluate_provider_access,
)


@dataclass(frozen=True, slots=True)
class IngestionPreflightDecision:
    allowed: bool
    reason_code: str
    provider_access: ProviderAccessDecision
    quota: QuotaDecision


def evaluate_ingestion_preflight(
    profile: ProviderAccessProfile | None,
    quota_snapshot: QuotaSnapshot | None,
    request: ProviderRequestSpec,
    *,
    now_utc: datetime,
) -> IngestionPreflightDecision:
    """Fail closed unless account capability and matching quota evidence agree.

    This function is pure and offline. It does not reserve quota or call a
    provider. The quota repository must still perform an atomic reservation
    immediately before transport execution.
    """
    access = evaluate_provider_access(
        profile,
        required_competition_ids=frozenset(request.competition_ids),
        required_data_class=request.data_class,
        required_history_start=request.history_start_date,
        now_utc=now_utc,
    )

    if profile is not None and profile.provider != request.provider:
        access = ProviderAccessDecision(
            profile.provider, ProviderAccessStatus.PROFILE_INVALID,
            "ACCOUNT_PROVIDER_MISMATCH",
        )

    if quota_snapshot is None:
        quota = evaluate_quota_request(
            None, requested_units=request.quota_units, now_utc=now_utc
        )
    elif (
        quota_snapshot.provider != request.provider
        or quota_snapshot.quota_scope != request.quota_scope
    ):
        quota = QuotaDecision(
            False, "QUOTA_PROVIDER_OR_SCOPE_MISMATCH",
            request.provider, request.quota_scope, request.quota_units,
            0, quota_snapshot.snapshot_id,
        )
    elif profile is not None and profile.quota_snapshot_id != quota_snapshot.snapshot_id:
        quota = QuotaDecision(
            False, "QUOTA_PROFILE_SNAPSHOT_MISMATCH",
            request.provider, request.quota_scope, request.quota_units,
            0, quota_snapshot.snapshot_id,
        )
    else:
        quota = evaluate_quota_request(
            quota_snapshot,
            requested_units=request.quota_units,
            now_utc=now_utc,
        )

    if access.status is not ProviderAccessStatus.AVAILABLE:
        return IngestionPreflightDecision(
            False, access.reason_code, access, quota
        )
    if not quota.allowed:
        return IngestionPreflightDecision(
            False, quota.reason_code, access, quota
        )
    return IngestionPreflightDecision(
        True, "INGESTION_PREFLIGHT_ALLOWED", access, quota
    )
