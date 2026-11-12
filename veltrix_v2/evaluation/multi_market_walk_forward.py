"""Chronological multi-market evaluation from one shared scoreline forecast.

For every eligible test fixture, 1X2, BTTS and half-goal O/U probabilities are
derived from the same Dixon-Coles joint scoreline distribution. Abstentions
are counted against the full fold test universe for every market.
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
from veltrix_v2.evaluation.walk_forward import (
    EvaluationFixture, build_expanding_walk_forward_folds,
)
from veltrix_v2.models.dixon_coles import build_dixon_coles_forecast
from veltrix_v2.models.poisson_strength import (
    TrainingMatch, fit_poisson_strength_model,
)


@dataclass(frozen=True, slots=True)
class MarketCoverage:
    eligible_fixture_count: int
    forecast_count: int
    abstention_count: int
    coverage: float | None


@dataclass(frozen=True, slots=True)
class MultiMarketFoldEvaluation:
    fold_number: int
    model_converged: bool
    model_objective: float | None
    training_availability_bases: tuple[str, ...]
    train_fixture_count: int
    training_fixture_ids: tuple[str, ...]
    training_observation_ids: tuple[str, ...]
    training_label_cutoff_utc: datetime
    test_start_utc: datetime
    test_end_utc: datetime
    test_observation_ids: tuple[str, ...]
    test_fixture_count: int
    forecast_count: int
    abstained_fixture_ids: tuple[str, ...]
    eligible_fixture_ids: tuple[str, ...]
    forecasts_1x2: tuple[Forecast1X2, ...]
    outcomes_1x2: tuple[SettledOutcome1X2, ...]
    score_1x2: ScoreReport1X2 | None
    coverage_1x2: MarketCoverage
    btts_forecasts: tuple[BinaryForecast, ...]
    btts_outcomes: tuple[SettledBinaryOutcome, ...]
    btts_report: BinaryScoreReport | None
    coverage_btts: MarketCoverage
    totals_forecasts: tuple[BinaryForecast, ...]
    totals_outcomes: tuple[SettledBinaryOutcome, ...]
    totals_report: BinaryScoreReport | None
    coverage_totals: MarketCoverage


@dataclass(frozen=True, slots=True)
class MultiMarketWalkForwardEvaluation:
    competition_key: str
    season: str
    folds: tuple[MultiMarketFoldEvaluation, ...]
    total_test_fixtures: int
    total_forecasts: int
    total_abstentions: int
    aggregate_1x2: ScoreReport1X2 | None
    aggregate_btts: BinaryScoreReport | None
    aggregate_totals: BinaryScoreReport | None
    aggregate_coverage_1x2: MarketCoverage
    aggregate_coverage_btts: MarketCoverage
    aggregate_coverage_totals: MarketCoverage
    total_line: float
    model_version: str


def run_multi_market_walk_forward(
    matches: Iterable[TrainingMatch],
    *,
    competition_key: str,
    season: str,
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
    model_version: str = "veltrix-v2-multimarket-wf-0.1",
) -> MultiMarketWalkForwardEvaluation:
    rows = tuple(matches)
    if not rows:
        raise ValueError("MULTI_MARKET_MATCH_DATA_REQUIRED")
    if isinstance(rho, bool) or not isinstance(rho, (int, float)) or not math.isfinite(float(rho)):
        raise ValueError("MULTI_MARKET_RHO_MUST_BE_FINITE_NUMERIC")
    if isinstance(total_line, bool) or not isinstance(total_line, (int, float)) or not math.isfinite(float(total_line)):
        raise ValueError("MULTI_MARKET_TOTAL_LINE_MUST_BE_FINITE_NUMERIC")
    if total_line < 0 or abs((total_line % 1.0) - 0.5) > 1e-9:
        raise ValueError("MULTI_MARKET_TOTAL_LINE_MUST_BE_HALF_GOAL")
    if first_test_start_utc.tzinfo is None or first_test_start_utc.utcoffset() is None:
        raise ValueError("MULTI_MARKET_FIRST_TEST_START_MUST_BE_AWARE")

    scoped_rows = tuple(
        row for row in rows
        if row.competition_key == competition_key and row.season == season
    )
    if not scoped_rows:
        raise ValueError("MULTI_MARKET_SCOPE_HAS_NO_FIXTURES")
    # Quarantined rows are outside the evaluation universe. A row marked
    # valid must have explicit source-use approval and a point-in-time basis;
    # otherwise its score could contaminate the held-out benchmark.
    scoped = tuple(row for row in scoped_rows if row.quality_state == "valid")
    if not scoped:
        raise ValueError("MULTI_MARKET_SCOPE_HAS_NO_QUALITY_APPROVED_FIXTURES")
    if any(row.availability_basis == "unspecified" for row in scoped):
        raise ValueError("MULTI_MARKET_AVAILABILITY_BASIS_REQUIRED")
    if any(not row.source_training_approved for row in scoped):
        raise ValueError("MULTI_MARKET_SOURCE_NOT_APPROVED_FOR_EVALUATION")
    evaluation_fixtures = tuple(
        EvaluationFixture(row.fixture_id, row.kickoff_utc, row.available_at_utc)
        for row in scoped
    )
    folds = build_expanding_walk_forward_folds(
        evaluation_fixtures,
        first_test_start_utc=first_test_start_utc,
        test_window=test_window,
        n_splits=n_splits,
        embargo=embargo,
        min_train_fixtures=minimum_training_matches,
    )

    fold_reports: list[MultiMarketFoldEvaluation] = []
    all_1x2_forecasts: list[Forecast1X2] = []
    all_1x2_outcomes: list[SettledOutcome1X2] = []
    all_btts_forecasts: list[BinaryForecast] = []
    all_btts_outcomes: list[SettledBinaryOutcome] = []
    all_totals_forecasts: list[BinaryForecast] = []
    all_totals_outcomes: list[SettledBinaryOutcome] = []
    all_eligible_ids: list[str] = []
    total_test = total_abstentions = 0

    for fold in folds:
        train_ids = set(fold.train_fixture_ids)
        test_ids = set(fold.test_fixture_ids)
        training_rows = [
            row for row in scoped if row.fixture_id in train_ids
        ]
        test_rows = sorted(
            (row for row in scoped if row.fixture_id in test_ids),
            key=lambda row: (row.kickoff_utc, row.fixture_id),
        )
        model = fit_poisson_strength_model(
            training_rows,
            competition_key=competition_key,
            season=season,
            training_cutoff_utc=fold.training_label_cutoff_utc,
            minimum_matches=minimum_training_matches,
            minimum_team_matches=minimum_team_matches,
            max_iterations=max_iterations,
            recency_half_life_days=recency_half_life_days,
            ridge=ridge,
            model_version=f"{model_version}-fold-{fold.fold_number}",
        )

        eligible_ids = tuple(row.fixture_id for row in test_rows)
        forecasts_1x2: list[Forecast1X2] = []
        outcomes_1x2: list[SettledOutcome1X2] = []
        btts_forecasts: list[BinaryForecast] = []
        btts_outcomes: list[SettledBinaryOutcome] = []
        totals_forecasts: list[BinaryForecast] = []
        totals_outcomes: list[SettledBinaryOutcome] = []
        abstained: list[str] = []
        model_converged = bool(getattr(model, "converged", False))
        model_objective_raw = getattr(model, "objective", None)
        model_objective = (
            float(model_objective_raw)
            if isinstance(model_objective_raw, (int, float)) and math.isfinite(float(model_objective_raw))
            else None
        )
        availability_bases = tuple(getattr(model, "training_availability_bases", ("unspecified",)))
        if not model_converged:
            abstained.extend(eligible_ids)

        for row in (() if not model_converged else test_rows):
            try:
                expected_home, expected_away = model.expected_goals(
                    row.home_team_id, row.away_team_id
                )
                joint = build_dixon_coles_forecast(
                    fixture_id=row.fixture_id,
                    expected_home_goals=expected_home,
                    expected_away_goals=expected_away,
                    rho=float(rho),
                    model_version=f"{model_version}-fold-{fold.fold_number}",
                )
                markets = joint.distribution.derive_markets(total_line=float(total_line))
            except ValueError:
                abstained.append(row.fixture_id)
                continue

            # All three markets use this exact same joint scoreline distribution.
            forecasts_1x2.append(Forecast1X2(
                row.fixture_id,
                markets.p_home_win,
                markets.p_draw,
                markets.p_away_win,
            ))
            btts_forecasts.append(BinaryForecast(row.fixture_id, markets.p_btts_yes))
            totals_forecasts.append(BinaryForecast(row.fixture_id, markets.p_over))

            outcome_1x2 = (
                "HOME" if row.home_goals > row.away_goals
                else "AWAY" if row.home_goals < row.away_goals
                else "DRAW"
            )
            outcomes_1x2.append(SettledOutcome1X2(row.fixture_id, outcome_1x2))
            btts_outcomes.append(SettledBinaryOutcome(
                row.fixture_id,
                "YES" if row.home_goals > 0 and row.away_goals > 0 else "NO",
            ))
            totals_outcomes.append(SettledBinaryOutcome(
                row.fixture_id,
                "YES" if row.home_goals + row.away_goals > total_line else "NO",
            ))

        one_x_two_report = score_1x2(forecasts_1x2, outcomes_1x2) if forecasts_1x2 else None
        btts_report = score_binary_market(
            btts_forecasts, btts_outcomes, eligible_fixture_ids=eligible_ids
        ) if btts_forecasts else None
        totals_report = score_binary_market(
            totals_forecasts, totals_outcomes, eligible_fixture_ids=eligible_ids
        ) if totals_forecasts else None

        total_test += len(test_rows)
        total_abstentions += len(abstained)
        all_eligible_ids.extend(eligible_ids)
        all_1x2_forecasts.extend(forecasts_1x2)
        all_1x2_outcomes.extend(outcomes_1x2)
        all_btts_forecasts.extend(btts_forecasts)
        all_btts_outcomes.extend(btts_outcomes)
        all_totals_forecasts.extend(totals_forecasts)
        all_totals_outcomes.extend(totals_outcomes)
        coverage = MarketCoverage(
            eligible_fixture_count=len(eligible_ids),
            forecast_count=len(forecasts_1x2),
            abstention_count=len(abstained),
            coverage=(len(forecasts_1x2) / len(eligible_ids)) if eligible_ids else None,
        )
        fold_reports.append(MultiMarketFoldEvaluation(
            fold_number=fold.fold_number,
            model_converged=model_converged,
            model_objective=model_objective,
            training_availability_bases=availability_bases,
            train_fixture_count=len(training_rows),
            training_fixture_ids=tuple(getattr(model, "training_fixture_ids", tuple(sorted(train_ids)))),
            training_observation_ids=tuple(getattr(model, "training_observation_ids", tuple(sorted(row.source_observation_id for row in training_rows)))),
            training_label_cutoff_utc=fold.training_label_cutoff_utc,
            test_start_utc=fold.test_start_utc,
            test_end_utc=fold.test_end_utc,
            test_observation_ids=tuple(sorted(row.source_observation_id for row in test_rows)),
            test_fixture_count=len(test_rows),
            forecast_count=len(forecasts_1x2),
            abstained_fixture_ids=tuple(abstained),
            eligible_fixture_ids=eligible_ids,
            forecasts_1x2=tuple(forecasts_1x2),
            outcomes_1x2=tuple(outcomes_1x2),
            score_1x2=one_x_two_report,
            coverage_1x2=coverage,
            btts_forecasts=tuple(btts_forecasts),
            btts_outcomes=tuple(btts_outcomes),
            btts_report=btts_report,
            coverage_btts=coverage,
            totals_forecasts=tuple(totals_forecasts),
            totals_outcomes=tuple(totals_outcomes),
            totals_report=totals_report,
            coverage_totals=coverage,
        ))

    aggregate_1x2 = (
        score_1x2(all_1x2_forecasts, all_1x2_outcomes)
        if all_1x2_forecasts else None
    )
    aggregate_btts = (
        score_binary_market(
            all_btts_forecasts,
            all_btts_outcomes,
            eligible_fixture_ids=all_eligible_ids,
        )
        if all_btts_forecasts else None
    )
    aggregate_totals = (
        score_binary_market(
            all_totals_forecasts,
            all_totals_outcomes,
            eligible_fixture_ids=all_eligible_ids,
        )
        if all_totals_forecasts else None
    )
    total_forecasts = len(all_1x2_forecasts)
    aggregate_coverage = MarketCoverage(
        eligible_fixture_count=total_test,
        forecast_count=total_forecasts,
        abstention_count=total_abstentions,
        coverage=(total_forecasts / total_test) if total_test else None,
    )
    return MultiMarketWalkForwardEvaluation(
        competition_key=competition_key,
        season=season,
        folds=tuple(fold_reports),
        total_test_fixtures=total_test,
        total_forecasts=total_forecasts,
        total_abstentions=total_abstentions,
        aggregate_1x2=aggregate_1x2,
        aggregate_btts=aggregate_btts,
        aggregate_totals=aggregate_totals,
        aggregate_coverage_1x2=aggregate_coverage,
        aggregate_coverage_btts=aggregate_coverage,
        aggregate_coverage_totals=aggregate_coverage,
        total_line=float(total_line),
        model_version=model_version,
    )
