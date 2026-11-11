"""Held-out 1X2 calibration diagnostics; deliberately does not fit calibrators.

Supply each chronological walk-forward fold's out-of-sample forecasts and
settled outcomes. The module reports one-vs-rest reliability for AWAY/DRAW/HOME
and never changes a probability or learns a mapping from evaluation labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from veltrix_v2.evaluation.metrics import Forecast1X2, SettledOutcome1X2

_CLASSES = ("AWAY", "DRAW", "HOME")


@dataclass(frozen=True, slots=True)
class HeldOutFold1X2:
    fold_number: int
    test_fixture_count: int
    forecasts: tuple[Forecast1X2, ...]
    outcomes: tuple[SettledOutcome1X2, ...]

    def __post_init__(self) -> None:
        if isinstance(self.fold_number, bool) or not isinstance(self.fold_number, int) or self.fold_number < 1:
            raise ValueError("fold_number must be a positive integer")
        if isinstance(self.test_fixture_count, bool) or not isinstance(self.test_fixture_count, int) or self.test_fixture_count < 0:
            raise ValueError("test_fixture_count must be a non-negative integer")
        forecasts = tuple(self.forecasts)
        outcomes = tuple(self.outcomes)
        if any(not isinstance(row, Forecast1X2) for row in forecasts):
            raise ValueError("held-out forecasts must be Forecast1X2 instances")
        if any(not isinstance(row, SettledOutcome1X2) for row in outcomes):
            raise ValueError("held-out outcomes must be SettledOutcome1X2 instances")
        object.__setattr__(self, "forecasts", forecasts)
        object.__setattr__(self, "outcomes", outcomes)
        if len(forecasts) > self.test_fixture_count:
            raise ValueError("forecast_count cannot exceed test_fixture_count")
        forecast_ids = [row.fixture_id for row in forecasts]
        outcome_ids = [row.fixture_id for row in outcomes]
        if len(forecast_ids) != len(set(forecast_ids)) or len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("duplicate fixture IDs within held-out fold")
        if set(forecast_ids) != set(outcome_ids):
            raise ValueError("held-out forecast and outcome fixture IDs must match")


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_predicted_probability: float
    observed_frequency: float
    absolute_calibration_gap: float


@dataclass(frozen=True, slots=True)
class ClassCalibration:
    outcome_class: str
    sample_size: int
    brier_score: float | None
    expected_calibration_error: float | None
    maximum_calibration_error: float | None
    bins: tuple[ReliabilityBin, ...]


@dataclass(frozen=True, slots=True)
class FoldCalibration:
    fold_number: int
    test_fixture_count: int
    forecast_count: int
    abstentions: int
    coverage: float | None
    classes: tuple[ClassCalibration, ...]


@dataclass(frozen=True, slots=True)
class CalibrationReport1X2:
    fold_count: int
    test_fixture_count: int
    forecast_count: int
    abstentions: int
    coverage: float | None
    classes: tuple[ClassCalibration, ...]
    folds: tuple[FoldCalibration, ...]


def _class_calibration(
    forecasts: tuple[Forecast1X2, ...],
    outcomes: tuple[SettledOutcome1X2, ...],
    outcome_class: str,
    bin_count: int,
) -> ClassCalibration:
    outcome_by_id = {row.fixture_id: row.outcome for row in outcomes}
    probability_field = {
        "AWAY": "p_away",
        "DRAW": "p_draw",
        "HOME": "p_home",
    }[outcome_class]
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(bin_count)]
    squared_error = 0.0
    for forecast in forecasts:
        probability = float(getattr(forecast, probability_field))
        observed = int(outcome_by_id[forecast.fixture_id] == outcome_class)
        squared_error += (probability - observed) ** 2
        index = min(int(probability * bin_count), bin_count - 1)
        grouped[index].append((probability, observed))

    bins: list[ReliabilityBin] = []
    count = len(forecasts)
    weighted_gap = 0.0
    max_gap = 0.0
    for index, members in enumerate(grouped):
        if not members:
            continue
        n = len(members)
        mean_probability = sum(item[0] for item in members) / n
        observed_frequency = sum(item[1] for item in members) / n
        gap = abs(mean_probability - observed_frequency)
        weighted_gap += (n / count) * gap
        max_gap = max(max_gap, gap)
        bins.append(ReliabilityBin(
            lower_bound=index / bin_count,
            upper_bound=(index + 1) / bin_count,
            sample_count=n,
            mean_predicted_probability=mean_probability,
            observed_frequency=observed_frequency,
            absolute_calibration_gap=gap,
        ))
    return ClassCalibration(
        outcome_class=outcome_class,
        sample_size=count,
        brier_score=squared_error / count if count else None,
        expected_calibration_error=weighted_gap if count else None,
        maximum_calibration_error=max_gap if count else None,
        bins=tuple(bins),
    )


def _fold_report(fold: HeldOutFold1X2, bin_count: int) -> FoldCalibration:
    classes = tuple(
        _class_calibration(fold.forecasts, fold.outcomes, label, bin_count)
        for label in _CLASSES
    )
    return FoldCalibration(
        fold_number=fold.fold_number,
        test_fixture_count=fold.test_fixture_count,
        forecast_count=len(fold.forecasts),
        abstentions=fold.test_fixture_count - len(fold.forecasts),
        coverage=(len(fold.forecasts) / fold.test_fixture_count)
        if fold.test_fixture_count else None,
        classes=classes,
    )


def diagnose_1x2_calibration(
    folds: Iterable[HeldOutFold1X2],
    *,
    bin_count: int = 10,
) -> CalibrationReport1X2:
    """Report reliability using only supplied held-out fold forecasts/results."""
    if isinstance(bin_count, bool) or not isinstance(bin_count, int) or not 2 <= bin_count <= 100:
        raise ValueError("bin_count must be an integer from 2 through 100")
    rows = tuple(folds)
    if not rows:
        raise ValueError("at least one held-out fold is required")
    if any(not isinstance(row, HeldOutFold1X2) for row in rows):
        raise ValueError("all inputs must be HeldOutFold1X2 instances")
    fold_numbers = [row.fold_number for row in rows]
    if len(fold_numbers) != len(set(fold_numbers)):
        raise ValueError("duplicate fold numbers")
    fixture_ids = [
        forecast.fixture_id for fold in rows for forecast in fold.forecasts
    ]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("fixture appears in more than one held-out fold")
    all_forecasts = tuple(f for fold in rows for f in fold.forecasts)
    all_outcomes = tuple(o for fold in rows for o in fold.outcomes)
    if not all_forecasts:
        raise ValueError("no held-out forecasts available for calibration diagnostics")
    if {f.fixture_id for f in all_forecasts} != {o.fixture_id for o in all_outcomes}:
        raise ValueError("aggregate held-out forecast and outcome identities must match")

    test_count = sum(fold.test_fixture_count for fold in rows)
    forecast_count = len(all_forecasts)
    classes = tuple(
        _class_calibration(all_forecasts, all_outcomes, label, bin_count)
        for label in _CLASSES
    )
    fold_reports = tuple(_fold_report(fold, bin_count) for fold in rows)
    return CalibrationReport1X2(
        fold_count=len(rows),
        test_fixture_count=test_count,
        forecast_count=forecast_count,
        abstentions=test_count - forecast_count,
        coverage=forecast_count / test_count if test_count else None,
        classes=classes,
        folds=fold_reports,
    )
