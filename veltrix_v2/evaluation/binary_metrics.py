"""Strict binary-market evaluation for BTTS and non-push O/U markets.

Only out-of-sample forecasts are accepted. Fixture identities must match exactly.
Coverage is measured against the full eligible fixture universe, including abstentions.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log, sqrt
from numbers import Real
from typing import Iterable, Literal

BinaryOutcome = Literal["YES", "NO"]


@dataclass(frozen=True, slots=True)
class BinaryForecast:
    fixture_id: str
    probability_yes: float

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.fixture_id.strip():
            raise ValueError("BINARY_FORECAST_FIXTURE_ID_REQUIRED")
        if isinstance(self.probability_yes, bool) or not isinstance(self.probability_yes, Real):
            raise ValueError("BINARY_FORECAST_PROBABILITY_INVALID")
        if not isfinite(float(self.probability_yes)) or not 0.0 < self.probability_yes < 1.0:
            raise ValueError("BINARY_FORECAST_PROBABILITY_OUT_OF_RANGE")


@dataclass(frozen=True, slots=True)
class SettledBinaryOutcome:
    fixture_id: str
    outcome: BinaryOutcome

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.fixture_id.strip():
            raise ValueError("BINARY_OUTCOME_FIXTURE_ID_REQUIRED")
        if self.outcome not in ("YES", "NO"):
            raise ValueError("BINARY_OUTCOME_MUST_BE_YES_OR_NO")


@dataclass(frozen=True, slots=True)
class BinaryScoreReport:
    sample_size: int
    eligible_fixture_count: int
    forecast_count: int
    abstention_count: int
    coverage: float
    hit_rate: float
    hit_rate_ci95_lower: float
    hit_rate_ci95_upper: float
    brier_score: float
    log_loss: float


def _wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("BINARY_METRIC_NONEMPTY_SAMPLE_REQUIRED")
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    margin = z * sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def score_binary_market(
    forecasts: Iterable[BinaryForecast],
    outcomes: Iterable[SettledBinaryOutcome],
    *,
    eligible_fixture_ids: Iterable[str],
) -> BinaryScoreReport:
    forecast_rows = tuple(forecasts)
    outcome_rows = tuple(outcomes)
    eligible_ids = tuple(eligible_fixture_ids)
    forecast_ids = [row.fixture_id for row in forecast_rows]
    outcome_ids = [row.fixture_id for row in outcome_rows]
    if len(eligible_ids) != len(set(eligible_ids)) or not eligible_ids:
        raise ValueError("BINARY_METRIC_ELIGIBLE_FIXTURE_IDS_INVALID")
    if len(forecast_ids) != len(set(forecast_ids)) or len(outcome_ids) != len(set(outcome_ids)):
        raise ValueError("BINARY_METRIC_DUPLICATE_FIXTURE_IDS")
    eligible = set(eligible_ids)
    if not set(forecast_ids) <= eligible or not set(outcome_ids) <= eligible:
        raise ValueError("BINARY_METRIC_FIXTURE_OUTSIDE_ELIGIBLE_UNIVERSE")
    if set(forecast_ids) != set(outcome_ids):
        raise ValueError("BINARY_METRIC_FORECAST_OUTCOME_IDS_MUST_MATCH")
    if not forecast_rows:
        raise ValueError("BINARY_METRIC_NO_FORECASTS")

    outcome_by_id = {row.fixture_id: row.outcome for row in outcome_rows}
    hits = 0
    brier = logloss = 0.0
    for row in forecast_rows:
        actual = outcome_by_id[row.fixture_id]
        target = 1.0 if actual == "YES" else 0.0
        predicted = float(row.probability_yes)
        brier += (predicted - target) ** 2
        logloss -= log(predicted if target else 1.0 - predicted)
        hits += int((predicted >= 0.5) == bool(target))
    count = len(forecast_rows)
    lower, upper = _wilson_interval(hits, count)
    eligible_count = len(eligible)
    return BinaryScoreReport(
        sample_size=count,
        eligible_fixture_count=eligible_count,
        forecast_count=count,
        abstention_count=eligible_count - count,
        coverage=count / eligible_count,
        hit_rate=hits / count,
        hit_rate_ci95_lower=lower,
        hit_rate_ci95_upper=upper,
        brier_score=brier / count,
        log_loss=logloss / count,
    )
