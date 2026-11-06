"""Rights-gated conversion of settled, identity-verified provider fixtures to history."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from veltrix_v2.domain.contracts import (
    DataUsePurpose,
    RightsDecision,
    SourceRights,
)
from veltrix_v2.domain.identity import HistoricalMatch
from veltrix_v2.domain.rights import evaluate_source_use
from veltrix_v2.identity.registry import (
    MappingResolutionStatus,
    ResolvedProviderFixture,
)
from veltrix_v2.ingestion.providers.five_dollar_fixture import (
    FiveDollarFixtureRecord,
    FiveDollarFixtureStatus,
)


@dataclass(frozen=True, slots=True)
class HistoricalMatchImportDecision:
    allowed: bool
    reason_code: str
    historical_match: HistoricalMatch | None
    rights_decisions: tuple[RightsDecision, ...]


def build_training_history_match(
    fixture: FiveDollarFixtureRecord,
    resolved_identity: ResolvedProviderFixture,
    source_record_id: str,
    rights: SourceRights,
    canonical_fixture_id: str,
    *,
    evaluated_at_utc: datetime,
) -> HistoricalMatchImportDecision:
    """Create a training row only from settled results, verified identity and rights."""
    if evaluated_at_utc.tzinfo is None or evaluated_at_utc.utcoffset() is None:
        raise ValueError("evaluated_at_utc must be timezone-aware")
    if not source_record_id or not source_record_id.strip():
        raise ValueError("source_record_id is required")
    if not canonical_fixture_id or not canonical_fixture_id.strip():
        raise ValueError("canonical_fixture_id is required")

    if (
        resolved_identity.status is not MappingResolutionStatus.VERIFIED
        or resolved_identity.canonical_identity is None
        or resolved_identity.source_identity != fixture.source_identity
    ):
        return HistoricalMatchImportDecision(
            False, "PROVIDER_IDENTITY_NOT_VERIFIED", None, ()
        )
    if fixture.status is not FiveDollarFixtureStatus.FINISHED or not fixture.is_settled_result:
        return HistoricalMatchImportDecision(
            False, "FIXTURE_RESULT_NOT_SETTLED", None, ()
        )
    kickoff = fixture.source_identity.kickoff_at_utc.astimezone(timezone.utc)
    evaluated = evaluated_at_utc.astimezone(timezone.utc)
    if kickoff >= evaluated:
        return HistoricalMatchImportDecision(
            False, "FIXTURE_NOT_HISTORICAL_AT_IMPORT_TIME", None, ()
        )

    canonical = resolved_identity.canonical_identity
    if (
        canonical.provider != fixture.source_identity.provider
        or canonical.provider_fixture_id != fixture.source_identity.provider_fixture_id
        or canonical.provider_competition_id != fixture.source_identity.provider_competition_id
    ):
        return HistoricalMatchImportDecision(
            False, "CANONICAL_IDENTITY_SOURCE_MISMATCH", None, ()
        )

    purposes = (
        DataUsePurpose.HISTORICAL_IMPORT,
        DataUsePurpose.CACHE,
        DataUsePurpose.MODEL_TRAINING,
    )
    decisions = tuple(
        evaluate_source_use(
            rights,
            purpose,
            commercial=True,
            public_facing=False,
        )
        for purpose in purposes
    )
    denied = next((decision for decision in decisions if not decision.allowed), None)
    if denied is not None:
        return HistoricalMatchImportDecision(
            False, denied.reason_code, None, decisions
        )

    match = HistoricalMatch(
        historical_match_id=canonical_fixture_id,
        canonical_fixture_id=canonical_fixture_id,
        canonical_competition_id=canonical.canonical_competition_id,
        squad_category=canonical.squad_category.value,
        home_team_id=canonical.canonical_home_team_id,
        away_team_id=canonical.canonical_away_team_id,
        kickoff_at_utc=kickoff,
        home_goals=fixture.completed_home_goals,
        away_goals=fixture.completed_away_goals,
        source_record_ids=(source_record_id,),
        provider_fixture_refs=((
            fixture.source_identity.provider,
            fixture.source_identity.source_id,
            fixture.source_identity.provider_fixture_id,
        ),),
    )
    return HistoricalMatchImportDecision(
        True, "TRAINING_HISTORY_MATCH_ACCEPTED", match, decisions
    )
