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
             "home_key": _name_key("Alpha FC"), "away_key": f"opponent{day}",
             "home_goals": 2, "away_goals": 0},
            {"date": d, "home": f"Rival {day}", "away": "Beta FC",
             "home_key": f"rival{day}", "away_key": _name_key("Beta FC"),
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
    assert prediction["data_availability"]["live_bookmaker_odds"] == "NOT_FETCHED_IN_THIS_RUN_API_FOOTBALL_ODDS_ENRICHMENT_NOT_CONFIRMED"


def test_insufficient_team_history_suppresses_probabilities():
    fixture = _fixture()
    fixture["league"]["id"] = 39
    fixture["teams"]["home"]["name"] = "Unknown Club"
    result = predict_fixtures([fixture], _history(), as_of=date(2026, 10, 23), now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")))
    assert result[0]["status"] == "INSUFFICIENT_HISTORY"
    assert "probabilities" not in result[0]


def test_unmapped_competition_with_insufficient_history_is_classified_unsupported():
    fixture = _fixture()
    fixture["league"].pop("id", None)
    fixture["teams"]["home"]["name"] = "Unknown Club"
    result = predict_fixtures(
        [fixture], _history(), as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "UNSUPPORTED_COMPETITION"
    assert "not mapped to the historical dataset" in result[0]["reason"]
    assert "probabilities" not in result[0]


def test_history_from_prediction_date_is_not_used():
    rows = _history()
    rows.append({
        "date": date(2026, 10, 23), "home": "Alpha FC", "away": "Beta FC",
        "home_key": _name_key("Alpha FC"), "away_key": _name_key("Beta FC"),
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



def test_argentine_provider_abbreviations_match_exact_club_aliases():
    assert _name_key("Argentinos JRS") == _name_key("Argentinos Juniors")
    assert _name_key("Independ. Rivadavia") == _name_key("Independiente Rivadavia")
    assert _name_key("Atalanta BC") == _name_key("Atalanta")


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



def test_high_confidence_fuzzy_team_name_is_automatically_matched():
    fixture = _fixture()
    fixture["league"]["id"] = 39
    fixture["teams"]["home"]["name"] = "Alph FC"
    result = predict_fixtures(
        [fixture], _history(), as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "EXPERIMENTAL_ONLY"
    assert result[0]["historical_matches"]["home"] == 6
    assert result[0]["team_name_matches"]["home"]["historical_key"] == "alpha"
    assert result[0]["team_name_matches"]["home"]["auto_matched"] is True


def test_ambiguous_fuzzy_team_name_is_not_automatically_merged():
    from app.live_predictions import _resolve_team_key

    # Similar candidates are deliberately ambiguous; never pick one at random.
    resolved = _resolve_team_key("united", {"manchesterunited", "newcastleunited"})
    assert resolved == "united"


# [run-live-verification] Validate conservative team matching in the live report.
def test_fuzzy_matching_does_not_drop_a_leading_club_initial():
    from app.live_predictions import _resolve_team_key

    assert _resolve_team_key("Slask", {"lask"}) == "slask"
    assert _resolve_team_key("R. Santander", {"santander"}) == "rsantander"
    # A trailing one-character typo remains eligible for the existing high-confidence rule.
    assert _resolve_team_key("Alph", {"alpha"}) == "alpha"


# [run-live-verification] Recheck live fixture identity after squad-safety fix.
def test_short_women_and_reserve_suffixes_cannot_match_senior_sides():
    from app.live_predictions import _resolve_team_key, _team_variant_signature

    assert _team_variant_signature(_name_key("Juventus(W)")) == ("women",)
    assert _team_variant_signature(_name_key("Godoy Cruz(R)")) == ("reserve", "r")
    assert _resolve_team_key("Juventus(W)", {"juventus"}) == "juventusw"
    assert _resolve_team_key("Godoy Cruz(R)", {"godoycruz"}) == "godoycruzr"
    assert _resolve_team_key("Boca Juniors(R)", {"bocajuniors"}) == "bocajuniorsr"


def test_fuzzy_matching_never_crosses_women_youth_or_reserve_squads():
    from app.live_predictions import _resolve_team_key

    assert _resolve_team_key("Newcastle United", {"newcastleunitedwomen"}) == "newcastleunited"
    assert _resolve_team_key("FC Porto B", {"porto"}) == "portob"
    assert _resolve_team_key("Arka Gdynia U19", {"arkagdynia"}) == "arkagdyniau19"
    assert _resolve_team_key("Crystal Palace", {"crystalpalacewomen"}) == "crystalpalace"
    assert _resolve_team_key("Boca Unidos", {"bocajuniors"}) == "bocaunidos"


def test_name_normalization_preserves_accented_club_identity():
    assert _name_key("Atlético Ottawa") == "atleticoottawa"
    assert _name_key("Sporting Gijón") == "sportinggijon"
    assert _name_key("Oţelul") == "otelul"



def test_goal_estimates_prefer_relevant_home_and_away_venue_history():
    rows = []
    for day in range(1, 7):
        d = date(2026, 10, day)
        rows.append({
            "date": d, "home": "Alpha FC", "away": f"Opponent {day}",
            "home_key": _name_key("Alpha FC"), "away_key": f"opponent{day}",
            "home_goals": 3, "away_goals": 0,
        })
        rows.append({
            "date": d, "home": f"Rival {day}", "away": "Beta FC",
            "home_key": f"rival{day}", "away_key": _name_key("Beta FC"),
            "home_goals": 1, "away_goals": 1,
        })
    # Add away-only Alpha matches and home-only Beta matches. Their weaker
    # performance should not erase the relevant venue-specific signal.
    for day in range(7, 13):
        d = date(2026, 10, day)
        rows.append({
            "date": d, "home": f"Opponent Away {day}", "away": "Alpha FC",
            "home_key": f"opponentaway{day}", "away_key": "alpha",
            "home_goals": 3, "away_goals": 0,
        })
        rows.append({
            "date": d, "home": "Beta FC", "away": f"Rival Away {day}",
            "home_key": "beta", "away_key": f"rivalaway{day}",
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
    future["teams"]["home"]["name"] = "Alph FC"
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
    assert report["primary_model_counts"] == {"experimental_recent_goals_poisson": 1}
    assert report["possible_team_name_mismatches"] == 1
    assert report["poisson_alternative_available"] == 0
    assert report["elo_alternative_available"] == 1



def test_empty_history_withholds_eligible_fixtures_explicitly():
    fixture = _fixture("2026-10-23T15:00:00+01:00")
    result = predict_fixtures(
        [fixture], [], as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert len(result) == 1
    assert result[0]["status"] == "INSUFFICIENT_HISTORY"
    assert result[0]["historical_matches"] == {"home": 0, "away": 0}
    assert "No historical matches" in result[0]["reason"]
    assert "probabilities" not in result[0]


def test_empty_history_still_excludes_past_and_other_day_fixtures():
    past = _fixture("2026-10-23T11:00:00+01:00")
    tomorrow = _fixture("2026-10-24T15:00:00+01:00")
    result = predict_fixtures(
        [past, tomorrow], [], as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result == []



def test_daily_report_warns_backtest_does_not_validate_live_pipeline(tmp_path):
    import csv
    rows = _history()
    history_path = tmp_path / "history.csv"
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
    report = build_daily_report(
        {"response": [_fixture()]}, history_path,
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert "underperforms the market benchmark" in report["notice"]
    assert "No betting recommendations" in report["notice"]
    assert report["model_status"] == "EXPERIMENTAL_NOT_VALIDATED"
    assert report["normal_bets"]["status"] == "NOT_GENERATED_MODEL_NOT_VALIDATED"



def test_competition_elo_uses_only_matching_division_history():
    rows = _history()
    for row in rows:
        row["division"] = "E0"
    # Add many contradictory results in a different competition. They must not
    # alter the EPL-scoped Elo estimate for this fixture.
    for day in range(1, 7):
        d = date(2026, 10, day)
        rows.extend([
            {"date": d, "division": "SP1", "home": "Alpha FC", "away": f"Spanish Opponent {day}",
             "home_key": _name_key("Alpha FC"), "away_key": f"spanishopponent{day}",
             "home_goals": 0, "away_goals": 4},
            {"date": d, "division": "SP1", "home": f"Spanish Rival {day}", "away": "Beta FC",
             "home_key": f"spanishrival{day}", "away_key": _name_key("Beta FC"),
             "home_goals": 4, "away_goals": 0},
        ])
    fixture = _fixture()
    fixture["league"]["id"] = 39
    result = predict_fixtures(
        [fixture], rows, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    prediction = result[0]
    assert prediction["model"] == "experimental_elo_by_competition"
    assert prediction["elo_history"]["scope"] == "COMPETITION"
    assert prediction["elo_history"]["division_code"] == "E0"
    assert prediction["elo_history"]["home_prior_matches"] == 6
    assert prediction["elo_history"]["away_prior_matches"] == 6
    assert set(prediction["probabilities"]) == {"home_win", "draw", "away_win"}
    assert abs(sum(prediction["probabilities"].values()) - 1) < 0.0002
    assert set(prediction["poisson_probabilities"]) == {"home_win", "draw", "away_win"}

def test_daily_report_includes_refreshed_completed_results_but_excludes_target_day():
    from app.live_predictions import build_daily_report

    base = [{
        "date": date(2026, 10, 20), "division": "E0",
        "home": "Old FC", "away": "Older FC",
        "home_key": "oldfc", "away_key": "olderfc",
        "home_goals": 1, "away_goals": 0,
    }]
    refreshed = [
        {
            "date": date(2026, 10, 22), "division": "E0",
            "home": "Recent FC", "away": "Visitor FC",
            "home_key": "recentfc", "away_key": "visitorfc",
            "home_goals": 2, "away_goals": 1,
        },
        {
            "date": date(2026, 10, 23), "division": "E0",
            "home": "Same Day FC", "away": "Same Day Visitor",
            "home_key": "samedayfc", "away_key": "samedayvisitor",
            "home_goals": 9, "away_goals": 0,
        },
    ]

    report = build_daily_report(
        {"response": []},
        "unused.csv",
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
        base_historical_matches=base,
        additional_historical_matches=refreshed,
    )

    assert report["historical_matches_available"] == 2
    assert report["historical_data_through"] == "2026-10-22"



def test_football_data_club_suffixes_and_prefixes_match_historical_names():
    assert _name_key("Liverpool FC") == _name_key("Liverpool")
    assert _name_key("AFC Bournemouth") == _name_key("Bournemouth")
    assert _name_key("EC Bahia") == _name_key("Bahia")
    assert _name_key("FC Internazionale Milano") == _name_key("Inter")
    assert _name_key("Athletic Club") == _name_key("Ath Bilbao")
    assert _name_key("SBV Excelsior") == _name_key("Excelsior")



def test_provider_local_league_ids_never_map_to_api_football_divisions():
    from app.live_predictions import _fixture_parts

    fixture = _fixture()
    fixture["league"]["id"] = 128  # API-Football's Argentina league ID
    fixture["_veltrix_source"] = "5DollarFootballAPI"
    parts = _fixture_parts(fixture)
    assert parts is not None
    assert parts["division_code"] is None

    # Legacy/API-Football-shaped fixtures retain the existing ID mapping.
    api_fixture = _fixture()
    api_fixture["league"]["id"] = 128
    api_parts = _fixture_parts(api_fixture)
    assert api_parts is not None
    assert api_parts["division_code"] == "ARG"



def test_explicit_historical_division_code_maps_without_numeric_id():
    from app.live_predictions import _fixture_parts

    fixture = _fixture()
    fixture["league"]["code"] = "SWE"
    fixture["league"].pop("id", None)
    parts = _fixture_parts(fixture)
    assert parts is not None
    assert parts["division_code"] == "SWE"
    assert _fixture_parts({
        **fixture,
        "league": {"name": "Brazil Serie A", "code": "BSA"},
    })["division_code"] == "BRA"

def test_non_senior_competitions_cannot_borrow_senior_historical_divisions():
    from app.live_predictions import _fixture_parts

    womens_fixture = _fixture()
    womens_fixture["league"] = {"name": "Swedish Women's League", "code": "SWE"}
    assert _fixture_parts(womens_fixture)["division_code"] is None

    # Even when team names have enough senior historical matches, category
    # mismatch must withhold the prediction instead of falling back globally.
    predictions = predict_fixtures(
        [womens_fixture],
        _history(),
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert predictions[0]["status"] == "UNSUPPORTED_COMPETITION"
    assert "category-matched historical results" in predictions[0]["reason"]
    assert "probabilities" not in predictions[0]

    youth_fixture = _fixture()
    youth_fixture["league"] = {"name": "U21 League", "id": 39}
    assert _fixture_parts(youth_fixture)["division_code"] is None

    reserve_fixture = _fixture()
    reserve_fixture["league"] = {"name": "Argentina Reserve League", "id": 128}
    assert _fixture_parts(reserve_fixture)["division_code"] is None

    for compact_label in ("BraCU20", "U-20 League", "EngNLW", "Arg(R)", "Col B"):
        compact_fixture = _fixture()
        compact_fixture["league"] = {"name": compact_label, "code": "SWE"}
        assert _fixture_parts(compact_fixture)["division_code"] is None, compact_label

    # Ordinary senior second divisions must not be blocked just because their
    # competition names contain a letter/number commonly used by reserves.
    senior_fixture = _fixture()
    senior_fixture["league"] = {"name": "English League One", "code": "EL1"}
    assert _fixture_parts(senior_fixture)["division_code"] == "E2"

