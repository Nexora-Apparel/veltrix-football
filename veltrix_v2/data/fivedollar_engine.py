"""Rights-scoped, offline 5Dollar-to-forecast batch orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from veltrix_v2.data.contracts import (
    ApprovalStatus,
    DataUsePurpose,
    FixtureStatus,
    HistoricalFixture,
    SourceApproval,
)
from veltrix_v2.data.observation_adapter import (
    historical_fixture_to_observation,
    historical_fixture_to_target,
)
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.models.engine import BatchForecastReport, predict_batch
from veltrix_v2.models.poisson import MatchObservation


@dataclass(frozen=True)
class FiveDollarForecastBatch:
    approval_id: str
    competition_scope: tuple[str, ...]
    source_fixture_count: int
    observation_count: int
    target_count: int
    skipped_duplicate_source_fixtures: int
    skipped_rights: int
    skipped_unsettled: int
    skipped_unavailable_results: int
    prediction_report: BatchForecastReport


def _approval_competitions(approval: SourceApproval) -> set[str]:
    return {
        item.strip() for item in approval.competition_scope.split(",")
        if item.strip()
    }


def build_fivedollar_forecast_batch(
    fixtures: Iterable[HistoricalFixture],
    *,
    approval: SourceApproval,
    cutoff_at: datetime,
    max_fixtures: int = 25,
    recency_half_life_days: float | None = None,
) -> FiveDollarForecastBatch:
    """Assemble a future forecast batch from parsed provider fixtures.

    No network, database or filesystem access occurs here. Source approval is
    evaluated for each use. Finished results retain their actual retrieval
    time and conservative availability basis; scheduled fixtures are targets
    only when their snapshot was retrieved before cutoff and kickoff is future.
    """
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("BATCH_CUTOFF_MUST_BE_TIMEZONE_AWARE")
    if approval.status is not ApprovalStatus.APPROVED:
        raise ValueError("FIVEDOLLAR_SOURCE_APPROVAL_NOT_APPROVED")
    if approval.provider != "5DollarFootballAPI" or approval.source_id != "5dollarfootballapi":
        raise ValueError("FIVEDOLLAR_SOURCE_APPROVAL_IDENTITY_MISMATCH")
    if approval.data_type not in {"fixture_result", "fixtures_and_results"}:
        raise ValueError("FIVEDOLLAR_SOURCE_APPROVAL_DATA_TYPE_MISMATCH")
    competitions = _approval_competitions(approval)
    if not competitions or "*" in competitions:
        raise ValueError("FIVEDOLLAR_COMPETITION_SCOPE_INVALID")

    rows = list(fixtures)
    counts: dict[str, int] = {}
    for fixture in rows:
        if isinstance(fixture, HistoricalFixture):
            key = fixture.provider_fixture_id
            counts[key] = counts.get(key, 0) + 1
    duplicates = {key for key, count in counts.items() if count > 1}
    skipped_duplicates = sum(counts[key] for key in duplicates)

    observations: list[MatchObservation] = []
    targets = []
    skipped_rights = skipped_unsettled = skipped_unavailable = 0

    for fixture in rows:
        if not isinstance(fixture, HistoricalFixture):
            skipped_unsettled += 1
            continue
        if fixture.provider_fixture_id in duplicates:
            continue
        if fixture.provider != approval.provider or fixture.source_id != approval.source_id:
            skipped_rights += 1
            continue
        if fixture.provider_competition_id not in competitions:
            skipped_rights += 1
            continue
        if fixture.rights_approval_id != approval.approval_id:
            skipped_rights += 1
            continue

        if fixture.status is FixtureStatus.FINISHED:
            purposes = (
                DataUsePurpose.COLLECTION,
                DataUsePurpose.STORAGE,
                DataUsePurpose.MODEL_TRAINING,
            )
        elif fixture.status is FixtureStatus.SCHEDULED:
            purposes = (DataUsePurpose.COLLECTION, DataUsePurpose.CACHE)
        else:
            skipped_unsettled += 1
            continue

        decisions = [
            evaluate_source_use(approval, purpose, at_utc=cutoff_at, commercial=True)
            for purpose in purposes
        ]
        if any(not decision.allowed for decision in decisions):
            skipped_rights += 1
            continue

        if fixture.status is FixtureStatus.FINISHED:
            observation = historical_fixture_to_observation(fixture)
            if observation is None:
                skipped_unavailable += 1
            else:
                observations.append(observation)
        else:
            target = historical_fixture_to_target(fixture)
            if target is None or target.retrieved_at > cutoff_at:
                skipped_unavailable += 1
            else:
                targets.append(target)

    prediction_report = predict_batch(
        observations, targets, cutoff_at=cutoff_at, max_fixtures=max_fixtures,
        recency_half_life_days=recency_half_life_days,
    )
    return FiveDollarForecastBatch(
        approval_id=approval.approval_id,
        competition_scope=tuple(sorted(competitions)),
        source_fixture_count=len(rows),
        observation_count=len(observations),
        target_count=len(targets),
        skipped_duplicate_source_fixtures=skipped_duplicates,
        skipped_rights=skipped_rights,
        skipped_unsettled=skipped_unsettled,
        skipped_unavailable_results=skipped_unavailable,
        prediction_report=prediction_report,
    )
