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


def test_walk_forward_binds_model_build_id_to_every_scored_fixture():
    report = walk_forward_evaluate(
        history(40), evaluation_as_of=AS_OF, model_build_id="poisson-build-2026-11-14"
    )
    assert report.model_build_id == "poisson-build-2026-11-14"
    assert report.fixtures
    assert all(
        row.model_build_id == "poisson-build-2026-11-14"
        for row in report.fixtures
    )


def test_walk_forward_rejects_blank_model_build_id():
    with pytest.raises(ValueError, match="MODEL_BUILD_ID_INVALID"):
        walk_forward_evaluate(history(40), evaluation_as_of=AS_OF, model_build_id=" ")


@pytest.mark.parametrize(
    ("available_delta", "recorded_delta"),
    [
        (timedelta(hours=-1), timedelta(hours=2)),
        (timedelta(hours=2), timedelta(hours=1)),
    ],
)
def test_walk_forward_rejects_impossible_target_result_chronology(
    available_delta, recorded_delta,
):
    rows = history(40)
    target = rows[-2]
    rows[-2] = replace(
        target,
        available_at=target.kickoff_at + available_delta,
        recorded_at=target.kickoff_at + recorded_delta,
    )
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.skipped_invalid_target >= 1
    assert all(row.fixture_id != target.fixture_id for row in report.fixtures)


def test_walk_forward_allows_non_pit_result_as_label_but_never_as_training():
    rows = history(40)
    target = rows[-1]
    rows[-1] = replace(target, point_in_time_certifiable=False)
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.non_certifiable_input_rows == 1
    assert target.fixture_id in {row.fixture_id for row in report.fixtures}


def test_walk_forward_rejects_target_with_invalid_pit_payload_hash():
    rows = history(40)
    target = rows[-1]
    rows[-1] = replace(target, payload_sha256="not-a-sha256")
    report = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    assert report.skipped_invalid_target >= 1
    assert all(row.fixture_id != target.fixture_id for row in report.fixtures)



def test_walk_forward_exposes_only_cutoff_eligible_openplay_context():
    rows = history(40)
    target = rows[-1]
    cutoff = target.kickoff_at - timedelta(seconds=1)
    eligible_at = cutoff - timedelta(hours=1)
    approval_hash = "5e6bd00416f180109751e422521d76910da8b491c62507c4d9836e6700c38c46"
    assets = {
        name: {"provider_response_id": response_id,
               "source_observation_id": observation_id, "sha256": "a" * 64}
        for name, response_id, observation_id in (
            ("matches.parquet", 101, 101),
            ("team_match_stats.parquet", 102, 102),
            ("player_match_stats.parquet", 103, 103),
            ("lineups.parquet", 104, 104),
            ("shots.parquet", 105, 105),
            ("cards.parquet", 106, 106),
            ("formations.parquet", 107, 107),
            ("teams.parquet", 108, 108),
            ("competitions.parquet", 109, 109),
        )
    }

    def feature(team, opponent, match_id, match_date, eligibility=eligible_at):
        crosswalk_times = (eligibility - timedelta(minutes=1)).isoformat()
        return {
            "canonical_team_id": team,
            "canonical_opponent_id": opponent,
            "canonical_competition_id": "league",
            "provider_team_id": team,
            "provider_opponent_id": opponent,
            "competition_code": "league",
            "provider_match_id": match_id,
            "match_date": match_date,
            "source_published_at": (eligibility - timedelta(days=2)).isoformat(),
            "available_at": (eligibility - timedelta(days=2)).isoformat(),
            "recorded_at": (eligibility - timedelta(hours=1)).isoformat(),
            "eligibility_at": eligibility.isoformat(),
            "point_in_time_certifiable": True,
            "commercial_use_allowed": False,
            "monetisation_prohibited": True,
            "rights_approval_id": "approval-openplay-whoscored-opta-noncommercial-2026-11-15",
            "source_timestamp_basis": "documented_guarantee",
            "source_observation_id": 700,
            "provider_response_id": 101,
            "asset_provenance": assets,
            "crosswalk_provenance": {
                "team": {
                    "provider_entity_id": team, "canonical_entity_id": team,
                    "mapping_status": "RESOLVED", "evidence_observation_id": 108,
                    "mapping_method": "EXACT_NAME_AND_COMPETITION_OVERLAP",
                    "crosswalk_version_id": 20, "valid_from": crosswalk_times,
                    "recorded_at": crosswalk_times, "valid_until": None,
                },
                "opponent": {
                    "provider_entity_id": opponent, "canonical_entity_id": opponent,
                    "mapping_status": "RESOLVED", "evidence_observation_id": 108,
                    "mapping_method": "EXACT_NAME_AND_COMPETITION_OVERLAP",
                    "crosswalk_version_id": 21, "valid_from": crosswalk_times,
                    "recorded_at": crosswalk_times, "valid_until": None,
                },
                "competition": {
                    "provider_entity_id": "league", "canonical_entity_id": "league",
                    "mapping_status": "RESOLVED", "evidence_observation_id": 109,
                    "mapping_method": "EXPLICIT_REGION_NAME_ALIAS",
                    "crosswalk_version_id": 22, "valid_from": crosswalk_times,
                    "recorded_at": crosswalk_times, "valid_until": None,
                },
            },
            "approval_provenance": {
                "status": "APPROVED", "evidence_sha256": approval_hash,
                "effective_at": (eligibility - timedelta(days=1)).isoformat(),
                "valid_from": (eligibility - timedelta(days=1)).isoformat(),
                "recorded_at": (eligibility - timedelta(days=1)).isoformat(),
                "approval_recorded_at": (eligibility - timedelta(days=1)).isoformat(),
                "valid_until": None,
            },
        }

    prior_date = (target.kickoff_at.date() - timedelta(days=3)).isoformat()
    features = [
        feature(target.home_team_id, target.away_team_id, "prior-home", prior_date),
        feature(target.away_team_id, target.home_team_id, "prior-away", prior_date),
        feature(target.home_team_id, target.away_team_id, "same-day",
                target.kickoff_at.date().isoformat()),
        feature(target.away_team_id, target.home_team_id, "future", prior_date,
                cutoff + timedelta(seconds=1)),
    ]
    report = walk_forward_evaluate(
        rows, evaluation_as_of=AS_OF, openplay_features=features
    )
    evaluated = next(row for row in report.fixtures if row.fixture_id == target.fixture_id)
    assert evaluated.openplay_home_feature_rows == 1
    assert evaluated.openplay_away_feature_rows == 1
    assert evaluated.openplay_latest_feature_eligibility_at == eligible_at

def test_walk_forward_openplay_context_is_optional_and_does_not_change_baseline_predictions():
    rows = history(40)
    without_context = walk_forward_evaluate(rows, evaluation_as_of=AS_OF)
    with_context = walk_forward_evaluate(rows, evaluation_as_of=AS_OF, openplay_features=())
    assert [row.model_home_win for row in without_context.fixtures] == [
        row.model_home_win for row in with_context.fixtures
    ]
    assert all(row.openplay_home_feature_rows == 0 for row in with_context.fixtures)
