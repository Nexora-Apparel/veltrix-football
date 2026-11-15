from datetime import datetime, timedelta, timezone
import pytest

from veltrix_v2.models.poisson import MatchObservation
from veltrix_v2.models.dixon_coles import (
    build_dixon_coles_rate_history, predict_dixon_coles_match,
)
from veltrix_v2.evaluation.model_challengers import evaluate_model_challengers
from veltrix_v2.evaluation.walk_forward import walk_forward_evaluate

UTC = timezone.utc


def pit_history(count=100):
    teams = ["A", "B", "C", "D", "E", "F"]
    rows = []
    origin = datetime(2026, 1, 1, 12, tzinfo=UTC)
    for i in range(count):
        home = teams[i % len(teams)]
        away = teams[(i + 1 + (i % 3)) % len(teams)]
        kickoff = origin + timedelta(days=i)
        rows.append(MatchObservation(
            fixture_id=f"pit-{i}", competition_id="comp-1",
            home_team_id=home, away_team_id=away,
            kickoff_at=kickoff,
            available_at=kickoff + timedelta(hours=2),
            recorded_at=kickoff + timedelta(hours=3),
            home_goals=i % 4, away_goals=(i + 1) % 3,
            provider="unit-test", source_id=f"source-{i}",
            availability_basis="controlled_fixture_timestamp",
            point_in_time_certifiable=True,
        ))
    return rows


def test_dixon_coles_rolling_fit_excludes_outcomes_recorded_after_target_cutoff():
    rows = pit_history()
    cutoff = rows[-1].kickoff_at + timedelta(hours=1)
    rows[-1] = MatchObservation(**{
        **rows[-1].__dict__,
        "recorded_at": cutoff + timedelta(hours=1),
    })
    target_kickoff = cutoff + timedelta(hours=2)
    fitted = predict_dixon_coles_match(
        rows, competition_id="comp-1", home_team_id="A", away_team_id="B",
        kickoff_at=target_kickoff, cutoff_at=cutoff, minimum_fit_rows=30,
    )
    assert fitted.fit.observations >= 30
    assert fitted.fit.observations < len(rows)
    probs = (fitted.prediction.home_win, fitted.prediction.draw, fitted.prediction.away_win)
    assert abs(sum(probs) - 1.0) < 1e-9
    assert fitted.prediction.dixon_coles_rho == fitted.fit.rho


def test_challenger_evaluation_includes_dixon_coles_and_per_competition_calibration():
    rows = pit_history(100)
    report = evaluate_model_challengers(
        rows, evaluation_as_of=rows[-1].kickoff_at + timedelta(days=2),
    )
    assert report.scored_fixtures > 0
    assert report.metrics["poisson"].sample_count > 0
    assert report.metrics["dixon_coles"].sample_count > 0
    assert "comp-1" in report.calibration_metrics
    assert report.calibration_fit_samples.get("comp-1:poisson", 0) >= 50
    assert report.calibration_test_samples.get("comp-1:poisson", 0) > 0
    assert "poisson_temperature" in report.calibration_metrics["comp-1"]


def test_walk_forward_fits_platt_only_on_earlier_competition_rows():
    rows = pit_history(100)
    report = walk_forward_evaluate(
        rows, evaluation_as_of=rows[-1].kickoff_at + timedelta(days=2),
    )
    assert report.eligible_scored_fixtures > 0
    assert report.calibration_fit_samples.get("comp-1:btts", 0) >= 50
    assert report.calibration_test_samples.get("comp-1:btts", 0) > 0
    assert "btts" in report.competition_calibration["comp-1"]
    assert "over_2_5" in report.competition_calibration["comp-1"]


def test_precomputed_dixon_coles_rates_match_independent_pre_kickoff_poisson_rates():
    from veltrix_v2.models.poisson import predict_match
    rows = pit_history(100)
    cutoff = rows[-1].kickoff_at + timedelta(days=2)
    rate_rows = build_dixon_coles_rate_history(
        rows, competition_id="comp-1", as_of=cutoff,
    )
    assert len(rate_rows) >= 30
    sample = rate_rows[-1]
    historical = next(row for row in rows if row.fixture_id == sample.fixture_id)
    historical_cutoff = historical.kickoff_at - timedelta(seconds=1)
    prior = [row for row in rows if row.fixture_id != historical.fixture_id
             and row.kickoff_at < historical_cutoff
             and row.available_at <= historical_cutoff
             and row.recorded_at <= historical_cutoff]
    baseline = predict_match(
        prior, competition_id="comp-1", home_team_id=historical.home_team_id,
        away_team_id=historical.away_team_id, kickoff_at=historical.kickoff_at,
        cutoff_at=historical_cutoff,
    )
    assert sample.expected_home_goals == pytest.approx(baseline.expected_home_goals)
    assert sample.expected_away_goals == pytest.approx(baseline.expected_away_goals)
