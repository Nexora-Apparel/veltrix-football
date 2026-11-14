from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from veltrix_v2.evaluation.walk_forward import walk_forward_evaluate
from veltrix_v2.models.poisson import MatchObservation

UTC = timezone.utc
AS_OF = datetime(2026, 11, 14, 23, tzinfo=UTC)


def history(n=40):
    rows = []
    teams = ["A", "B", "C", "D", "E", "F"]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        kickoff = start + timedelta(days=i * 2)
        home = teams[i % len(teams)]
        away = teams[(i + 1) % len(teams)]
        rows.append(MatchObservation(
            fixture_id=f"fixture-{i}", competition_id="league",
            home_team_id=home, away_team_id=away,
            kickoff_at=kickoff,
            available_at=kickoff + timedelta(hours=2),
            recorded_at=kickoff + timedelta(hours=3),
            home_goals=1 + (i % 3 == 0), away_goals=i % 2,
            point_in_time_certifiable=True,
        ))
    return rows


def test_walk_forward_is_chronological_and_scores_only_after_results_exist():
    rows = history(40)
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.total_input_fixtures == 40
    assert report.eligible_scored_fixtures > 0
    assert report.one_x_two is not None
    assert report.btts is not None and report.over_2_5 is not None
    assert all(x.cutoff_at < x.kickoff_at for x in report.fixtures)
    assert all(report.fixtures[i].kickoff_at <= report.fixtures[i + 1].kickoff_at
               for i in range(len(report.fixtures) - 1))
    assert report.one_x_two.sample_count == report.eligible_scored_fixtures


def test_future_result_and_future_fixture_are_not_scored():
    rows = history(40)
    future = rows[-1]
    rows[-1] = MatchObservation(
        fixture_id=future.fixture_id, competition_id=future.competition_id,
        home_team_id=future.home_team_id, away_team_id=future.away_team_id,
        kickoff_at=future.kickoff_at, available_at=AS_OF + timedelta(days=1),
        recorded_at=AS_OF + timedelta(days=1), home_goals=future.home_goals,
        away_goals=future.away_goals,
    )
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.skipped_after_evaluation_as_of == 1
    assert all(x.fixture_id != future.fixture_id for x in report.fixtures)


def test_duplicate_fixture_ids_are_excluded_from_evaluation():
    rows = history(40)
    rows.append(rows[0])
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.skipped_duplicate_ids == 2
    assert all(x.fixture_id != rows[0].fixture_id for x in report.fixtures)


def test_competition_isolation_and_no_history_are_explicit():
    rows = history(20)
    rows.extend(history(10))
    rows[-10:] = [MatchObservation(
        fixture_id=f"other-{i}", competition_id="other",
        home_team_id=f"X{i}", away_team_id=f"Y{i}",
        kickoff_at=row.kickoff_at, available_at=row.available_at,
        recorded_at=row.recorded_at, home_goals=row.home_goals,
        away_goals=row.away_goals,
    ) for i, row in enumerate(rows[-10:])]
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.skipped_no_history > 0
    assert all(x.competition_id == "league" for x in report.fixtures)


def test_evaluation_as_of_must_be_timezone_aware():
    with pytest.raises(ValueError, match="EVALUATION_AS_OF_MUST_BE_TIMEZONE_AWARE"):
        walk_forward_evaluate(history(), evaluation_as_of=datetime(2026, 11, 14))


def test_walk_forward_metrics_are_finite_and_improvement_sign_is_consistent():
    report = walk_forward_evaluate(history(40), evaluation_as_of=AS_OF)
    for market in (report.one_x_two, report.btts, report.over_2_5):
        assert market is not None
        assert all(value >= 0 for value in (market.model_brier, market.baseline_brier,
                                            market.model_log_loss, market.baseline_log_loss))
        assert market.brier_improvement == pytest.approx(market.baseline_brier - market.model_brier)
        assert market.log_loss_improvement == pytest.approx(market.baseline_log_loss - market.model_log_loss)


def test_date_only_archive_rows_can_train_future_targets_but_are_not_scored_as_targets():
    snapshot = datetime(2026, 8, 21, 7, 43, tzinfo=UTC)
    rows = []
    pairs = [("A", "C"), ("D", "B"), ("C", "A"), ("B", "D")]
    for i in range(12):
        home, away = pairs[i % len(pairs)]
        rows.append(MatchObservation(
            fixture_id=f"archive-{i}", competition_id="league",
            home_team_id=home, away_team_id=away,
            kickoff_at=None, available_at=snapshot, recorded_at=snapshot,
            home_goals=1 + (i % 2), away_goals=i % 2,
            kickoff_date=date(2026, 8, 1 + (i % 10)),
            point_in_time_certifiable=True,
        ))
    kickoff = datetime(2026, 11, 20, 12, tzinfo=UTC)
    rows.append(MatchObservation(
        fixture_id="future-target", competition_id="league",
        home_team_id="A", away_team_id="B", kickoff_at=kickoff,
        available_at=kickoff + timedelta(hours=2),
        recorded_at=kickoff + timedelta(hours=3), home_goals=2, away_goals=1,
    ))
    report = walk_forward_evaluate(rows, evaluation_as_of=datetime(2026, 11, 22, tzinfo=UTC))
    assert report.skipped_date_only_targets == 12
    assert report.eligible_scored_fixtures == 1
    assert report.fixtures[0].fixture_id == "future-target"


def test_non_certifiable_provider_snapshots_are_excluded_from_historical_training():
    rows = [replace(row, point_in_time_certifiable=False) for row in history(40)]
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.non_certifiable_input_rows == 40
    assert report.eligible_scored_fixtures == 0
    assert report.skipped_no_history > 0


def test_walk_forward_records_and_applies_recency_half_life():
    report = walk_forward_evaluate(
        history(40), evaluation_as_of=AS_OF, recency_half_life_days=30
    )
    assert report.recency_half_life_days == 30
    assert report.eligible_scored_fixtures > 0


def test_walk_forward_rejects_invalid_recency_half_life():
    import pytest
    with pytest.raises(ValueError, match="RECENCY_HALF_LIFE_MUST_BE_POSITIVE_FINITE"):
        walk_forward_evaluate(history(40), evaluation_as_of=AS_OF,
                              recency_half_life_days=0)


def test_walk_forward_records_dixon_coles_candidate_configuration():
    report = walk_forward_evaluate(
        history(40), evaluation_as_of=AS_OF, dixon_coles_rho=-0.1
    )
    assert report.dixon_coles_rho == -0.1
    assert report.eligible_scored_fixtures > 0


def test_walk_forward_rejects_invalid_dixon_coles_rho():
    import pytest
    with pytest.raises(ValueError, match="DIXON_COLES_RHO_INVALID"):
        walk_forward_evaluate(history(40), evaluation_as_of=AS_OF,
                              dixon_coles_rho=1.5)
