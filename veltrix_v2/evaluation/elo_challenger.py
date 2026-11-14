"""Chronological evaluation of Elo expected-score features.

This is deliberately not a 1X2 probability certification. Elo's expected
score (win=1, draw=.5, loss=0) is evaluated against a pre-cutoff competition
home-score baseline using only certified observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Iterable

from veltrix_v2.models.elo import ratings_as_of
from veltrix_v2.models.poisson import MatchObservation


@dataclass(frozen=True)
class ExpectedScoreMetrics:
    sample_count: int
    elo_brier: float
    baseline_brier: float
    brier_improvement: float


@dataclass(frozen=True)
class EloChallengerReport:
    evaluation_as_of: datetime
    input_rows: int
    scored_targets: int
    skipped_uncertified_targets: int
    skipped_invalid_targets: int
    skipped_without_history: int
    duplicate_fixture_rows: int
    metrics: ExpectedScoreMetrics | None


def evaluate_elo_challenger(
    observations: Iterable[MatchObservation],
    *,
    evaluation_as_of: datetime,
    cutoff_buffer: timedelta = timedelta(seconds=1),
) -> EloChallengerReport:
    if not isinstance(evaluation_as_of, datetime) or evaluation_as_of.tzinfo is None or evaluation_as_of.utcoffset() is None:
        raise ValueError("ELO_EVALUATION_AS_OF_MUST_BE_AWARE")
    if not isinstance(cutoff_buffer, timedelta) or cutoff_buffer <= timedelta(0):
        raise ValueError("ELO_CUTOFF_BUFFER_MUST_BE_POSITIVE")

    rows = list(observations)
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, MatchObservation) and isinstance(row.fixture_id, str):
            counts[row.fixture_id] = counts.get(row.fixture_id, 0) + 1
    duplicates = {key for key, count in counts.items() if count > 1}
    duplicate_rows = sum(counts[key] for key in duplicates)
    valid = [row for row in rows if isinstance(row, MatchObservation)
             and row.fixture_id not in duplicates]
    valid.sort(key=lambda row: row.kickoff_at if row.kickoff_at is not None
               else datetime.max.replace(tzinfo=evaluation_as_of.tzinfo))

    elo_losses: list[float] = []
    baseline_losses: list[float] = []
    skipped_uncertified = skipped_invalid = skipped_history = 0

    for target in valid:
        if target.point_in_time_certifiable is not True:
            skipped_uncertified += 1
            continue
        times = (target.kickoff_at, target.available_at, target.recorded_at)
        if any(not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None
               for value in times):
            skipped_invalid += 1
            continue
        if any(value > evaluation_as_of for value in times):
            continue
        if (not target.fixture_id or not target.competition_id or not target.home_team_id
                or not target.away_team_id or target.home_team_id == target.away_team_id
                or not isinstance(target.home_goals, int) or isinstance(target.home_goals, bool)
                or not isinstance(target.away_goals, int) or isinstance(target.away_goals, bool)
                or target.home_goals < 0 or target.away_goals < 0):
            skipped_invalid += 1
            continue

        cutoff = target.kickoff_at - cutoff_buffer
        training = [row for row in valid if row.fixture_id != target.fixture_id
                    and row.competition_id == target.competition_id
                    and row.point_in_time_certifiable is True
                    and row.kickoff_at is not None
                    and row.kickoff_at < cutoff
                    and row.available_at is not None and row.available_at <= cutoff
                    and row.recorded_at is not None and row.recorded_at <= cutoff]
        if not training:
            skipped_history += 1
            continue
        try:
            snapshot = ratings_as_of(
                training, competition_id=target.competition_id,
                home_team_id=target.home_team_id, away_team_id=target.away_team_id,
                cutoff_at=cutoff,
            )
        except (TypeError, ValueError):
            skipped_history += 1
            continue

        actual = 1.0 if target.home_goals > target.away_goals else (
            0.5 if target.home_goals == target.away_goals else 0.0
        )
        baseline = sum(
            1.0 if row.home_goals > row.away_goals else
            0.5 if row.home_goals == row.away_goals else 0.0
            for row in training
        ) / len(training)
        elo_losses.append((snapshot.expected_home_score - actual) ** 2)
        baseline_losses.append((baseline - actual) ** 2)

    metrics = None
    if elo_losses:
        elo_score = sum(elo_losses) / len(elo_losses)
        base_score = sum(baseline_losses) / len(baseline_losses)
        metrics = ExpectedScoreMetrics(
            sample_count=len(elo_losses), elo_brier=elo_score,
            baseline_brier=base_score, brier_improvement=base_score - elo_score,
        )
    return EloChallengerReport(
        evaluation_as_of=evaluation_as_of, input_rows=len(rows),
        scored_targets=len(elo_losses),
        skipped_uncertified_targets=skipped_uncertified,
        skipped_invalid_targets=skipped_invalid,
        skipped_without_history=skipped_history,
        duplicate_fixture_rows=duplicate_rows, metrics=metrics,
    )
