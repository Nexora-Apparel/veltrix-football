from scripts.audit_historical_model import audit_report


def _report():
    return {
        "as_of_date": "2026-10-25",
        "generated_at_utc": "2026-10-25T07:00:00+00:00",
        "historical_data_through": "2026-10-24",
        "same_day_only": True,
        "predictions": [
            {
                "fixture_id": 1, "kickoff": "2026-10-25T15:00:00+00:00",
                "kickoff_local": "2026-10-25T16:00:00+01:00",
                "home_team": "Alpha FC", "away_team": "Beta",
                "status": "EXPERIMENTAL_ONLY",
                "model": "experimental_recent_goals_poisson",
                "probabilities": {"home_win": .6, "draw": .2, "away_win": .2},
                "elo_probabilities": {"home_win": .5, "draw": .3, "away_win": .2},
                "advanced_model_alternative": {"probabilities": {"H": .55, "D": .25, "A": .2}},
            },
            {
                "fixture_id": 2, "kickoff": "2026-10-25T15:00:00+00:00",
                "kickoff_local": "2026-10-25T16:00:00+01:00",
                "home_team": "Gamma", "away_team": "Delta",
                "status": "UNSUPPORTED_COMPETITION",
            },
        ],
    }


def test_audit_scores_models_on_same_exact_fixture_identity():
    cache = {"matches": [
        {"date": "2026-10-25", "home": "Alpha", "away": "Beta FC",
         "home_goals": 2, "away_goals": 0, "source_provider": "5DollarFootballAPI"},
    ]}
    result = audit_report(_report(), cache)
    assert result["forecast_eligible"] == 1
    assert result["matched_forecast_fixtures"] == 1
    assert result["common_fixture_count_for_model_comparison"] == 1
    assert result["metrics_by_model_on_common_fixtures"]["experimental_recent_goals_poisson"]["accuracy"] == 1
    assert result["metrics_by_model_on_common_fixtures"]["experimental_elo_by_competition"]["accuracy"] == 1
    assert result["metrics_by_model_on_common_fixtures"]["experimental_recency_weighted_dixon_coles"]["accuracy"] == 1


def test_audit_refuses_to_score_forecasts_generated_after_kickoff():
    report = _report()
    report["generated_at_utc"] = "2026-10-25T18:00:00+00:00"
    cache = {"matches": [
        {"date": "2026-10-25", "home": "Alpha FC", "away": "Beta",
         "home_goals": 2, "away_goals": 0},
    ]}
    result = audit_report(report, cache)
    assert result["excluded_non_chronological"] == 1
    assert result["matched_forecast_fixtures"] == 0


def test_audit_does_not_match_by_team_name_without_exact_date():
    cache = {"matches": [
        {"date": "2026-10-26", "home": "Alpha", "away": "Beta",
         "home_goals": 2, "away_goals": 0},
    ]}
    result = audit_report(_report(), cache)
    assert result["unmatched_forecast_fixtures"] == 1
    assert result["common_fixture_count_for_model_comparison"] == 0
