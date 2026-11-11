"""End-to-end chronological evaluation for the unfitted V2 Poisson/DC stack.

Each fold fits team strengths only on results available by its training cutoff.
Test fixtures are forecast once, scored only after their outcomes are settled.
Unseen teams and invalid model fits are abstentions, never generic fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from veltrix_v2.evaluation.metrics import Forecast1X2, ScoreReport1X2, SettledOutcome1X2, score_1x2
from veltrix_v2.evaluation.walk_forward import EvaluationFixture, build_expanding_walk_forward_folds
from veltrix_v2.models.dixon_coles import build_dixon_coles_forecast
from veltrix_v2.models.poisson_strength import TrainingMatch, fit_poisson_strength_model


@dataclass(frozen=True, slots=True)
class FoldEvaluation:
    fold_number: int
    train_fixture_count: int
    test_fixture_count: int
    forecast_count: int
    abstained_fixture_ids: tuple[str, ...]
    forecasts: tuple[Forecast1X2, ...]
    outcomes: tuple[SettledOutcome1X2, ...]
    score_report: ScoreReport1X2 | None
    training_objective: float | None
    training_converged: bool | None


@dataclass(frozen=True, slots=True)
class WalkForwardEvaluation:
    competition_key: str
    season: str
    folds: tuple[FoldEvaluation, ...]
    total_test_fixtures: int
    total_forecasts: int
    total_abstentions: int
    aggregate_score: ScoreReport1X2 | None
    model_version: str


def run_poisson_walk_forward(
    matches: Iterable[TrainingMatch],
    *,
    competition_key: str,
    season: str,
    first_test_start_utc: datetime,
    test_window: timedelta,
    n_splits: int,
    embargo: timedelta = timedelta(0),
    minimum_training_matches: int = 40,
    minimum_team_matches: int = 3,
    recency_half_life_days: float = 180.0,
    ridge: float = 0.05,
    rho: float = 0.0,
    total_line: float = 2.5,
    model_version: str = "veltrix-v2-poisson-dc-wf-0.1",
) -> WalkForwardEvaluation:
    rows = tuple(matches)
    if not rows:
        raise ValueError("WALK_FORWARD_MATCH_DATA_REQUIRED")
    if isinstance(rho, bool) or not isinstance(rho, (int, float)):
        raise ValueError("WALK_FORWARD_RHO_MUST_BE_NUMERIC")
    if abs((total_line % 1.0) - 0.5) > 1e-9 or total_line < 0:
        raise ValueError("WALK_FORWARD_TOTAL_LINE_MUST_BE_HALF_GOAL")
    eval_fixtures = tuple(
        EvaluationFixture(row.fixture_id, row.kickoff_utc, row.available_at_utc)
        for row in rows if row.competition_key == competition_key and row.season == season
    )
    if not eval_fixtures:
        raise ValueError("WALK_FORWARD_SCOPE_HAS_NO_FIXTURES")
    folds = build_expanding_walk_forward_folds(
        eval_fixtures,
        first_test_start_utc=first_test_start_utc,
        test_window=test_window,
        n_splits=n_splits,
        embargo=embargo,
        min_train_fixtures=minimum_training_matches,
    )
    fold_results = []
    all_forecasts = []
    all_outcomes = []
    total_tests = total_abstentions = 0

    for fold in folds:
        train_ids = set(fold.train_fixture_ids)
        test_ids = set(fold.test_fixture_ids)
        training_rows = [
            row for row in rows
            if row.fixture_id in train_ids
            and row.competition_key == competition_key
            and row.season == season
        ]
        test_rows = [
            row for row in rows
            if row.fixture_id in test_ids
            and row.competition_key == competition_key
            and row.season == season
        ]
        model = fit_poisson_strength_model(
            training_rows,
            competition_key=competition_key,
            season=season,
            training_cutoff_utc=fold.training_label_cutoff_utc,
            minimum_matches=minimum_training_matches,
            minimum_team_matches=minimum_team_matches,
            recency_half_life_days=recency_half_life_days,
            ridge=ridge,
            model_version=f"{model_version}-fold-{fold.fold_number}",
        )
        forecasts = []
        outcomes = []
        abstained = []
        if not model.converged:
            abstained.extend(row.fixture_id for row in test_rows)
        for row in (() if not model.converged else sorted(test_rows, key=lambda item: (item.kickoff_utc, item.fixture_id))):
            total_tests += 1
            try:
                expected_home, expected_away = model.expected_goals(row.home_team_id, row.away_team_id)
                joint = build_dixon_coles_forecast(
                    fixture_id=row.fixture_id,
                    expected_home_goals=expected_home,
                    expected_away_goals=expected_away,
                    rho=rho,
                    model_version=f"{model_version}-fold-{fold.fold_number}",
                )
                markets = joint.distribution.derive_markets(total_line=total_line)
                forecasts.append(Forecast1X2(
                    row.fixture_id, markets.p_home_win, markets.p_draw, markets.p_away_win,
                ))
                outcome = "HOME" if row.home_goals > row.away_goals else "AWAY" if row.home_goals < row.away_goals else "DRAW"
                outcomes.append(SettledOutcome1X2(row.fixture_id, outcome))
            except ValueError:
                abstained.append(row.fixture_id)
        report = score_1x2(forecasts, outcomes) if forecasts else None
        total_abstentions += len(abstained)
        all_forecasts.extend(forecasts)
        all_outcomes.extend(outcomes)
        fold_results.append(FoldEvaluation(
            fold.fold_number, len(training_rows), len(test_rows), len(forecasts),
            tuple(abstained), tuple(forecasts), tuple(outcomes), report,
            model.objective, model.converged,
        ))

    aggregate = score_1x2(all_forecasts, all_outcomes) if all_forecasts else None
    return WalkForwardEvaluation(
        competition_key, season, tuple(fold_results), total_tests,
        len(all_forecasts), total_abstentions, aggregate, model_version,
    )
