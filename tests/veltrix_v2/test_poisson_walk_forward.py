from datetime import datetime, timedelta, timezone

from veltrix_v2.evaluation.poisson_walk_forward import run_poisson_walk_forward
from veltrix_v2.models.poisson_strength import TrainingMatch


BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def dataset():
    rows = []
    fixture = 0
    for week in range(18):
        for home, away in (("A", "B"), ("B", "C"), ("C", "A")):
            fixture += 1
            kickoff = BASE + timedelta(days=week * 7 + fixture % 3)
            # Deterministic outcomes for pipeline integration, not model quality claims.
            home_goals = 2 if home == "A" else 1
            away_goals = 0 if away == "B" else 1
            rows.append(TrainingMatch(
                f"f{fixture}", "league", "2024/25", kickoff,
                kickoff + timedelta(hours=4), home, away,
                home_goals, away_goals, f"obs{fixture}",
                availability_basis="source_timestamp", source_training_approved=True,
            ))
    return rows


def test_each_fold_fits_only_past_and_scores_disjoint_future_fixtures():
    result = run_poisson_walk_forward(
        dataset(), competition_key="league", season="2024/25",
        first_test_start_utc=BASE + timedelta(days=84),
        test_window=timedelta(days=14), n_splits=2,
        minimum_training_matches=30, minimum_team_matches=10,
        model_version="test-wf",
    )
    assert len(result.folds) == 2
    assert result.total_test_fixtures == 12
    assert result.total_forecasts + result.total_abstentions == 12
    assert result.aggregate_score is not None
    assert result.aggregate_score.sample_size == result.total_forecasts
    assert result.folds[0].train_fixture_count == 36
    assert result.folds[1].train_fixture_count == 42
    assert result.folds[0].training_converged is True


def test_unknown_teams_are_abstained_without_fallback():
    rows = dataset()
    kickoff = BASE + timedelta(days=85)
    rows.append(TrainingMatch(
        "unknown", "league", "2024/25", kickoff,
        kickoff + timedelta(hours=4), "UNKNOWN", "A", 1, 0, "obs-unknown",
    ))
    result = run_poisson_walk_forward(
        rows, competition_key="league", season="2024/25",
        first_test_start_utc=BASE + timedelta(days=84),
        test_window=timedelta(days=14), n_splits=1,
        minimum_training_matches=30, minimum_team_matches=10,
    )
    assert "unknown" in result.folds[0].abstained_fixture_ids


def test_integer_total_lines_are_rejected_and_valid_negative_rho_is_supported():
    args = dict(
        matches=dataset(), competition_key="league", season="2024/25",
        first_test_start_utc=BASE + timedelta(days=84),
        test_window=timedelta(days=14), n_splits=1,
        minimum_training_matches=30,
    )
    try:
        run_poisson_walk_forward(**args, total_line=2.0)
        assert False, "integer line must be rejected"
    except ValueError as exc:
        assert "HALF_GOAL" in str(exc)
    result = run_poisson_walk_forward(**args, rho=-0.05)
    assert result.total_test_fixtures == 6


def test_nonconverged_model_abstains_from_every_test_fixture(monkeypatch):
    class NonConvergedModel:
        objective = 123.0
        converged = False

    monkeypatch.setattr(
        "veltrix_v2.evaluation.poisson_walk_forward.fit_poisson_strength_model",
        lambda *args, **kwargs: NonConvergedModel(),
    )
    result = run_poisson_walk_forward(
        dataset(), competition_key="league", season="2024/25",
        first_test_start_utc=BASE + timedelta(days=84),
        test_window=timedelta(days=14), n_splits=1,
        minimum_training_matches=30, minimum_team_matches=10,
    )
    fold = result.folds[0]
    assert fold.training_converged is False
    assert fold.forecast_count == 0
    assert fold.score_report is None
    assert len(fold.abstained_fixture_ids) == fold.test_fixture_count
    assert result.total_forecasts == 0
    assert result.total_abstentions == result.total_test_fixtures
