"""Expanding-window team-form expected-score challenger evaluation.

This is a score-feature diagnostic, not a 1X2 probability or calibration claim.
Every target uses form reconstructed from the same-competition, certified
history available strictly before its cutoff.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from veltrix_v2.models.form import team_form_as_of
from veltrix_v2.models.poisson import MatchObservation, observation_eligible_as_of


@dataclass(frozen=True)
class FormExpectedScoreMetrics:
    sample_count: int
    form_mse: float
    competition_baseline_mse: float
    mse_improvement: float


@dataclass(frozen=True)
class TeamFormChallengerReport:
    evaluation_as_of: datetime
    input_rows: int
    scored_targets: int
    skipped_uncertified_targets: int
    skipped_invalid_targets: int
    skipped_without_history: int
    duplicate_fixture_rows: int
    metrics: FormExpectedScoreMetrics | None


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def evaluate_team_form_challenger(
    observations: Iterable[MatchObservation],
    *,
    evaluation_as_of: datetime,
    cutoff_buffer: timedelta = timedelta(seconds=1),
) -> TeamFormChallengerReport:
    if not _aware(evaluation_as_of):
        raise ValueError("TEAM_FORM_EVALUATION_AS_OF_MUST_BE_AWARE")
    if not isinstance(cutoff_buffer, timedelta) or cutoff_buffer <= timedelta(0):
        raise ValueError("TEAM_FORM_CUTOFF_BUFFER_MUST_BE_POSITIVE")

    rows = list(observations)
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, MatchObservation) and isinstance(row.fixture_id, str):
            counts[row.fixture_id] = counts.get(row.fixture_id, 0) + 1
    duplicate_ids = {key for key, count in counts.items() if count > 1}
    duplicate_rows = sum(counts[key] for key in duplicate_ids)
    unique = [row for row in rows if isinstance(row, MatchObservation)
              and row.fixture_id not in duplicate_ids]
    unique.sort(key=lambda row: row.kickoff_at if _aware(row.kickoff_at)
                else datetime.max.replace(tzinfo=evaluation_as_of.tzinfo))

    form_losses: list[float] = []
    baseline_losses: list[float] = []
    skipped_uncertified = skipped_invalid = skipped_history = 0

    for target in unique:
        if target.point_in_time_certifiable is not True:
            skipped_uncertified += 1
            continue
        if not all(_aware(x) for x in (target.kickoff_at, target.available_at, target.recorded_at)):
            skipped_invalid += 1
            continue
        if (target.kickoff_at > evaluation_as_of or target.available_at > evaluation_as_of
                or target.recorded_at > evaluation_as_of):
            continue
        if (not target.fixture_id or not target.competition_id or not target.home_team_id
                or not target.away_team_id or target.home_team_id == target.away_team_id
                or any(not isinstance(x, int) or isinstance(x, bool) or x < 0
                       for x in (target.home_goals, target.away_goals))):
            skipped_invalid += 1
            continue

        cutoff = target.kickoff_at - cutoff_buffer
        training = [row for row in unique
                    if row.fixture_id != target.fixture_id
                    and row.point_in_time_certifiable is True
                    and observation_eligible_as_of(row, cutoff_at=cutoff,
                                                   competition_id=target.competition_id)]
        if not training:
            skipped_history += 1
            continue
        try:
            snapshot = team_form_as_of(
                training, competition_id=target.competition_id,
                home_team_id=target.home_team_id, away_team_id=target.away_team_id,
                cutoff_at=cutoff,
            )
        except (TypeError, ValueError):
            skipped_history += 1
            continue

        form_expected = min(max(
            0.5 + (snapshot.home.points_per_match - snapshot.away.points_per_match) / 6.0,
            0.0,
        ), 1.0)
        baseline_expected = sum(
            1.0 if row.home_goals > row.away_goals else
            0.5 if row.home_goals == row.away_goals else 0.0
            for row in training
        ) / len(training)
        actual = 1.0 if target.home_goals > target.away_goals else (
            0.5 if target.home_goals == target.away_goals else 0.0
        )
        form_losses.append((form_expected - actual) ** 2)
        baseline_losses.append((baseline_expected - actual) ** 2)

    metrics = None
    if form_losses:
        form_mse = sum(form_losses) / len(form_losses)
        baseline_mse = sum(baseline_losses) / len(baseline_losses)
        metrics = FormExpectedScoreMetrics(
            len(form_losses), form_mse, baseline_mse, baseline_mse - form_mse
        )
    return TeamFormChallengerReport(
        evaluation_as_of=evaluation_as_of, input_rows=len(rows),
        scored_targets=len(form_losses),
        skipped_uncertified_targets=skipped_uncertified,
        skipped_invalid_targets=skipped_invalid,
        skipped_without_history=skipped_history,
        duplicate_fixture_rows=duplicate_rows, metrics=metrics,
    )
