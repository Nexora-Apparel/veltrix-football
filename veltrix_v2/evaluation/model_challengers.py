"""Chronological challenger comparison for VELTRIX FOOTBALL 2.0.

All candidates are evaluated on the same target fixtures. Elo/form expected
scores are converted to 1X2 using only the pre-cutoff competition draw rate.
The conversion is an explicit transparent baseline, not a fitted probability
model. Equal-weight blends are diagnostic challengers, never auto-promoted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Iterable

from veltrix_v2.models.elo import ratings_as_of
from veltrix_v2.models.form import team_form_as_of
from veltrix_v2.models.poisson import (
    InsufficientHistoryError, MatchObservation, observation_eligible_as_of,
    predict_match,
)


@dataclass(frozen=True)
class ProbabilityVector:
    home: float
    draw: float
    away: float


@dataclass(frozen=True)
class ReliabilityBin:
    outcome_class: str
    lower: float
    upper: float
    count: int
    mean_probability: float
    observed_frequency: float


@dataclass(frozen=True)
class CandidateMetrics:
    sample_count: int
    multiclass_brier: float
    log_loss: float
    reliability: tuple[ReliabilityBin, ...]


@dataclass(frozen=True)
class FixtureCandidateRow:
    fixture_id: str
    competition_id: str
    kickoff_at: datetime
    cutoff_at: datetime
    actual_class: str
    predictions: dict[str, ProbabilityVector]


@dataclass(frozen=True)
class CompetitionReliability:
    competition_id: str
    sample_count: int
    metrics: dict[str, CandidateMetrics]


@dataclass(frozen=True)
class ChallengerComparisonReport:
    evaluation_as_of: datetime
    input_rows: int
    duplicate_fixture_rows: int
    scored_fixtures: int
    skipped_uncertified_targets: int
    skipped_after_evaluation_as_of: int
    skipped_invalid_targets: int
    skipped_without_shared_history: int
    metrics: dict[str, CandidateMetrics]
    competitions: tuple[CompetitionReliability, ...]
    fixtures: tuple[FixtureCandidateRow, ...]


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _normalise(p: ProbabilityVector) -> ProbabilityVector:
    values = (p.home, p.draw, p.away)
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("CHALLENGER_PROBABILITY_INVALID")
    total = sum(values)
    if total <= 0:
        raise ValueError("CHALLENGER_PROBABILITY_MASS_INVALID")
    return ProbabilityVector(*(x / total for x in values))


def _expected_score_to_1x2(expected_home_score: float, draw_rate: float) -> ProbabilityVector:
    if not math.isfinite(expected_home_score) or not math.isfinite(draw_rate):
        raise ValueError("CHALLENGER_EXPECTED_SCORE_INVALID")
    d = min(max(draw_rate, 0.0), 0.95)
    # E[score] = P(home win) + 0.5 * P(draw).
    e = min(max(expected_home_score, d / 2.0), 1.0 - d / 2.0)
    return _normalise(ProbabilityVector(e - d / 2.0, d, 1.0 - e - d / 2.0))


def _actual(row: MatchObservation) -> str:
    if row.home_goals > row.away_goals:
        return "HOME"
    if row.home_goals == row.away_goals:
        return "DRAW"
    return "AWAY"


def _blend(*vectors: ProbabilityVector) -> ProbabilityVector:
    n = len(vectors)
    return _normalise(ProbabilityVector(
        sum(x.home for x in vectors) / n,
        sum(x.draw for x in vectors) / n,
        sum(x.away for x in vectors) / n,
    ))


def _metrics(rows: list[FixtureCandidateRow], name: str) -> CandidateMetrics:
    if not rows:
        return CandidateMetrics(0, 0.0, 0.0, ())
    eps = 1e-15
    brier = loss = 0.0
    classes = ("HOME", "DRAW", "AWAY")
    for row in rows:
        p = row.predictions[name]
        vals = (p.home, p.draw, p.away)
        actual_index = classes.index(row.actual_class)
        brier += sum((v - (1.0 if i == actual_index else 0.0)) ** 2
                     for i, v in enumerate(vals))
        loss -= math.log(max(eps, vals[actual_index]))
    bins: list[ReliabilityBin] = []
    edges = [i / 10 for i in range(11)]
    for label, attr in zip(classes, ("home", "draw", "away")):
        for lower, upper in zip(edges[:-1], edges[1:]):
            selected = [row for row in rows
                        if lower <= getattr(row.predictions[name], attr)
                        and (getattr(row.predictions[name], attr) < upper
                             or upper == 1.0 and getattr(row.predictions[name], attr) <= upper)]
            if not selected:
                continue
            mean_p = sum(getattr(row.predictions[name], attr) for row in selected) / len(selected)
            observed = sum(row.actual_class == label for row in selected) / len(selected)
            bins.append(ReliabilityBin(label, lower, upper, len(selected), mean_p, observed))
    n = len(rows)
    return CandidateMetrics(n, brier / n, loss / n, tuple(bins))


def evaluate_model_challengers(
    observations: Iterable[MatchObservation],
    *,
    evaluation_as_of: datetime,
    cutoff_buffer: timedelta = timedelta(seconds=1),
) -> ChallengerComparisonReport:
    """Compare Poisson, Elo, form and equal-weight blends on identical fixtures."""
    if not _aware(evaluation_as_of):
        raise ValueError("CHALLENGER_EVALUATION_AS_OF_MUST_BE_AWARE")
    if not isinstance(cutoff_buffer, timedelta) or cutoff_buffer <= timedelta(0):
        raise ValueError("CHALLENGER_CUTOFF_BUFFER_MUST_BE_POSITIVE")

    source = list(observations)
    counts: dict[str, int] = {}
    for row in source:
        if isinstance(row, MatchObservation) and isinstance(row.fixture_id, str):
            counts[row.fixture_id] = counts.get(row.fixture_id, 0) + 1
    duplicate_ids = {key for key, count in counts.items() if count > 1}
    duplicate_rows = sum(counts[key] for key in duplicate_ids)
    unique = [row for row in source if isinstance(row, MatchObservation)
              and row.fixture_id not in duplicate_ids]
    unique.sort(key=lambda x: x.kickoff_at if _aware(x.kickoff_at)
                else datetime.max.replace(tzinfo=evaluation_as_of.tzinfo))

    scored: list[FixtureCandidateRow] = []
    skipped_uncertified = skipped_future = skipped_invalid = skipped_history = 0
    for target in unique:
        if target.point_in_time_certifiable is not True:
            skipped_uncertified += 1
            continue
        if not all(_aware(x) for x in (target.kickoff_at, target.available_at, target.recorded_at)):
            skipped_invalid += 1
            continue
        if target.kickoff_at > evaluation_as_of or target.available_at > evaluation_as_of or target.recorded_at > evaluation_as_of:
            skipped_future += 1
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
            poisson = predict_match(
                training, competition_id=target.competition_id,
                home_team_id=target.home_team_id, away_team_id=target.away_team_id,
                kickoff_at=target.kickoff_at, cutoff_at=cutoff,
            )
            elo = ratings_as_of(
                training, competition_id=target.competition_id,
                home_team_id=target.home_team_id, away_team_id=target.away_team_id,
                cutoff_at=cutoff,
            )
            form = team_form_as_of(
                training, competition_id=target.competition_id,
                home_team_id=target.home_team_id, away_team_id=target.away_team_id,
                cutoff_at=cutoff,
            )
        except (InsufficientHistoryError, TypeError, ValueError):
            skipped_history += 1
            continue

        draw_rate = sum(row.home_goals == row.away_goals for row in training) / len(training)
        p_poisson = _normalise(ProbabilityVector(poisson.home_win, poisson.draw, poisson.away_win))
        p_elo = _expected_score_to_1x2(elo.expected_home_score, draw_rate)
        # Explicit linear score mapping: 0.5 +/- (PPM differential / 6).
        # It is a transparent form baseline, not a fitted or calibrated model.
        form_score = 0.5 + (form.home.points_per_match - form.away.points_per_match) / 6.0
        p_form = _expected_score_to_1x2(min(max(form_score, 0.0), 1.0), draw_rate)
        predictions = {
            "poisson": p_poisson,
            "elo": p_elo,
            "form": p_form,
            "blend_poisson_elo": _blend(p_poisson, p_elo),
            "blend_poisson_form": _blend(p_poisson, p_form),
            "blend_elo_form": _blend(p_elo, p_form),
            "blend_all_equal": _blend(p_poisson, p_elo, p_form),
        }
        scored.append(FixtureCandidateRow(
            target.fixture_id, target.competition_id, target.kickoff_at, cutoff,
            _actual(target), predictions,
        ))

    names = ("poisson", "elo", "form", "blend_poisson_elo",
             "blend_poisson_form", "blend_elo_form", "blend_all_equal")
    metrics = {name: _metrics(scored, name) for name in names}
    competition_reports = []
    for competition in sorted({row.competition_id for row in scored}):
        subset = [row for row in scored if row.competition_id == competition]
        competition_reports.append(CompetitionReliability(
            competition, len(subset), {name: _metrics(subset, name) for name in names}
        ))
    return ChallengerComparisonReport(
        evaluation_as_of=evaluation_as_of, input_rows=len(source),
        duplicate_fixture_rows=duplicate_rows, scored_fixtures=len(scored),
        skipped_uncertified_targets=skipped_uncertified,
        skipped_after_evaluation_as_of=skipped_future,
        skipped_invalid_targets=skipped_invalid,
        skipped_without_shared_history=skipped_history,
        metrics=metrics, competitions=tuple(competition_reports),
        fixtures=tuple(scored),
    )
