from datetime import date

from app.live_predictions import predict_fixtures


def _history():
    rows = []
    # Each team has six completed matches before the prediction date.
    for day in range(1, 7):
        d = date(2026, 10, day)
        rows.extend([
            {"date": d, "home": "Alpha FC", "away": f"Opponent {day}",
             "home_key": "alphafc", "away_key": f"opponent{day}",
             "home_goals": 2, "away_goals": 0},
            {"date": d, "home": f"Rival {day}", "away": "Beta FC",
             "home_key": f"rival{day}", "away_key": "betafc",
             "home_goals": 1, "away_goals": 1},
        ])
    return rows


def _fixture(kickoff="2026-10-23T15:00:00+01:00"):
    return {
        "fixture": {"id": 123, "date": kickoff, "status": {"short": "NS"}},
        "teams": {"home": {"name": "Alpha FC"}, "away": {"name": "Beta FC"}},
        "league": {"name": "Test League"},
    }


def test_prediction_uses_minimum_history_and_never_claims_validated():
    result = predict_fixtures([_fixture()], _history(), as_of=date(2026, 10, 23))
    assert len(result) == 1
    prediction = result[0]
    assert prediction["status"] == "EXPERIMENTAL_ONLY"
    assert prediction["model_validated"] is False
    assert prediction["betting_recommendation"] is False
    assert abs(sum(prediction["probabilities"].values()) - 1) < 0.0002
    assert prediction["expected_goals"]["home"] > 0
    assert prediction["expected_goals"]["away"] > 0


def test_insufficient_team_history_suppresses_probabilities():
    fixture = _fixture()
    fixture["teams"]["home"]["name"] = "Unknown Club"
    result = predict_fixtures([fixture], _history(), as_of=date(2026, 10, 23))
    assert result[0]["status"] == "INSUFFICIENT_HISTORY"
    assert "probabilities" not in result[0]


def test_history_from_prediction_date_is_not_used():
    rows = _history()
    rows.append({
        "date": date(2026, 10, 23), "home": "Alpha FC", "away": "Beta FC",
        "home_key": "alphafc", "away_key": "betafc",
        "home_goals": 8, "away_goals": 0,
    })
    result = predict_fixtures([_fixture()], rows, as_of=date(2026, 10, 23))
    assert result[0]["status"] == "EXPERIMENTAL_ONLY"
    assert result[0]["historical_matches"] == {"home": 6, "away": 6}


def test_only_fixtures_on_target_nigeria_day_are_included():
    same_day = _fixture("2026-10-23T15:00:00+01:00")
    tomorrow = _fixture("2026-10-24T00:30:00+01:00")
    tomorrow["fixture"]["id"] = 456
    result = predict_fixtures(
        [same_day, tomorrow], _history(), as_of=date(2026, 10, 23),
        timezone_name="Africa/Lagos",
    )
    assert [item["fixture_id"] for item in result] == [123]
    assert result[0]["kickoff_local"].startswith("2026-10-23")


def test_utc_kickoff_is_converted_to_nigeria_calendar_date():
    fixture = _fixture("2026-10-22T23:30:00Z")
    result = predict_fixtures(
        [fixture], _history(), as_of=date(2026, 10, 23),
        timezone_name="Africa/Lagos",
    )
    assert len(result) == 1
    assert result[0]["kickoff_local"].startswith("2026-10-23")
