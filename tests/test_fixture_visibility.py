import pytest

from scripts.validate_fixture_visibility import validate_fixture_visibility


def sample():
    return {
        "same_day_only": True,
        "future_fixtures_considered": 2,
        "same_day_fixtures_retained": 4,
        "predictions": [
            {"home_team": "A", "away_team": "B", "status": "EXPERIMENTAL_ONLY", "probabilities": {"home_win": .5, "draw": .2, "away_win": .3}},
            {"home_team": "C", "away_team": "D", "status": "INSUFFICIENT_HISTORY"},
            {"home_team": "E", "away_team": "F", "status": "KICKOFF_UNVERIFIED"},
            {"home_team": "G", "away_team": "H", "status": "KICKOFF_PASSED"},
        ],
    }


def test_fixture_visibility_counts_every_fixture_without_fabricating_forecasts():
    report = sample()
    result = validate_fixture_visibility(report)
    assert result["status"] == "PASSED"
    assert result["fixture_rows"] == 4
    assert result["forecast_rows"] == 1
    assert result["kickoff_unverified_rows"] == 1
    assert result["fixture_status_counts"]["KICKOFF_PASSED"] == 1
    assert report["fixture_visibility_validation"]["alerts_enabled"] is False


def test_fixture_visibility_fails_if_any_fixture_row_is_missing():
    report = sample()
    report["predictions"].pop()
    # Keep the original expected count: three rows remain but four were expected.
    with pytest.raises(ValueError, match="visibility mismatch"):
        validate_fixture_visibility(report)


def test_non_forecast_fixture_cannot_carry_model_probabilities():
    report = sample()
    report["predictions"][1]["probabilities"] = {"home_win": .7, "draw": .2, "away_win": .1}
    with pytest.raises(ValueError, match="unexpectedly contains probabilities"):
        validate_fixture_visibility(report)


def test_forecast_row_requires_probability_distribution():
    report = sample()
    report["predictions"][0].pop("probabilities")
    with pytest.raises(ValueError, match="has no probability distribution"):
        validate_fixture_visibility(report)



def test_legacy_low_data_forecast_probabilities_are_rejected():
    report = {
        "same_day_only": True,
        "future_fixtures_considered": 1,
        "predictions": [{
            "home_team": "Unknown Home",
            "away_team": "Unknown Away",
            "status": "EXPERIMENTAL_LOW_DATA",
            "probabilities": {"home_win": .45, "draw": .28, "away_win": .27},
        }],
    }
    with pytest.raises(ValueError, match="unexpectedly contains probabilities"):
        validate_fixture_visibility(report)


def test_fixture_visibility_accepts_withheld_low_history_fixtures_without_forecast_gate():
    rows = [{
        "home_team": f"Home {index}",
        "away_team": f"Away {index}",
        "status": "EXPERIMENTAL_ONLY" if index == 0 else "INSUFFICIENT_HISTORY",
        **({"probabilities": {"home_win": .4, "draw": .3, "away_win": .3}} if index == 0 else {}),
    } for index in range(24)]
    rows.append({
        "home_team": "Women's Home",
        "away_team": "Women's Away",
        "status": "UNSUPPORTED_COMPETITION",
        "reason": "Women's, youth and reserve competitions require category-matched historical results; senior-team history is not used.",
    })
    report = {
        "same_day_only": True,
        "future_fixtures_considered": 25,
        "predictions": rows,
        "historical_data_coverage": {
            "recent_cache_source_counts": {"5DollarFootballAPI": 96},
        },
    }
    result = validate_fixture_visibility(report)
    assert result["fixture_rows"] == 25
    assert result["forecast_rows"] == 1
    assert result["insufficient_history_rows"] == 23
    assert result["senior_forecast_coverage"] < 1.0



def test_category_neutral_forecasts_do_not_inflate_senior_coverage():
    report = {
        "same_day_only": True,
        "future_fixtures_considered": 2,
        "predictions": [
            {
                "home_team": "Senior A", "away_team": "Senior B",
                "status": "LOW_HISTORY_FORECAST",
                "probabilities": {"home_win": .45, "draw": .28, "away_win": .27},
                "evidence_scope": "SENIOR_COMPETITION_PRIOR",
            },
            {
                "home_team": "Youth A", "away_team": "Youth B",
                "status": "LOW_HISTORY_FORECAST",
                "probabilities": {"home_win": .45, "draw": .28, "away_win": .27},
                "evidence_scope": "CATEGORY_NEUTRAL_PRIOR",
            },
        ],
    }

    result = validate_fixture_visibility(report)

    assert result["forecast_rows"] == 2
    assert result["senior_forecast_rows"] == 1
    assert result["senior_forecast_coverage"] == 1.0


def test_fixture_visibility_rejects_any_legacy_low_data_probability_row():
    rows = [{
        "home_team": f"Home {index}",
        "away_team": f"Away {index}",
        "status": "EXPERIMENTAL_ONLY" if index == 0 else "EXPERIMENTAL_LOW_DATA",
        **({"probabilities": {"home_win": .4, "draw": .3, "away_win": .3}} if index in {0, 1} else {}),
    } for index in range(24)]
    rows.append({
        "home_team": "Women's Home",
        "away_team": "Women's Away",
        "status": "UNSUPPORTED_COMPETITION",
        "reason": "Women's, youth and reserve competitions require category-matched historical results; senior-team history is not used.",
    })
    report = {
        "same_day_only": True,
        "future_fixtures_considered": 25,
        "predictions": rows,
        "historical_data_coverage": {
            "recent_cache_source_counts": {"5DollarFootballAPI": 96},
        },
    }
    with pytest.raises(ValueError, match="unexpectedly contains probabilities"):
        validate_fixture_visibility(report)
