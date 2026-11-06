"""Fail-closed data-rights gate for every V2 source use."""
from __future__ import annotations

from datetime import timezone
from string import hexdigits

from veltrix_v2.domain.contracts import (
    DataUsePurpose,
    RightsDecision,
    RightsStatus,
    SourceRights,
)


def _decision(
    rights: SourceRights,
    purpose: DataUsePurpose,
    allowed: bool,
    reason_code: str,
    *,
    attribution: bool = False,
) -> RightsDecision:
    return RightsDecision(
        source_id=rights.source_id,
        purpose=purpose,
        allowed=allowed,
        reason_code=reason_code,
        attribution_text=rights.attribution_text if attribution else None,
        attribution_url=rights.attribution_url if attribution else None,
        terms_url=rights.terms_url,
        terms_version=rights.terms_version,
        evidence_sha256=rights.evidence_sha256,
    )


def _evidence_is_complete(rights: SourceRights) -> bool:
    digest = rights.evidence_sha256 or ""
    verified_at = rights.verified_at_utc
    return bool(
        rights.source_id.strip()
        and rights.terms_url
        and rights.terms_version
        and verified_at is not None
        and verified_at.tzinfo is not None
        and verified_at.utcoffset() is not None
        and len(digest) == 64
        and all(character in hexdigits for character in digest)
        and rights.permitted_uses
    )


def evaluate_source_use(
    rights: SourceRights,
    purpose: DataUsePurpose,
    *,
    commercial: bool = True,
    public_facing: bool = False,
) -> RightsDecision:
    """Evaluate a specific use against verified source terms.

    Unknown or incompletely evidenced rights, missing purpose grants,
    prohibited commercial use and unsatisfied public attribution all fail closed.
    """
    if rights.rights_status is not RightsStatus.VERIFIED:
        return _decision(rights, purpose, False, "RIGHTS_UNVERIFIED")
    if not _evidence_is_complete(rights):
        return _decision(rights, purpose, False, "RIGHTS_EVIDENCE_INCOMPLETE")
    if purpose not in rights.permitted_uses:
        return _decision(rights, purpose, False, "PURPOSE_NOT_PERMITTED")
    if commercial and not rights.commercial_use_allowed:
        return _decision(rights, purpose, False, "COMMERCIAL_USE_NOT_PERMITTED")
    if public_facing and rights.attribution_required:
        if not rights.attribution_text or not rights.attribution_url:
            return _decision(
                rights, purpose, False, "ATTRIBUTION_REQUIREMENT_UNSATISFIED"
            )
        return _decision(
            rights, purpose, True, "ALLOWED", attribution=True
        )
    return _decision(rights, purpose, True, "ALLOWED")


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
