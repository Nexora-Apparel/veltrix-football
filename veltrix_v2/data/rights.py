"""Fail-closed source rights evaluation for historical data imports."""
from __future__ import annotations

from datetime import datetime, timezone

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, RightsDecision, SourceApproval,
)


def evaluate_source_use(
    approval: SourceApproval,
    purpose: DataUsePurpose,
    *,
    at_utc: datetime,
    commercial: bool = True,
    public_facing: bool = False,
) -> RightsDecision:
    if at_utc.tzinfo is None or at_utc.utcoffset() is None:
        raise ValueError("RIGHTS_EVALUATION_TIME_MUST_BE_TIMEZONE_AWARE")
    at = at_utc.astimezone(timezone.utc)
    if approval.status is not ApprovalStatus.APPROVED:
        return RightsDecision(False, "SOURCE_RIGHTS_NOT_APPROVED", approval.approval_id)
    if at < approval.valid_from_utc.astimezone(timezone.utc):
        return RightsDecision(False, "SOURCE_APPROVAL_NOT_YET_VALID", approval.approval_id)
    if approval.valid_until_utc and at >= approval.valid_until_utc.astimezone(timezone.utc):
        return RightsDecision(False, "SOURCE_APPROVAL_EXPIRED", approval.approval_id)
    if purpose is DataUsePurpose.RAW_REDISTRIBUTION and not approval.raw_redistribution_allowed:
        return RightsDecision(False, "RAW_REDISTRIBUTION_PROHIBITED", approval.approval_id)
    if purpose not in approval.permitted_uses:
        return RightsDecision(False, "PURPOSE_NOT_PERMITTED", approval.approval_id)
    if commercial and not approval.commercial_use_allowed:
        return RightsDecision(False, "COMMERCIAL_USE_NOT_PERMITTED", approval.approval_id)
    if public_facing and approval.attribution_required:
        if not approval.attribution_text or not approval.attribution_url:
            return RightsDecision(False, "ATTRIBUTION_REQUIREMENT_UNSATISFIED", approval.approval_id)
        return RightsDecision(
            True, "APPROVED_WITH_ATTRIBUTION", approval.approval_id,
            approval.attribution_text, approval.attribution_url,
        )
    return RightsDecision(True, "APPROVED", approval.approval_id)


def evaluate_fixture_import(
    fixture,
    approval: SourceApproval,
    *,
    evaluated_at_utc: datetime,
) -> FixtureImportDecision:
    from veltrix_v2.data.contracts import FixtureImportDecision, FixtureStatus, ImportOutcomeStatus

    if approval.provider != fixture.provider or approval.source_id != fixture.source_id:
        return FixtureImportDecision(
            ImportOutcomeStatus.QUARANTINED, "SOURCE_APPROVAL_IDENTITY_MISMATCH",
            fixture.provider_fixture_id,
        )
    # Scope is an explicit comma-separated allowlist of provider competition IDs.
    # Wildcards are intentionally unsupported: a broad provider approval must never
    # silently expand beyond the competitions actually reviewed and entitled.
    approved_competitions = {
        item.strip()
        for item in approval.competition_scope.split(",")
        if item.strip()
    }
    if (
        not approved_competitions
        or "*" in approved_competitions
        or fixture.provider_competition_id not in approved_competitions
    ):
        return FixtureImportDecision(
            ImportOutcomeStatus.QUARANTINED, "COMPETITION_OUTSIDE_SOURCE_APPROVAL",
            fixture.provider_fixture_id,
        )
    if approval.data_type not in {"fixture_result", "fixtures_and_results"}:
        return FixtureImportDecision(
            ImportOutcomeStatus.QUARANTINED, "DATA_TYPE_OUTSIDE_SOURCE_APPROVAL",
            fixture.provider_fixture_id,
        )
    if fixture.rights_approval_id != approval.approval_id:
        return FixtureImportDecision(
            ImportOutcomeStatus.QUARANTINED, "RIGHTS_APPROVAL_REFERENCE_MISMATCH",
            fixture.provider_fixture_id,
        )
    purposes = (
        DataUsePurpose.COLLECTION,
        DataUsePurpose.STORAGE,
        DataUsePurpose.HISTORICAL_IMPORT,
        DataUsePurpose.MODEL_TRAINING,
    )
    decisions = tuple(
        evaluate_source_use(approval, purpose, at_utc=evaluated_at_utc, commercial=True)
        for purpose in purposes
    )
    denied = next((decision for decision in decisions if not decision.allowed), None)
    if denied:
        return FixtureImportDecision(
            ImportOutcomeStatus.QUARANTINED, denied.reason_code,
            fixture.provider_fixture_id, decisions,
        )
    if fixture.status is not FixtureStatus.FINISHED:
        return FixtureImportDecision(
            ImportOutcomeStatus.REJECTED, "FIXTURE_NOT_SETTLED",
            fixture.provider_fixture_id, decisions,
        )
    if fixture.kickoff_at_utc >= evaluated_at_utc:
        return FixtureImportDecision(
            ImportOutcomeStatus.REJECTED, "FIXTURE_NOT_HISTORICAL",
            fixture.provider_fixture_id, decisions,
        )
    if fixture.retrieved_at_utc < fixture.kickoff_at_utc:
        return FixtureImportDecision(
            ImportOutcomeStatus.QUARANTINED, "SOURCE_RETRIEVAL_PRECEDES_KICKOFF",
            fixture.provider_fixture_id, decisions,
        )
    return FixtureImportDecision(
        ImportOutcomeStatus.IMPORTABLE, "RIGHTS_AND_SETTLEMENT_VERIFIED",
        fixture.provider_fixture_id, decisions,
    )
