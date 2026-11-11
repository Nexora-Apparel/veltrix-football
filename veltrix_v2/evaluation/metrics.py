"""Strict, deterministic proper-scoring metrics for 1X2 evaluation.

Inputs must already be joined by immutable fixture identity and represent
out-of-sample forecasts. This module never fits, calibrates or repairs scores.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log
from numbers import Real
from typing import Iterable, Literal

Outcome1X2 = Literal["HOME", "DRAW", "AWAY"]
# Ordered by home goal difference: away win < draw < home win.
_CLASS_ORDER: tuple[Outcome1X2, ...] = ("AWAY", "DRAW", "HOME")


@dataclass(frozen=True, slots=True)
class Forecast1X2:
    fixture_id: str
    p_home: float
    p_draw: float
    p_away: float

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        values = (self.p_home, self.p_draw, self.p_away)
        if any(isinstance(value, bool) or not isinstance(value, Real) for value in values):
            raise ValueError("1X2 probabilities must be real numbers")
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("1X2 probabilities must be finite")
        if any(value <= 0.0 or value > 1.0 for value in values):
            raise ValueError("1X2 probabilities must be in (0, 1]")
        if abs(sum(values) - 1.0) > 1e-9:
            raise ValueError("1X2 probabilities must sum to one")


@dataclass(frozen=True, slots=True)
class SettledOutcome1X2:
    fixture_id: str
    outcome: Outcome1X2

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if self.outcome not in _CLASS_ORDER:
            raise ValueError("outcome must be HOME, DRAW or AWAY")


@dataclass(frozen=True, slots=True)
class ScoreReport1X2:
    sample_size: int
    multiclass_brier: float
    log_loss: float
    ranked_probability_score: float


@dataclass(frozen=True, slots=True)
class BenchmarkComparison1X2:
    sample_size: int
    model_report: ScoreReport1X2
    benchmark_report: ScoreReport1X2
    brier_delta: float
    log_loss_delta: float
    ranked_probability_score_delta: float
    model_beats_brier: bool
    model_beats_log_loss: bool


def score_1x2(
    forecasts: Iterable[Forecast1X2],
    outcomes: Iterable[SettledOutcome1X2],
) -> ScoreReport1X2:
    """Score one-to-one matched out-of-sample 1X2 forecasts and results.

    Brier is the mean sum of the three class-wise squared errors.
    RPS follows the ordinal home-goal-difference order AWAY/DRAW/HOME.
    """
    forecast_rows = tuple(forecasts)
    outcome_rows = tuple(outcomes)
    forecast_ids = [row.fixture_id for row in forecast_rows]
    outcome_ids = [row.fixture_id for row in outcome_rows]
    if len(forecast_ids) != len(set(forecast_ids)):
        raise ValueError("duplicate forecast fixture IDs")
    if len(outcome_ids) != len(set(outcome_ids)):
        raise ValueError("duplicate outcome fixture IDs")
    if not forecast_rows:
        raise ValueError("at least one matched forecast is required")
    if set(forecast_ids) != set(outcome_ids):
        raise ValueError("forecast and outcome fixture identities must match exactly")

    outcome_by_id = {row.fixture_id: row.outcome for row in outcome_rows}
    brier_total = 0.0
    log_loss_total = 0.0
    rps_total = 0.0
    for forecast in forecast_rows:
        actual = outcome_by_id[forecast.fixture_id]
        probabilities = (forecast.p_away, forecast.p_draw, forecast.p_home)
        observed = tuple(1.0 if actual == label else 0.0 for label in _CLASS_ORDER)
        brier_total += sum((p - y) ** 2 for p, y in zip(probabilities, observed))
        log_loss_total -= log(probabilities[_CLASS_ORDER.index(actual)])
        predicted_cumulative = (probabilities[0], probabilities[0] + probabilities[1])
        observed_cumulative = (observed[0], observed[0] + observed[1])
        rps_total += sum(
            (predicted - target) ** 2
            for predicted, target in zip(predicted_cumulative, observed_cumulative)
        ) / 2.0

    count = len(forecast_rows)
    return ScoreReport1X2(
        sample_size=count,
        multiclass_brier=brier_total / count,
        log_loss=log_loss_total / count,
        ranked_probability_score=rps_total / count,
    )


def compare_1x2_forecasts(
    model_forecasts: Iterable[Forecast1X2],
    benchmark_forecasts: Iterable[Forecast1X2],
    outcomes: Iterable[SettledOutcome1X2],
) -> BenchmarkComparison1X2:
    """Compare model and benchmark on exactly the same settled fixtures.

    Deltas are model minus benchmark; negative values indicate lower (better)
    scoring loss. Both reports are scored against the same outcome set.
    """
    settled = tuple(outcomes)
    model_report = score_1x2(model_forecasts, settled)
    benchmark_report = score_1x2(benchmark_forecasts, settled)
    if model_report.sample_size != benchmark_report.sample_size:
        raise ValueError("model and benchmark sample sizes must match")
    brier_delta = model_report.multiclass_brier - benchmark_report.multiclass_brier
    log_loss_delta = model_report.log_loss - benchmark_report.log_loss
    rps_delta = model_report.ranked_probability_score - benchmark_report.ranked_probability_score
    return BenchmarkComparison1X2(
        sample_size=model_report.sample_size,
        model_report=model_report,
        benchmark_report=benchmark_report,
        brier_delta=brier_delta,
        log_loss_delta=log_loss_delta,
        ranked_probability_score_delta=rps_delta,
        model_beats_brier=brier_delta < 0.0,
        model_beats_log_loss=log_loss_delta < 0.0,
    )
