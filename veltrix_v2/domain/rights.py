"""Fail-closed data-rights gate for every V2 source use."""
from __future__ import annotations

from veltrix_v2.domain.contracts import (
    DataUsePurpose,
    RightsDecision,
    RightsStatus,
    SourceRights,
)


def evaluate_source_use(
    rights: SourceRights,
    purpose: DataUsePurpose,
    *,
    commercial: bool = True,
    public_facing: bool = False,
) -> RightsDecision:
    """Evaluate a specific use against verified source terms.

    Unknown rights, missing purpose grants, prohibited commercial use and
    unsatisfied public attribution requirements all fail closed.
    """
    if rights.rights_status is not RightsStatus.VERIFIED:
        return RightsDecision(
            rights.source_id, purpose, False, "RIGHTS_UNVERIFIED"
        )
    if purpose not in rights.permitted_uses:
        return RightsDecision(
            rights.source_id, purpose, False, "PURPOSE_NOT_PERMITTED"
        )
    if commercial and not rights.commercial_use_allowed:
        return RightsDecision(
            rights.source_id, purpose, False, "COMMERCIAL_USE_NOT_PERMITTED"
        )
    if public_facing and rights.attribution_required:
        if not rights.attribution_text or not rights.attribution_url:
            return RightsDecision(
                rights.source_id, purpose, False, "ATTRIBUTION_REQUIREMENT_UNSATISFIED"
            )
        return RightsDecision(
            rights.source_id,
            purpose,
            True,
            "ALLOWED",
            rights.attribution_text,
            rights.attribution_url,
        )
    return RightsDecision(rights.source_id, purpose, True, "ALLOWED")


def require_source_use(
    rights: SourceRights,
    purpose: DataUsePurpose,
    *,
    commercial: bool = True,
    public_facing: bool = False,
) -> RightsDecision:
    """Return an allowed decision or raise before data enters a V2 pipeline."""
    decision = evaluate_source_use(
        rights,
        purpose,
        commercial=commercial,
        public_facing=public_facing,
    )
    if not decision.allowed:
        raise ValueError(
            f"Source {rights.source_id!r} cannot be used for "
            f"{purpose.value}: {decision.reason_code}"
        )
    return decision
