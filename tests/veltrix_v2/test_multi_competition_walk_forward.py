from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.evaluation.multi_competition_walk_forward import (
    run_multi_competition_walk_forward,
)
from veltrix_v2.evaluation.walk_forward import WalkForwardFold
from veltrix_v2.models.poisson_strength import TrainingMatch

UTC = timezone.utc


def match(fixture, comp, day, home, away, hg, ag):
    kickoff = datetime(2026, 1, day, 15, tzinfo=UTC)
    return TrainingMatch(
        fixture_id=fixture,
        competition_key=comp,
        season="2025-26",
        kickoff_utc=kickoff,
        available_at_utc=kickoff + timedelta(hours=2),
        home_team_id=home,
        away_team_id=away,
        home_goals=hg,
        away_goals=ag,
        source_observation_id=f"obs-{fixture}",
    )


def test_aggregates_multiple_competitions_without_pooling_strength_models(monkeypatch):
    rows = [
        match("a-train", "league-a", 1, "A1", "A2", 2, 0),
        match("a-test", "league-a", 10, "A1", "A2", 1, 1),
        match("b-train", "league-b", 1, "B1", "B2", 1, 0),
        match("b-test", "league-b", 10, "B1", "B2", 0, 2),
    ]
    fit_scopes = []

    class FakeModel:
        converged = True
        objective = 1.0
        training_availability_bases = ("unspecified",)

        def expected_goals(self, home_team_id, away_team_id):
            return (1.3, 1.1)

    def fake_folds(fixtures, **kwargs):
        ids = {row.fixture_id for row in fixtures}
        train_id = next(item for item in ids if item.endswith("train"))
        test_id = next(item for item in ids if item.endswith("test"))
        return (WalkForwardFold(
            fold_number=1,
            train_fixture_ids=(train_id,),
            test_fixture_ids=(test_id,),
            test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_end_utc=datetime(2026, 1, 17, tzinfo=UTC),
            training_label_cutoff_utc=datetime(2026, 1, 9, tzinfo=UTC),
        ),)

    def fake_fit(training, *, competition_key, **kwargs):
        fit_scopes.append((competition_key, tuple(row.fixture_id for row in training)))
        return FakeModel()

    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.build_expanding_walk_forward_folds",
        fake_folds,
    )
    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.fit_poisson_strength_model",
        fake_fit,
    )
    result = run_multi_competition_walk_forward(
        rows,
        competition_seasons=(("league-a", "2025-26"), ("league-b", "2025-26")),
        first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
        test_window=timedelta(days=7),
        n_splits=1,
        minimum_training_matches=1,
    )
    assert result.total_test_fixtures == 2
    assert result.total_forecasts == 2
    assert result.aggregate_1x2.sample_size == 2
    assert result.aggregate_btts.sample_size == 2
    assert result.aggregate_totals.sample_size == 2
    assert result.coverage_1x2.coverage == 1.0
    assert result.total_folds == 2
    assert result.converged_folds == 2
    assert result.model_convergence_rate == 1.0
    assert {scope for scope, _ in fit_scopes} == {"league-a", "league-b"}
    assert all(len(train_ids) == 1 for _, train_ids in fit_scopes)


def test_missing_competition_scope_fails_closed():
    rows = [match("a-train", "league-a", 1, "A1", "A2", 2, 0)]
    with pytest.raises(ValueError, match="SCOPE_DATA_MISSING"):
        run_multi_competition_walk_forward(
            rows,
            competition_seasons=(("league-b", "2025-26"),),
            first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_window=timedelta(days=7),
            n_splits=1,
            minimum_training_matches=1,
        )


def test_duplicate_competition_scope_is_rejected():
    rows = [match("a-train", "league-a", 1, "A1", "A2", 2, 0)]
    with pytest.raises(ValueError, match="SCOPES_REQUIRED_AND_UNIQUE"):
        run_multi_competition_walk_forward(
            rows,
            competition_seasons=(("league-a", "2025-26"), ("league-a", "2025-26")),
            first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_window=timedelta(days=7),
            n_splits=1,
            minimum_training_matches=1,
        )
