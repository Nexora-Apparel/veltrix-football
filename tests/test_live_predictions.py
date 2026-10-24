from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.live_predictions import _name_key, build_daily_report, predict_fixtures


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
    result = predict_fixtures([_fixture()], _history(), as_of=date(2026, 10, 23), now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")))
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
    result = predict_fixtures([fixture], _history(), as_of=date(2026, 10, 23), now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")))
    assert result[0]["status"] == "INSUFFICIENT_HISTORY"
    assert "probabilities" not in result[0]


def test_history_from_prediction_date_is_not_used():
    rows = _history()
    rows.append({
        "date": date(2026, 10, 23), "home": "Alpha FC", "away": "Beta FC",
        "home_key": "alphafc", "away_key": "betafc",
        "home_goals": 8, "away_goals": 0,
    })
    result = predict_fixtures([_fixture()], rows, as_of=date(2026, 10, 23), now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")))
    assert result[0]["status"] == "EXPERIMENTAL_ONLY"
    assert result[0]["historical_matches"] == {"home": 6, "away": 6}


def test_only_fixtures_on_target_nigeria_day_are_included():
    same_day = _fixture("2026-10-23T15:00:00+01:00")
    tomorrow = _fixture("2026-10-24T00:30:00+01:00")
    tomorrow["fixture"]["id"] = 456
    result = predict_fixtures(
        [same_day, tomorrow], _history(), as_of=date(2026, 10, 23),
        timezone_name="Africa/Lagos",
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert [item["fixture_id"] for item in result] == [123]
    assert result[0]["kickoff_local"].startswith("2026-10-23")


def test_utc_kickoff_is_converted_to_nigeria_calendar_date():
    fixture = _fixture("2026-10-22T23:30:00Z")
    result = predict_fixtures(
        [fixture], _history(), as_of=date(2026, 10, 23),
        timezone_name="Africa/Lagos",
        now=datetime(2026, 10, 23, 0, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert len(result) == 1
    assert result[0]["kickoff_local"].startswith("2026-10-23")


def test_past_kickoffs_are_excluded_from_pre_match_report():
    past = _fixture("2026-10-23T11:00:00+01:00")
    past["fixture"]["id"] = 100
    future = _fixture("2026-10-23T15:00:00+01:00")
    future["fixture"]["id"] = 200
    result = predict_fixtures(
        [past, future], _history(), as_of=date(2026, 10, 23),
        timezone_name="Africa/Lagos",
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert [item["fixture_id"] for item in result] == [200]
    assert result[0]["kickoff_local"].startswith("2026-10-23T15:00:00")



def test_known_team_aliases_match_without_fuzzy_guessing():
    assert _name_key("Man Utd") == _name_key("Manchester United")
    assert _name_key("Spurs") == _name_key("Tottenham Hotspur")
    assert _name_key("Paris SG") == _name_key("PSG")
    assert _name_key("Unknown Athletic") == "unknownathletic"


def test_aliases_allow_known_fixture_name_variant_to_use_history():
    rows = _history()
    # Simulate source data spelling out Manchester United while the fixture API
    # abbreviates it as Man Utd. Keys are produced by the same normalizer used
    # by the real historical CSV loader.
    rows = []
    for day in range(1, 7):
        d = date(2026, 10, day)
        rows.extend([
            {"date": d, "home": "Manchester United", "away": f"Opponent {day}",
             "home_key": _name_key("Manchester United"), "away_key": _name_key(f"Opponent {day}"),
             "home_goals": 2, "away_goals": 0},
            {"date": d, "home": f"Rival {day}", "away": "Beta FC",
             "home_key": _name_key(f"Rival {day}"), "away_key": _name_key("Beta FC"),
             "home_goals": 1, "away_goals": 1},
        ])
    fixture = _fixture()
    fixture["teams"]["home"]["name"] = "Man Utd"
    result = predict_fixtures(
        [fixture], rows, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "EXPERIMENTAL_ONLY"
    assert result[0]["historical_matches"]["home"] == 6



def test_fuzzy_name_matches_are_suggestions_only_not_automatic_predictions():
    fixture = _fixture()
    fixture["teams"]["home"]["name"] = "Alph FC"
    result = predict_fixtures(
        [fixture], _history(), as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "INSUFFICIENT_HISTORY"
    assert "probabilities" not in result[0]
    assert "Alpha FC" in result[0]["team_name_match_suggestions"]["home"]



def test_goal_estimates_prefer_relevant_home_and_away_venue_history():
    rows = []
    for day in range(1, 7):
        d = date(2026, 10, day)
        rows.append({
            "date": d, "home": "Alpha FC", "away": f"Opponent {day}",
            "home_key": "alphafc", "away_key": f"opponent{day}",
            "home_goals": 3, "away_goals": 0,
        })
        rows.append({
            "date": d, "home": f"Rival {day}", "away": "Beta FC",
            "home_key": f"rival{day}", "away_key": "betafc",
            "home_goals": 1, "away_goals": 1,
        })
    # Add away-only Alpha matches and home-only Beta matches. Their weaker
    # performance should not erase the relevant venue-specific signal.
    for day in range(7, 13):
        d = date(2026, 10, day)
        rows.append({
            "date": d, "home": f"Opponent Away {day}", "away": "Alpha FC",
            "home_key": f"opponentaway{day}", "away_key": "alphafc",
            "home_goals": 3, "away_goals": 0,
        })
        rows.append({
            "date": d, "home": "Beta FC", "away": f"Rival Away {day}",
            "home_key": "betafc", "away_key": f"rivalaway{day}",
            "home_goals": 0, "away_goals": 2,
        })
    result = predict_fixtures(
        [_fixture()], rows, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "EXPERIMENTAL_ONLY"
    assert result[0]["expected_goals"]["home"] > result[0]["expected_goals"]["away"]



def test_zero_goal_history_keeps_estimates_finite():
    rows = _history()
    for row in rows:
        row["home_goals"] = 0
        row["away_goals"] = 0
    result = predict_fixtures(
        [_fixture()], rows, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    prediction = result[0]
    assert prediction["status"] == "EXPERIMENTAL_ONLY"
    assert prediction["expected_goals"]["home"] > 0
    assert prediction["expected_goals"]["away"] > 0
    assert all(0 <= p <= 1 for p in prediction["probabilities"].values())



def test_daily_report_explains_fixture_filtering(tmp_path):
    history_path = tmp_path / "history.csv"
    import csv
    rows = _history()
    with history_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["match_date", "home_team", "away_team", "home_goals", "away_goals"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "match_date": row["date"].isoformat(),
                "home_team": row["home"],
                "away_team": row["away"],
                "home_goals": row["home_goals"],
                "away_goals": row["away_goals"],
            })
    past = _fixture("2026-10-23T11:00:00+01:00")
    past["fixture"]["id"] = 100
    future = _fixture("2026-10-23T15:00:00+01:00")
    future["fixture"]["id"] = 200
    tomorrow = _fixture("2026-10-24T15:00:00+01:00")
    tomorrow["fixture"]["id"] = 300
    finished = _fixture("2026-10-23T16:00:00+01:00")
    finished["fixture"]["id"] = 400
    finished["fixture"]["status"]["short"] = "FT"
    report = build_daily_report(
        {"response": [past, future, tomorrow, finished]},
        history_path,
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert report["fixtures_received"] == 4
    assert report["same_day_pre_match_fixtures"] == 2
    assert report["past_kickoffs_excluded"] == 1
    assert report["future_fixtures_considered"] == 1
    assert report["fixtures_excluded_other_date_or_status"] == 2
    assert len(report["predictions"]) == 1
    assert report["predictions"][0]["fixture_id"] == 200
