"""Date-clustered uncertainty and probability calibration diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import math
import random
from collections import defaultdict

from .walk_forward import WalkForwardReport, FixtureEvaluation


@dataclass(frozen=True)
class BootstrapInterval:
    lower_95: float
    upper_95: float
    replicates: int
    distinct_dates: int


@dataclass(frozen=True)
class CalibrationBin:
    lower_bound: float
    upper_bound: float
    count: int
    mean_predicted: float
    observed_rate: float


@dataclass(frozen=True)
class CalibrationCurve:
    outcome_class: str
    model_bins: tuple[CalibrationBin, ...]
    baseline_bins: tuple[CalibrationBin, ...]


@dataclass(frozen=True)
class MarketReliability:
    market: str
    sample_count: int
    distinct_dates: int
    brier_improvement_ci: BootstrapInterval | None
    log_loss_improvement_ci: BootstrapInterval | None
    calibration: tuple[CalibrationCurve, ...]


@dataclass(frozen=True)
class ReliabilityAssessment:
    evaluation_as_of: object
    bootstrap_seed: int
    bootstrap_replicates: int
    one_x_two: MarketReliability | None
    btts: MarketReliability | None
    over_2_5: MarketReliability | None


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("BOOTSTRAP_SAMPLE_EMPTY")
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _calibration_bins(probabilities: list[float], outcomes: list[int], bin_count: int) -> tuple[CalibrationBin, ...]:
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bin_count)]
    for probability, outcome in zip(probabilities, outcomes):
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("CALIBRATION_PROBABILITY_INVALID")
        index = min(int(probability * bin_count), bin_count - 1)
        buckets[index].append((probability, outcome))
    result = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        result.append(CalibrationBin(
            lower_bound=index / bin_count,
            upper_bound=(index + 1) / bin_count,
            count=len(bucket),
            mean_predicted=sum(p for p, _ in bucket) / len(bucket),
            observed_rate=sum(y for _, y in bucket) / len(bucket),
        ))
    return tuple(result)


def _date_groups(fixtures: tuple[FixtureEvaluation, ...], differences: list[tuple[float, float]]) -> dict[str, list[tuple[float, float]]]:
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for fixture, difference in zip(fixtures, differences):
        day = fixture.kickoff_at.astimezone(timezone.utc).date().isoformat()
        groups[day].append(difference)
    return dict(groups)


def _cluster_interval(groups: dict[str, list[tuple[float, float]]], *, index: int,
                      replicates: int, seed: int) -> BootstrapInterval | None:
    dates = sorted(groups)
    if len(dates) < 2:
        return None
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(replicates):
        sampled_dates = [rng.choice(dates) for _ in dates]
        sample = [row[index] for day in sampled_dates for row in groups[day]]
        if sample:
            values.append(sum(sample) / len(sample))
    if len(values) != replicates:
        raise ValueError("BOOTSTRAP_REPLICATE_COUNT_MISMATCH")
    return BootstrapInterval(
        lower_95=_quantile(values, 0.025), upper_95=_quantile(values, 0.975),
        replicates=replicates, distinct_dates=len(dates),
    )


def _binary_reliability(fixtures: tuple[FixtureEvaluation, ...], *, market: str,
                        model_attr: str, baseline_attr: str, outcome_fn,
                        replicates: int, seed: int, bin_count: int) -> MarketReliability | None:
    if not fixtures:
        return None
    outcomes = [outcome_fn(x) for x in fixtures]
    model_probs = [getattr(x, model_attr) for x in fixtures]
    base_probs = [getattr(x, baseline_attr) for x in fixtures]
    differences = []
    for mp, bp, outcome in zip(model_probs, base_probs, outcomes):
        model_brier = (mp - outcome) ** 2
        base_brier = (bp - outcome) ** 2
        model_loss = -math.log(max(min(mp if outcome else 1 - mp, 1 - 1e-15), 1e-15))
        base_loss = -math.log(max(min(bp if outcome else 1 - bp, 1 - 1e-15), 1e-15))
        differences.append((base_brier - model_brier, base_loss - model_loss))
    groups = _date_groups(fixtures, differences)
    return MarketReliability(
        market=market, sample_count=len(fixtures), distinct_dates=len(groups),
        brier_improvement_ci=_cluster_interval(groups, index=0, replicates=replicates, seed=seed),
        log_loss_improvement_ci=_cluster_interval(groups, index=1, replicates=replicates, seed=seed + 1),
        calibration=(CalibrationCurve(
            outcome_class=market,
            model_bins=_calibration_bins(model_probs, outcomes, bin_count),
            baseline_bins=_calibration_bins(base_probs, outcomes, bin_count),
        ),),
    )


def _one_x_two_reliability(fixtures: tuple[FixtureEvaluation, ...], *,
                           replicates: int, seed: int, bin_count: int) -> MarketReliability | None:
    if not fixtures:
        return None
    class_names = ("HOME", "DRAW", "AWAY")
    model_probs = [(x.model_home_win, x.model_draw, x.model_away_win) for x in fixtures]
    base_probs = [(x.baseline_home_win, x.baseline_draw, x.baseline_away_win) for x in fixtures]
    outcomes = [class_names.index(x.actual_1x2) for x in fixtures]
    differences = []
    for mp, bp, outcome in zip(model_probs, base_probs, outcomes):
        model_brier = sum((p - (i == outcome)) ** 2 for i, p in enumerate(mp))
        base_brier = sum((p - (i == outcome)) ** 2 for i, p in enumerate(bp))
        model_loss = -math.log(max(mp[outcome], 1e-15))
        base_loss = -math.log(max(bp[outcome], 1e-15))
        differences.append((base_brier - model_brier, base_loss - model_loss))
    groups = _date_groups(fixtures, differences)
    curves = []
    for i, name in enumerate(class_names):
        binary_outcomes = [int(value == i) for value in outcomes]
        curves.append(CalibrationCurve(
            outcome_class=name,
            model_bins=_calibration_bins([p[i] for p in model_probs], binary_outcomes, bin_count),
            baseline_bins=_calibration_bins([p[i] for p in base_probs], binary_outcomes, bin_count),
        ))
    return MarketReliability(
        market="1X2", sample_count=len(fixtures), distinct_dates=len(groups),
        brier_improvement_ci=_cluster_interval(groups, index=0, replicates=replicates, seed=seed),
        log_loss_improvement_ci=_cluster_interval(groups, index=1, replicates=replicates, seed=seed + 1),
        calibration=tuple(curves),
    )


def assess_reliability(report: WalkForwardReport, *, bootstrap_replicates: int = 2000,
                       bootstrap_seed: int = 20261114, calibration_bins: int = 10) -> ReliabilityAssessment:
    """Attach calibration curves and date-clustered paired loss CIs to a walk-forward report.

    The bootstrap resamples whole UTC kickoff dates, preserving within-day
    fixture clustering. Improvement is baseline loss minus model loss; a
    strictly positive 95% lower bound is evidence of better scoring on this
    evaluation sample, not standalone release certification.
    """
    if not isinstance(bootstrap_replicates, int) or isinstance(bootstrap_replicates, bool) or bootstrap_replicates < 100:
        raise ValueError("BOOTSTRAP_REPLICATES_MUST_BE_AT_LEAST_100")
    if not isinstance(calibration_bins, int) or isinstance(calibration_bins, bool) or not 2 <= calibration_bins <= 100:
        raise ValueError("CALIBRATION_BIN_COUNT_INVALID")
    if not isinstance(bootstrap_seed, int) or isinstance(bootstrap_seed, bool):
        raise ValueError("BOOTSTRAP_SEED_INVALID")
    fixtures = report.fixtures
    return ReliabilityAssessment(
        evaluation_as_of=report.evaluation_as_of,
        bootstrap_seed=bootstrap_seed, bootstrap_replicates=bootstrap_replicates,
        one_x_two=_one_x_two_reliability(fixtures, replicates=bootstrap_replicates,
                                         seed=bootstrap_seed, bin_count=calibration_bins),
        btts=_binary_reliability(
            fixtures, market="BTTS", model_attr="model_btts_yes",
            baseline_attr="baseline_btts_yes",
            outcome_fn=lambda x: int(x.actual_home_goals > 0 and x.actual_away_goals > 0),
            replicates=bootstrap_replicates, seed=bootstrap_seed + 2, bin_count=calibration_bins,
        ),
        over_2_5=_binary_reliability(
            fixtures, market="OVER_2_5", model_attr="model_over_2_5",
            baseline_attr="baseline_over_2_5",
            outcome_fn=lambda x: int(x.actual_home_goals + x.actual_away_goals >= 3),
            replicates=bootstrap_replicates, seed=bootstrap_seed + 4, bin_count=calibration_bins,
        ),
    )
