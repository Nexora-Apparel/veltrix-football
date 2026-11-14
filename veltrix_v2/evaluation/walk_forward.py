"""Leakage-aware expanding-window evaluation for VELTRIX 2.0.

The evaluator scores historical fixtures only after their result is known,
while each forecast uses a cutoff strictly before that fixture's kickoff.
No random split, shuffled fold, legacy model, or external service is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Iterable

from veltrix_v2.models.poisson import (
    InsufficientHistoryError,
    MatchObservation,
    observation_eligible_as_of,
    predict_match,
)


@dataclass(frozen=True)
class BinaryMetrics:
    sample_count: int
    brier_score: float
    log_loss: float


@dataclass(frozen=True)
class MarketComparison:
    sample_count: int
    model_brier: float
    baseline_brier: float
    model_log_loss: float
    baseline_log_loss: float
    brier_improvement: float
    log_loss_improvement: float


@dataclass(frozen=True)
class FixtureEvaluation:
    fixture_id: str
    competition_id: str
    kickoff_at: datetime
    cutoff_at: datetime
    actual_home_goals: int
    actual_away_goals: int
    actual_1x2: str
    model_home_win: float
    model_draw: float
    model_away_win: float
    baseline_home_win: float
    baseline_draw: float
    baseline_away_win: float
    model_btts_yes: float
    baseline_btts_yes: float
    model_over_2_5: float
    baseline_over_2_5: float


@dataclass(frozen=True)
class WalkForwardReport:
    evaluation_as_of: datetime
    total_input_fixtures: int
    eligible_scored_fixtures: int
    skipped_no_history: int
    skipped_invalid_target: int
    skipped_duplicate_ids: int
    skipped_after_evaluation_as_of: int
    one_x_two: MarketComparison | None
    btts: MarketComparison | None
    over_2_5: MarketComparison | None
    fixtures: tuple[FixtureEvaluation, ...]
    skipped_date_only_targets: int = 0
    non_certifiable_input_rows: int = 0


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _pmf(mean: float, goals: int) -> float:
    return math.exp(-mean) * mean**goals / math.factorial(goals)


def _score_grid(home_mean: float, away_mean: float) -> tuple[float, float, float, float, float]:
    home = [_pmf(home_mean, i) for i in range(13)]
    away = [_pmf(away_mean, i) for i in range(13)]
    mass = sum(home) * sum(away)
    if mass <= 0 or not math.isfinite(mass):
        raise ValueError("BASELINE_SCORE_GRID_INVALID")
    h = d = a = btts = over = 0.0
    for hg, hp in enumerate(home):
        for ag, ap in enumerate(away):
            p = hp * ap / mass
            if hg > ag:
                h += p
            elif hg == ag:
                d += p
            else:
                a += p
            if hg > 0 and ag > 0:
                btts += p
            if hg + ag >= 3:
                over += p
    return h, d, a, btts, over


def _binary_metrics(probabilities: list[float], outcomes: list[int]) -> BinaryMetrics:
    if not probabilities:
        raise ValueError("METRICS_REQUIRE_NONEMPTY_SAMPLE")
    eps = 1e-15
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(outcomes)
    loss = -sum(
        math.log(min(max(p, eps), 1 - eps) if y else min(max(1 - p, eps), 1 - eps))
        for p, y in zip(probabilities, outcomes)
    ) / len(outcomes)
    return BinaryMetrics(len(outcomes), brier, loss)


def _multiclass_metrics(probabilities: list[tuple[float, float, float]], outcomes: list[int]) -> tuple[float, float]:
    if not probabilities:
        raise ValueError("METRICS_REQUIRE_NONEMPTY_SAMPLE")
    eps = 1e-15
    brier = 0.0
    loss = 0.0
    for probs, outcome in zip(probabilities, outcomes):
        brier += sum((p - (1.0 if i == outcome else 0.0)) ** 2 for i, p in enumerate(probs))
        loss -= math.log(min(max(probs[outcome], eps), 1.0))
    n = len(outcomes)
    return brier / n, loss / n


def _comparison(model_p: list[float], base_p: list[float], outcomes: list[int]) -> MarketComparison | None:
    if not outcomes:
        return None
    mm = _binary_metrics(model_p, outcomes)
    bm = _binary_metrics(base_p, outcomes)
    return MarketComparison(
        sample_count=len(outcomes), model_brier=mm.brier_score,
        baseline_brier=bm.brier_score, model_log_loss=mm.log_loss,
        baseline_log_loss=bm.log_loss,
        brier_improvement=bm.brier_score - mm.brier_score,
        log_loss_improvement=bm.log_loss - mm.log_loss,
    )


def walk_forward_evaluate(
    observations: Iterable[MatchObservation],
    *,
    evaluation_as_of: datetime,
    cutoff_buffer: timedelta = timedelta(seconds=1),
) -> WalkForwardReport:
    """Evaluate with an expanding chronological window and strict point-in-time cutoffs.

    A fixture is scored only if its outcome was both available and recorded by
    evaluation_as_of. Its model training set is independently reconstructed
    at kickoff minus cutoff_buffer. Duplicate fixture IDs are all excluded.
    Skips are counted explicitly rather than silently imputed.
    """
    if not _aware(evaluation_as_of):
        raise ValueError("EVALUATION_AS_OF_MUST_BE_TIMEZONE_AWARE")
    if not isinstance(cutoff_buffer, timedelta) or cutoff_buffer <= timedelta(0):
        raise ValueError("CUTOFF_BUFFER_MUST_BE_POSITIVE")
    rows = list(observations)
    id_counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, MatchObservation) and isinstance(row.fixture_id, str):
            id_counts[row.fixture_id] = id_counts.get(row.fixture_id, 0) + 1

    duplicate_ids = {key for key, count in id_counts.items() if count > 1}
    skipped_duplicate = sum(id_counts[key] for key in duplicate_ids)
    skipped_invalid = skipped_no_history = skipped_future = 0
    scored: list[FixtureEvaluation] = []
    non_certifiable_input_rows = sum(
        1 for row in rows if isinstance(row, MatchObservation)
        and row.point_in_time_certifiable is not True
    )

    valid_rows = [row for row in rows if isinstance(row, MatchObservation)
                  and row.fixture_id not in duplicate_ids]
    skipped_date_only_targets = sum(
        1 for row in valid_rows if row.kickoff_at is None and row.kickoff_date is not None
    )
    valid_rows = [row for row in valid_rows
                  if not (row.kickoff_at is None and row.kickoff_date is not None)]
    valid_rows.sort(key=lambda row: row.kickoff_at if _aware(row.kickoff_at)
                    else datetime.max.replace(tzinfo=evaluation_as_of.tzinfo))

    for target in valid_rows:
        if not _aware(target.kickoff_at) or not _aware(target.available_at) or not _aware(target.recorded_at):
            skipped_invalid += 1
            continue
        if (target.kickoff_at > evaluation_as_of or target.available_at > evaluation_as_of
                or target.recorded_at > evaluation_as_of):
            skipped_future += 1
            continue
        if (not isinstance(target.home_goals, int) or isinstance(target.home_goals, bool)
                or not isinstance(target.away_goals, int) or isinstance(target.away_goals, bool)
                or target.home_goals < 0 or target.away_goals < 0
                or not target.fixture_id or not target.competition_id
                or not target.home_team_id or not target.away_team_id
                or target.home_team_id == target.away_team_id):
            skipped_invalid += 1
            continue

        cutoff = target.kickoff_at - cutoff_buffer
        if cutoff >= target.kickoff_at:
            skipped_invalid += 1
            continue
        certified_training = [
            m for m in rows if isinstance(m, MatchObservation)
            and m.point_in_time_certifiable is True
            and id_counts.get(m.fixture_id, 0) == 1
        ]
        try:
            prediction = predict_match(
                certified_training, competition_id=target.competition_id,
                home_team_id=target.home_team_id, away_team_id=target.away_team_id,
                kickoff_at=target.kickoff_at, cutoff_at=cutoff,
            )
        except InsufficientHistoryError:
            skipped_no_history += 1
            continue
        except (TypeError, ValueError):
            skipped_invalid += 1
            continue

        training = [m for m in certified_training
                    if m.fixture_id != target.fixture_id
                    and observation_eligible_as_of(
                        m, cutoff_at=cutoff, competition_id=target.competition_id
                    )]
        if not training:
            skipped_no_history += 1
            continue
        league_home = sum(m.home_goals for m in training) / len(training)
        league_away = sum(m.away_goals for m in training) / len(training)
        if league_home <= 0 or league_away <= 0:
            skipped_no_history += 1
            continue
        base = _score_grid(league_home, league_away)
        actual = 0 if target.home_goals > target.away_goals else 1 if target.home_goals == target.away_goals else 2
        scored.append(FixtureEvaluation(
            fixture_id=target.fixture_id, competition_id=target.competition_id,
            kickoff_at=target.kickoff_at, cutoff_at=cutoff,
            actual_home_goals=target.home_goals, actual_away_goals=target.away_goals,
            actual_1x2=("HOME" if actual == 0 else "DRAW" if actual == 1 else "AWAY"),
            model_home_win=prediction.home_win, model_draw=prediction.draw,
            model_away_win=prediction.away_win,
            baseline_home_win=base[0], baseline_draw=base[1], baseline_away_win=base[2],
            model_btts_yes=prediction.btts_yes, baseline_btts_yes=base[3],
            model_over_2_5=prediction.over_2_5, baseline_over_2_5=base[4],
        ))

    model_1x2 = [(x.model_home_win, x.model_draw, x.model_away_win) for x in scored]
    base_1x2 = [(x.baseline_home_win, x.baseline_draw, x.baseline_away_win) for x in scored]
    outcomes_1x2 = [0 if x.actual_1x2 == "HOME" else 1 if x.actual_1x2 == "DRAW" else 2 for x in scored]
    if scored:
        model_brier, model_loss = _multiclass_metrics(model_1x2, outcomes_1x2)
        base_brier, base_loss = _multiclass_metrics(base_1x2, outcomes_1x2)
        one_x_two = MarketComparison(
            sample_count=len(scored), model_brier=model_brier, baseline_brier=base_brier,
            model_log_loss=model_loss, baseline_log_loss=base_loss,
            brier_improvement=base_brier - model_brier,
            log_loss_improvement=base_loss - model_loss,
        )
    else:
        one_x_two = None

    btts_outcomes = [int(x.actual_home_goals > 0 and x.actual_away_goals > 0) for x in scored]
    over_outcomes = [int(x.actual_home_goals + x.actual_away_goals >= 3) for x in scored]
    btts = _comparison([x.model_btts_yes for x in scored], [x.baseline_btts_yes for x in scored], btts_outcomes)
    over = _comparison([x.model_over_2_5 for x in scored], [x.baseline_over_2_5 for x in scored], over_outcomes)

    return WalkForwardReport(
        evaluation_as_of=evaluation_as_of, total_input_fixtures=len(rows),
        eligible_scored_fixtures=len(scored), skipped_no_history=skipped_no_history,
        skipped_invalid_target=skipped_invalid, skipped_duplicate_ids=skipped_duplicate,
        skipped_after_evaluation_as_of=skipped_future,
        one_x_two=one_x_two, btts=btts, over_2_5=over,
        fixtures=tuple(scored), skipped_date_only_targets=skipped_date_only_targets,
        non_certifiable_input_rows=non_certifiable_input_rows,
    )
