"""Versioned, evidence-hashed provider rights approvals for VELTRIX V2."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval


REVIEWER_ID = "VELTRIX_PHASE2_RIGHTS_REVIEW_2026_11_12"
REPOSITORY = "Nexora-Apparel/veltrix-football"


def _approval(
    root: Path,
    *,
    approval_id: str,
    provider: str,
    source_id: str,
    data_type: str,
    evidence_path: str,
    terms_url: str,
    terms_version: str,
    rights_basis: str,
    permitted_uses: frozenset[DataUsePurpose],
    commercial_use_allowed: bool,
    attribution_required: bool = False,
    attribution_text: str | None = None,
    attribution_url: str | None = None,
    raw_redistribution_allowed: bool = False,
    status: ApprovalStatus = ApprovalStatus.APPROVED,
    competition_scope: str = "*",
    reviewed_at_utc: datetime,
) -> SourceApproval:
    evidence_file = root / evidence_path
    evidence_bytes = evidence_file.read_bytes()
    evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
    evidence_ref = f"https://github.com/{REPOSITORY}/blob/main/{evidence_path}"
    return SourceApproval(
        approval_id=approval_id,
        provider=provider,
        source_id=source_id,
        competition_scope=competition_scope,
        data_type=data_type,
        status=status,
        permitted_uses=permitted_uses,
        commercial_use_allowed=commercial_use_allowed,
        terms_url=terms_url,
        terms_version=terms_version,
        evidence_uri=evidence_ref,
        evidence_sha256=evidence_sha256,
        rights_basis=rights_basis,
        reviewed_at_utc=reviewed_at_utc,
        reviewer_id=REVIEWER_ID,
        valid_from_utc=reviewed_at_utc,
        attribution_required=attribution_required,
        attribution_text=attribution_text,
        attribution_url=attribution_url,
        raw_redistribution_allowed=raw_redistribution_allowed,
    )


def load_provider_rights_registry(
    repository_root: str | Path,
    *,
    reviewed_at_utc: datetime | None = None,
) -> tuple[SourceApproval, ...]:
    """Load approvals only when their exact local review evidence is present.

    Provider rights and provider account entitlements are separate gates.
    In particular, the Odds API historical archive remains PROVISIONAL until
    the account's paid historical endpoint entitlement is independently proven.
    """
    root = Path(repository_root).resolve(strict=True)
    reviewed = reviewed_at_utc or datetime.now(timezone.utc)
    if reviewed.tzinfo is None or reviewed.utcoffset() is None:
        raise ValueError("RIGHTS_REVIEW_TIME_MUST_BE_TIMEZONE_AWARE")

    five_dollar_uses = frozenset({
        DataUsePurpose.COLLECTION,
        DataUsePurpose.STORAGE,
        DataUsePurpose.HISTORICAL_IMPORT,
        DataUsePurpose.MODEL_TRAINING,
        DataUsePurpose.BENCHMARKING,
        DataUsePurpose.CACHE,
        DataUsePurpose.PUBLIC_DISPLAY,
    })
    odds_current_uses = frozenset({
        DataUsePurpose.COLLECTION,
        DataUsePurpose.STORAGE,
        DataUsePurpose.MODEL_TRAINING,
        DataUsePurpose.BENCHMARKING,
        DataUsePurpose.CACHE,
        DataUsePurpose.PUBLIC_DISPLAY,
    })
    wyscout_uses = frozenset({
        DataUsePurpose.COLLECTION,
        DataUsePurpose.STORAGE,
        DataUsePurpose.HISTORICAL_IMPORT,
        DataUsePurpose.MODEL_TRAINING,
        DataUsePurpose.BENCHMARKING,
        DataUsePurpose.CACHE,
        DataUsePurpose.PUBLIC_DISPLAY,
    })

    return (
        _approval(
            root,
            approval_id="rights-5dollar-fixture-result-2026-11-12",
            provider="5DollarFootballAPI",
            source_id="5dollarfootballapi",
            data_type="fixture_result",
            evidence_path="docs/legal/5dollar-terms-review-2026-11-12.md",
            terms_url="https://5dollarfootballapi.com/terms",
            terms_version="October 2026",
            rights_basis="TERMS",
            permitted_uses=five_dollar_uses,
            commercial_use_allowed=True,
            attribution_required=True,
            attribution_text="Football data by 5DollarFootballAPI",
            attribution_url="https://5dollarfootballapi.com",
            reviewed_at_utc=reviewed,
        ),
        _approval(
            root,
            approval_id="rights-the-odds-api-current-odds-2026-11-12",
            provider="The Odds API",
            source_id="the-odds-api",
            data_type="bookmaker_odds_current",
            evidence_path="docs/legal/the-odds-api-terms-review-2026-11-12.md",
            terms_url="https://the-odds-api.com/terms-and-conditions.html",
            terms_version="2026-08-31",
            rights_basis="TERMS",
            permitted_uses=odds_current_uses,
            commercial_use_allowed=True,
            attribution_required=False,
            reviewed_at_utc=reviewed,
        ),
        _approval(
            root,
            approval_id="rights-the-odds-api-historical-odds-provisional-2026-11-12",
            provider="The Odds API",
            source_id="the-odds-api",
            data_type="bookmaker_odds_historical",
            evidence_path="docs/legal/the-odds-api-terms-review-2026-11-12.md",
            terms_url="https://the-odds-api.com/terms-and-conditions.html",
            terms_version="2026-08-31",
            rights_basis="TERMS",
            permitted_uses=frozenset(),
            commercial_use_allowed=False,
            status=ApprovalStatus.PROVISIONAL,
            reviewed_at_utc=reviewed,
        ),
        _approval(
            root,
            approval_id="rights-wyscout-open-events-cc-by-4-0-2026-11-12",
            provider="Pappalardo et al. Wyscout Open Event Dataset",
            source_id="wyscout-open-events",
            data_type="historical_shot_events",
            evidence_path="docs/legal/wyscout-cc-by-4.0-review-2026-11-12.md",
            terms_url="https://creativecommons.org/licenses/by/4.0/",
            terms_version="CC BY 4.0",
            rights_basis="OPEN_LICENSE",
            permitted_uses=wyscout_uses,
            commercial_use_allowed=True,
            attribution_required=True,
            attribution_text=(
                "Shot-event training data: Pappalardo et al. (2019), "
                "A public data set of spatio-temporal match events in soccer competitions, "
                "CC BY 4.0. Adapted to train the VELTRIX xG model."
            ),
            attribution_url="https://figshare.com/collections/Soccer_match_event_dataset/4415000",
            reviewed_at_utc=reviewed,
        ),
    )
