"""Held-out binary-market calibration diagnostics for BTTS and totals.

No calibration mapping is fitted. Only chronological out-of-sample forecasts
and their exactly matched settled outcomes are accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from veltrix_v2.evaluation.binary_metrics import BinaryForecast, SettledBinaryOutcome


@dataclass(frozen=True, slots=True)
class HeldOutBinaryFold:
    fold_number: int
    market: str
    test_fixture_count: int
    forecasts: tuple[BinaryForecast, ...]
    outcomes: tuple[SettledBinaryOutcome, ...]

    def __post_init__(self) -> None:
        if isinstance(self.fold_number, bool) or not isinstance(self.fold_number, int) or self.fold_number < 1:
            raise ValueError("fold_number must be positive")
        if self.market not in {"BTTS", "TOTALS", "OVER_UNDER"}:
            raise ValueError("unsupported binary calibration market")
        if isinstance(self.test_fixture_count, bool) or not isinstance(self.test_fixture_count, int) or self.test_fixture_count < 0:
            raise ValueError("test_fixture_count must be non-negative")
        forecasts, outcomes = tuple(self.forecasts), tuple(self.outcomes)
        if any(not isinstance(row, BinaryForecast) for row in forecasts):
            raise ValueError("forecasts must be BinaryForecast instances")
        if any(not isinstance(row, SettledBinaryOutcome) for row in outcomes):
            raise ValueError("outcomes must be SettledBinaryOutcome instances")
        object.__setattr__(self, "forecasts", forecasts)
        object.__setattr__(self, "outcomes", outcomes)
        if len(forecasts) > self.test_fixture_count:
            raise ValueError("forecast count exceeds test fixture count")
        forecast_ids = [row.fixture_id for row in forecasts]
        outcome_ids = [row.fixture_id for row in outcomes]
        if len(forecast_ids) != len(set(forecast_ids)) or len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("duplicate fixture IDs in held-out binary fold")
        if set(forecast_ids) != set(outcome_ids):
            raise ValueError("held-out binary forecast/outcome identities must match")


@dataclass(frozen=True, slots=True)
class BinaryReliabilityBin:
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_predicted_probability: float
    observed_frequency: float
    absolute_calibration_gap: float


@dataclass(frozen=True, slots=True)
class BinaryClassCalibration:
    outcome: str
    sample_size: int
    brier_score: float | None
    expected_calibration_error: float | None
    maximum_calibration_error: float | None
    bins: tuple[BinaryReliabilityBin, ...]


@dataclass(frozen=True, slots=True)
class BinaryFoldCalibration:
    fold_number: int
    test_fixture_count: int
    forecast_count: int
    abstentions: int
    coverage: float | None
    calibration: BinaryClassCalibration


@dataclass(frozen=True, slots=True)
class BinaryCalibrationReport:
    market: str
    fold_count: int
    test_fixture_count: int
    forecast_count: int
    abstentions: int
    coverage: float | None
    calibration: BinaryClassCalibration
    folds: tuple[BinaryFoldCalibration, ...]


def _calibrate(
    forecasts: tuple[BinaryForecast, ...],
    outcomes: tuple[SettledBinaryOutcome, ...],
    *,
    outcome: str,
    bin_count: int,
) -> BinaryClassCalibration:
    actual_by_id = {row.fixture_id: row.outcome for row in outcomes}
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bin_count)]
    squared_error = 0.0
    for row in forecasts:
        probability = float(row.probability_yes)
        observed = int(actual_by_id[row.fixture_id] == outcome)
        squared_error += (probability - observed) ** 2
        buckets[min(int(probability * bin_count), bin_count - 1)].append((probability, observed))
    bins: list[BinaryReliabilityBin] = []
    ece = max_gap = 0.0
    count = len(forecasts)
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        n = len(bucket)
        mean_p = sum(p for p, _ in bucket) / n
        observed_rate = sum(y for _, y in bucket) / n
        gap = abs(mean_p - observed_rate)
        ece += n / count * gap
        max_gap = max(max_gap, gap)
        bins.append(BinaryReliabilityBin(
            lower_bound=index / bin_count,
            upper_bound=(index + 1) / bin_count,
            sample_count=n,
            mean_predicted_probability=mean_p,
            observed_frequency=observed_rate,
            absolute_calibration_gap=gap,
        ))
    return BinaryClassCalibration(
        outcome=outcome,
        sample_size=count,
        brier_score=squared_error / count if count else None,
        expected_calibration_error=ece if count else None,
        maximum_calibration_error=max_gap if count else None,
        bins=tuple(bins),
    )


def diagnose_binary_calibration(
    folds: Iterable[HeldOutBinaryFold],
    *,
    bin_count: int = 10,
) -> BinaryCalibrationReport:
    if isinstance(bin_count, bool) or not isinstance(bin_count, int) or not 2 <= bin_count <= 100:
        raise ValueError("bin_count must be from 2 through 100")
    rows = tuple(folds)
    if not rows or any(not isinstance(row, HeldOutBinaryFold) for row in rows):
        raise ValueError("at least one valid held-out binary fold is required")
    market = rows[0].market
    if any(row.market != market for row in rows):
        raise ValueError("cannot mix markets in one calibration report")
    fold_numbers = [row.fold_number for row in rows]
    if len(fold_numbers) != len(set(fold_numbers)):
        raise ValueError("duplicate fold numbers")
    fixture_ids = [f.fixture_id for fold in rows for f in fold.forecasts]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("fixture appears in more than one held-out fold")
    forecasts = tuple(f for fold in rows for f in fold.forecasts)
    outcomes = tuple(o for fold in rows for o in fold.outcomes)
    if not forecasts:
        raise ValueError("no held-out forecasts available")
    outcome_label = "YES"
    aggregate = _calibrate(forecasts, outcomes, outcome=outcome_label, bin_count=bin_count)
    fold_reports = tuple(
        BinaryFoldCalibration(
            fold_number=fold.fold_number,
            test_fixture_count=fold.test_fixture_count,
            forecast_count=len(fold.forecasts),
            abstentions=fold.test_fixture_count - len(fold.forecasts),
            coverage=(len(fold.forecasts) / fold.test_fixture_count) if fold.test_fixture_count else None,
            calibration=_calibrate(fold.forecasts, fold.outcomes, outcome=outcome_label, bin_count=bin_count),
        )
        for fold in rows
    )
    test_count = sum(fold.test_fixture_count for fold in rows)
    forecast_count = len(forecasts)
    return BinaryCalibrationReport(
        market=market,
        fold_count=len(rows),
        test_fixture_count=test_count,
        forecast_count=forecast_count,
        abstentions=test_count - forecast_count,
        coverage=forecast_count / test_count if test_count else None,
        calibration=aggregate,
        folds=fold_reports,
    )
