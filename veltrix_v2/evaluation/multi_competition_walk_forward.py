"""Aggregate chronological multi-market evaluation across competitions.

Each competition-season is fitted independently to preserve its own goal
rates, teams and home advantage. The aggregate score is computed only after
each scope has generated out-of-sample forecasts for its own chronological
folds. Fixture IDs must remain globally unique.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Iterable

from veltrix_v2.evaluation.binary_metrics import (
    BinaryForecast, BinaryScoreReport, SettledBinaryOutcome, score_binary_market,
)
from veltrix_v2.evaluation.metrics import (
    Forecast1X2, ScoreReport1X2, SettledOutcome1X2, score_1x2,
)
from veltrix_v2.evaluation.multi_market_walk_forward import (
    MarketCoverage, MultiMarketWalkForwardEvaluation, run_multi_market_walk_forward,
)
from veltrix_v2.models.poisson_strength import TrainingMatch


@dataclass(frozen=True, slots=True)
class MultiCompetitionWalkForwardEvaluation:
    scopes: tuple[tuple[str, str], ...]
    scope_reports: tuple[MultiMarketWalkForwardEvaluation, ...]
    total_test_fixtures: int
    total_forecasts: int
    total_abstentions: int
    total_folds: int
    converged_folds: int
    model_convergence_rate: float | None
    aggregate_1x2: ScoreReport1X2 | None
    aggregate_btts: BinaryScoreReport | None
    aggregate_totals: BinaryScoreReport | None
    coverage_1x2: MarketCoverage
    coverage_btts: MarketCoverage
    coverage_totals: MarketCoverage
    total_line: float
    model_version: str


def run_multi_competition_walk_forward(
    matches: Iterable[TrainingMatch],
    *,
    competition_seasons: Iterable[tuple[str, str]],
    first_test_start_utc: datetime,
    test_window: timedelta,
    n_splits: int,
    embargo: timedelta = timedelta(0),
    minimum_training_matches: int = 40,
    minimum_team_matches: int = 1,
    max_iterations: int = 6000,
    recency_half_life_days: float = 180.0,
    ridge: float = 0.05,
    rho: float = 0.0,
    total_line: float = 2.5,
    model_version: str = "veltrix-v2-multicomp-wf-0.1",
) -> MultiCompetitionWalkForwardEvaluation:
    rows = tuple(matches)
    scopes = tuple(competition_seasons)
    if not rows:
        raise ValueError("MULTI_COMPETITION_MATCH_DATA_REQUIRED")
    if not scopes or len(scopes) != len(set(scopes)):
        raise ValueError("MULTI_COMPETITION_SCOPES_REQUIRED_AND_UNIQUE")
    if any(
        not isinstance(scope, tuple) or len(scope) != 2
        or not all(isinstance(value, str) and value.strip() for value in scope)
        for scope in scopes
    ):
        raise ValueError("MULTI_COMPETITION_SCOPE_INVALID")

    reports: list[MultiMarketWalkForwardEvaluation] = []
    for competition_key, season in scopes:
        if not any(row.competition_key == competition_key and row.season == season for row in rows):
            raise ValueError(f"MULTI_COMPETITION_SCOPE_DATA_MISSING:{competition_key}:{season}")
        reports.append(run_multi_market_walk_forward(
            rows,
            competition_key=competition_key,
            season=season,
            first_test_start_utc=first_test_start_utc,
            test_window=test_window,
            n_splits=n_splits,
            embargo=embargo,
            minimum_training_matches=minimum_training_matches,
            minimum_team_matches=minimum_team_matches,
            max_iterations=max_iterations,
            recency_half_life_days=recency_half_life_days,
            ridge=ridge,
            rho=rho,
            total_line=total_line,
            model_version=f"{model_version}-{competition_key}-{season}",
        ))

    forecasts_1x2 = tuple(f for report in reports for fold in report.folds for f in fold.forecasts_1x2)
    outcomes_1x2 = tuple(o for report in reports for fold in report.folds for o in fold.outcomes_1x2)
    forecasts_btts = tuple(f for report in reports for fold in report.folds for f in fold.btts_forecasts)
    outcomes_btts = tuple(o for report in reports for fold in report.folds for o in fold.btts_outcomes)
    forecasts_totals = tuple(f for report in reports for fold in report.folds for f in fold.totals_forecasts)
    outcomes_totals = tuple(o for report in reports for fold in report.folds for o in fold.totals_outcomes)
    eligible_ids = tuple(
        fixture_id
        for report in reports
        for fold in report.folds
        for fixture_id in fold.eligible_fixture_ids
    )
    if len(eligible_ids) != len(set(eligible_ids)):
        raise ValueError("MULTI_COMPETITION_DUPLICATE_ELIGIBLE_FIXTURE_IDS")

    test_count = sum(report.total_test_fixtures for report in reports)
    forecast_count = len(forecasts_1x2)
    abstentions = test_count - forecast_count
    aggregate_1x2 = score_1x2(forecasts_1x2, outcomes_1x2) if forecasts_1x2 else None
    aggregate_btts = (
        score_binary_market(forecasts_btts, outcomes_btts, eligible_fixture_ids=eligible_ids)
        if forecasts_btts else None
    )
    aggregate_totals = (
        score_binary_market(forecasts_totals, outcomes_totals, eligible_fixture_ids=eligible_ids)
        if forecasts_totals else None
    )
    total_folds = sum(len(report.folds) for report in reports)
    converged_folds = sum(
        1 for report in reports for fold in report.folds if fold.model_converged
    )
    convergence_rate = converged_folds / total_folds if total_folds else None
    coverage = MarketCoverage(
        eligible_fixture_count=test_count,
        forecast_count=forecast_count,
        abstention_count=abstentions,
        coverage=(forecast_count / test_count) if test_count else None,
    )
    return MultiCompetitionWalkForwardEvaluation(
        scopes=scopes,
        scope_reports=tuple(reports),
        total_test_fixtures=test_count,
        total_forecasts=forecast_count,
        total_abstentions=abstentions,
        total_folds=total_folds,
        converged_folds=converged_folds,
        model_convergence_rate=convergence_rate,
        aggregate_1x2=aggregate_1x2,
        aggregate_btts=aggregate_btts,
        aggregate_totals=aggregate_totals,
        coverage_1x2=coverage,
        coverage_btts=coverage,
        coverage_totals=coverage,
        total_line=float(total_line),
        model_version=model_version,
    )
