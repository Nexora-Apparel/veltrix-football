from datetime import datetime, timedelta, timezone

from veltrix_v2.evaluation.multi_market_walk_forward import (
    run_multi_market_walk_forward,
)
from veltrix_v2.evaluation.walk_forward import WalkForwardFold
from veltrix_v2.models.poisson_strength import TrainingMatch


UTC = timezone.utc


def match(fixture, day, home, away, home_goals, away_goals, *, quality_state="valid", approved=True, availability_basis="source_timestamp"):
    kickoff = datetime(2026, 1, day, 15, tzinfo=UTC)
    return TrainingMatch(
        fixture_id=fixture,
        competition_key="league-a",
        season="2025-26",
        kickoff_utc=kickoff,
        available_at_utc=kickoff + timedelta(hours=2),
        home_team_id=home,
        away_team_id=away,
        home_goals=home_goals,
        away_goals=away_goals,
        source_observation_id=f"obs-{fixture}",
        quality_state=quality_state,
        availability_basis=availability_basis,
        source_training_approved=approved,
    )


def test_all_three_markets_share_same_forecast_coverage(monkeypatch):
    rows = [
        match("train-1", 1, "A", "B", 2, 0),
        match("train-2", 2, "B", "A", 0, 1),
        match("test-1", 10, "A", "B", 2, 1),
        match("test-2", 11, "B", "A", 0, 0),
    ]

    class FakeModel:
        objective = 1.0
        converged = True

        def expected_goals(self, home_team_id, away_team_id):
            return (1.4, 1.0)

    def fake_folds(*args, **kwargs):
        return (WalkForwardFold(
            fold_number=1,
            train_fixture_ids=("train-1", "train-2"),
            test_fixture_ids=("test-1", "test-2"),
            test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_end_utc=datetime(2026, 1, 17, tzinfo=UTC),
            training_label_cutoff_utc=datetime(2026, 1, 9, tzinfo=UTC),
        ),)

    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.build_expanding_walk_forward_folds",
        fake_folds,
    )
    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.fit_poisson_strength_model",
        lambda *args, **kwargs: FakeModel(),
    )
    result = run_multi_market_walk_forward(
        rows,
        competition_key="league-a",
        season="2025-26",
        first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
        test_window=timedelta(days=7),
        n_splits=1,
        minimum_training_matches=2,
    )
    fold = result.folds[0]
    assert result.total_test_fixtures == 2
    assert result.total_forecasts == 2
    assert result.total_abstentions == 0
    assert fold.score_1x2.sample_size == 2
    assert fold.training_fixture_ids == ("train-1", "train-2")
    assert fold.training_observation_ids == ("obs-train-1", "obs-train-2")
    assert fold.btts_report.sample_size == 2
    assert fold.totals_report.sample_size == 2
    assert fold.btts_report.coverage == fold.totals_report.coverage == 1.0
    assert fold.btts_report.eligible_fixture_count == 2
    assert fold.totals_report.eligible_fixture_count == 2
    assert fold.coverage_1x2.coverage == 1.0
    assert fold.coverage_btts.coverage == 1.0
    assert fold.coverage_totals.coverage == 1.0
    assert result.aggregate_coverage_1x2.forecast_count == 2


def test_unknown_team_abstention_counts_against_every_market(monkeypatch):
    rows = [
        match("train-1", 1, "A", "B", 2, 0),
        match("test-1", 10, "UNKNOWN", "B", 1, 0),
    ]

    class FakeModel:
        objective = 1.0
        converged = True

        def expected_goals(self, home_team_id, away_team_id):
            raise ValueError("unknown team")

    def fake_folds(*args, **kwargs):
        return (WalkForwardFold(
            fold_number=1,
            train_fixture_ids=("train-1",),
            test_fixture_ids=("test-1",),
            test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_end_utc=datetime(2026, 1, 17, tzinfo=UTC),
            training_label_cutoff_utc=datetime(2026, 1, 9, tzinfo=UTC),
        ),)

    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.build_expanding_walk_forward_folds",
        fake_folds,
    )
    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.fit_poisson_strength_model",
        lambda *args, **kwargs: FakeModel(),
    )
    result = run_multi_market_walk_forward(
        rows,
        competition_key="league-a",
        season="2025-26",
        first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
        test_window=timedelta(days=7),
        n_splits=1,
        minimum_training_matches=1,
    )
    assert result.total_abstentions == 1
    assert result.total_forecasts == 0
    assert result.aggregate_1x2 is None
    assert result.aggregate_btts is None
    assert result.aggregate_totals is None
    assert result.folds[0].abstained_fixture_ids == ("test-1",)
    assert result.folds[0].coverage_1x2.eligible_fixture_count == 1
    assert result.folds[0].coverage_1x2.forecast_count == 0
    assert result.folds[0].coverage_1x2.abstention_count == 1
    assert result.folds[0].coverage_1x2.coverage == 0.0
    assert result.folds[0].coverage_btts.coverage == 0.0
    assert result.folds[0].coverage_totals.coverage == 0.0
    assert result.aggregate_coverage_1x2.coverage == 0.0


def test_integer_totals_line_is_rejected():
    rows = [match("train-1", 1, "A", "B", 2, 0)]
    import pytest
    with pytest.raises(ValueError, match="HALF_GOAL"):
        run_multi_market_walk_forward(
            rows,
            competition_key="league-a",
            season="2025-26",
            first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_window=timedelta(days=7),
            n_splits=1,
            total_line=2.0,
        )


def test_nonconverged_model_abstains_from_all_markets(monkeypatch):
    rows = [
        match("train-1", 1, "A", "B", 2, 0),
        match("test-1", 10, "A", "B", 1, 0),
    ]

    class NonConvergedModel:
        converged = False
        objective = 123.0
        training_availability_bases = ("date_only_conservative_4d",)

        def expected_goals(self, home_team_id, away_team_id):
            return (1.4, 1.0)

    def fake_folds(*args, **kwargs):
        return (WalkForwardFold(
            fold_number=1,
            train_fixture_ids=("train-1",),
            test_fixture_ids=("test-1",),
            test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_end_utc=datetime(2026, 1, 17, tzinfo=UTC),
            training_label_cutoff_utc=datetime(2026, 1, 9, tzinfo=UTC),
        ),)

    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.build_expanding_walk_forward_folds",
        fake_folds,
    )
    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.fit_poisson_strength_model",
        lambda *args, **kwargs: NonConvergedModel(),
    )
    result = run_multi_market_walk_forward(
        rows,
        competition_key="league-a",
        season="2025-26",
        first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
        test_window=timedelta(days=7),
        n_splits=1,
        minimum_training_matches=1,
    )
    fold = result.folds[0]
    assert fold.model_converged is False
    assert fold.model_objective == 123.0
    assert fold.training_availability_bases == ("date_only_conservative_4d",)
    assert fold.abstained_fixture_ids == ("test-1",)
    assert fold.coverage_1x2.coverage == 0.0
    assert fold.coverage_btts.coverage == 0.0
    assert fold.coverage_totals.coverage == 0.0


def test_quarantined_test_fixture_is_excluded_from_evaluation_universe(monkeypatch):
    rows = [
        match("train-1", 1, "A", "B", 2, 0),
        match("test-valid", 10, "A", "B", 1, 0),
        match("test-quarantined", 11, "B", "A", 99, 0, quality_state="quarantined"),
    ]

    class FakeModel:
        objective = 1.0
        converged = True

        def expected_goals(self, home_team_id, away_team_id):
            return (1.4, 1.0)

    def fake_folds(fixtures, **kwargs):
        fixture_ids = {row.fixture_id for row in fixtures}
        assert "test-quarantined" not in fixture_ids
        return (WalkForwardFold(
            fold_number=1,
            train_fixture_ids=("train-1",),
            test_fixture_ids=("test-valid",),
            test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_end_utc=datetime(2026, 1, 17, tzinfo=UTC),
            training_label_cutoff_utc=datetime(2026, 1, 9, tzinfo=UTC),
        ),)

    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.build_expanding_walk_forward_folds",
        fake_folds,
    )
    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.fit_poisson_strength_model",
        lambda *args, **kwargs: FakeModel(),
    )
    result = run_multi_market_walk_forward(
        rows,
        competition_key="league-a", season="2025-26",
        first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
        test_window=timedelta(days=7), n_splits=1,
        minimum_training_matches=1,
    )
    assert result.total_test_fixtures == 1
    assert result.folds[0].eligible_fixture_ids == ("test-valid",)


def test_unapproved_held_out_result_source_fails_closed():
    rows = [
        match("train-1", 1, "A", "B", 2, 0),
        match("test-unapproved", 10, "A", "B", 1, 0, approved=False),
    ]
    import pytest
    with pytest.raises(ValueError, match="SOURCE_NOT_APPROVED_FOR_EVALUATION"):
        run_multi_market_walk_forward(
            rows,
            competition_key="league-a", season="2025-26",
            first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_window=timedelta(days=7), n_splits=1,
            minimum_training_matches=1,
        )
