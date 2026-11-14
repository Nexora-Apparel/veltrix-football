"""Deterministic batch forecast engine for the new VELTRIX model."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Iterable

from .poisson import InsufficientHistoryError, MatchObservation, PoissonPrediction, predict_match


@dataclass(frozen=True)
class PredictionTarget:
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime
    provider: str
    source_id: str
    source_fixture_id: str
    retrieved_at: datetime
    payload_sha256: str
    rights_approval_id: str
    home_team_name: str = ""
    away_team_name: str = ""


@dataclass(frozen=True)
class ForecastRecord:
    fixture_id: str
    competition_id: str
    kickoff_at: datetime
    cutoff_at: datetime
    provider: str
    source_id: str
    home_team_name: str
    away_team_name: str
    model: PoissonPrediction


@dataclass(frozen=True)
class BatchForecastReport:
    cutoff_at: datetime
    requested_target_count: int
    forecast_count: int
    skipped_duplicate_target_ids: int
    skipped_invalid_targets: int
    skipped_targets_not_yet_known: int
    skipped_no_history: int
    skipped_capacity: int
    forecasts: tuple[ForecastRecord, ...]


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _valid_target(target: PredictionTarget) -> bool:
    if not isinstance(target, PredictionTarget):
        return False
    if not all(isinstance(value, str) and value.strip() for value in (
        target.fixture_id, target.competition_id, target.home_team_id,
        target.away_team_id, target.provider, target.source_id,
        target.source_fixture_id, target.payload_sha256, target.rights_approval_id,
    )):
        return False
    if target.home_team_id == target.away_team_id:
        return False
    if len(target.payload_sha256) != 64 or any(
        ch not in "0123456789abcdef" for ch in target.payload_sha256.casefold()
    ):
        return False
    return _aware(target.kickoff_at) and _aware(target.retrieved_at)


def predict_batch(
    observations: Iterable[MatchObservation],
    targets: Iterable[PredictionTarget],
    *,
    cutoff_at: datetime,
    max_fixtures: int = 25,
    recency_half_life_days: float | None = None,
    dixon_coles_rho: float = 0.0,
) -> BatchForecastReport:
    """Generate up to 25 forecasts in kickoff order, without favourites filtering.

    This function calculates forecasts only. It never publishes them, activates
    a schedule, writes to a database, or unlocks value betting.
    """
    if not _aware(cutoff_at):
        raise ValueError("BATCH_CUTOFF_MUST_BE_TIMEZONE_AWARE")
    if not isinstance(max_fixtures, int) or isinstance(max_fixtures, bool) or not 1 <= max_fixtures <= 25:
        raise ValueError("MAX_FIXTURES_MUST_BE_1_TO_25")
    if recency_half_life_days is not None and (
        not isinstance(recency_half_life_days, (int, float))
        or isinstance(recency_half_life_days, bool)
        or not math.isfinite(recency_half_life_days)
        or recency_half_life_days <= 0
    ):
        raise ValueError("RECENCY_HALF_LIFE_MUST_BE_POSITIVE_FINITE")
    if (not isinstance(dixon_coles_rho, (int, float)) or isinstance(dixon_coles_rho, bool)
            or not math.isfinite(dixon_coles_rho) or not -1.0 <= dixon_coles_rho <= 1.0):
        raise ValueError("DIXON_COLES_RHO_INVALID")

    history = list(observations)
    target_rows = list(targets)
    counts: dict[str, int] = {}
    for target in target_rows:
        if isinstance(target, PredictionTarget) and isinstance(target.fixture_id, str):
            counts[target.fixture_id] = counts.get(target.fixture_id, 0) + 1
    duplicate_ids = {key for key, count in counts.items() if count > 1}
    skipped_duplicates = sum(counts[key] for key in duplicate_ids)
    invalid_target_types = sum(1 for target in target_rows if not isinstance(target, PredictionTarget))

    candidates = [target for target in target_rows
                  if isinstance(target, PredictionTarget)
                  and target.fixture_id not in duplicate_ids]
    invalid_targets = [target for target in candidates if not _valid_target(target)]
    candidates = [target for target in candidates if _valid_target(target)]
    not_known = [target for target in candidates if target.retrieved_at > cutoff_at]
    candidates = [target for target in candidates if target.retrieved_at <= cutoff_at]
    past_or_live = [target for target in candidates if target.kickoff_at <= cutoff_at]
    candidates = [target for target in candidates if target.kickoff_at > cutoff_at]

    candidates.sort(key=lambda target: (target.kickoff_at, target.fixture_id))
    skipped_capacity = max(0, len(candidates) - max_fixtures)
    selected = candidates[:max_fixtures]

    forecasts: list[ForecastRecord] = []
    skipped_no_history = 0
    skipped_invalid = invalid_target_types + len(invalid_targets) + len(past_or_live)
    for target in selected:
        try:
            prediction = predict_match(
                history,
                competition_id=target.competition_id,
                home_team_id=target.home_team_id,
                away_team_id=target.away_team_id,
                kickoff_at=target.kickoff_at,
                cutoff_at=cutoff_at,
                recency_half_life_days=recency_half_life_days,
                dixon_coles_rho=dixon_coles_rho,
            )
        except InsufficientHistoryError:
            skipped_no_history += 1
            continue
        except (TypeError, ValueError):
            skipped_invalid += 1
            continue
        forecasts.append(ForecastRecord(
            fixture_id=target.fixture_id,
            competition_id=target.competition_id,
            kickoff_at=target.kickoff_at,
            cutoff_at=cutoff_at,
            provider=target.provider,
            source_id=target.source_id,
            home_team_name=target.home_team_name,
            away_team_name=target.away_team_name,
            model=prediction,
        ))

    return BatchForecastReport(
        cutoff_at=cutoff_at,
        requested_target_count=len(target_rows),
        forecast_count=len(forecasts),
        skipped_duplicate_target_ids=skipped_duplicates,
        skipped_invalid_targets=skipped_invalid,
        skipped_targets_not_yet_known=len(not_known),
        skipped_no_history=skipped_no_history,
        skipped_capacity=skipped_capacity,
        forecasts=tuple(forecasts),
    )
