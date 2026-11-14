from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.live_predictions import _name_key, build_daily_report, predict_fixtures


def _history():
    rows = []
    # Each team has six completed matches before the prediction date.
    for day in range(1, 7):
        d = date(2026, 10, day)
        rows.extend([
            {"date": d, "division": "E0", "home": "Alpha FC", "away": f"Opponent {day}",
             "home_key": _name_key("Alpha FC"), "away_key": f"opponent{day}",
             "home_goals": 2, "away_goals": 0},
            {"date": d, "division": "E0", "home": f"Rival {day}", "away": "Beta FC",
             "home_key": f"rival{day}", "away_key": _name_key("Beta FC"),
             "home_goals": 1, "away_goals": 1},
        ])
    return rows


def _fixture(kickoff="2026-10-23T15:00:00+01:00"):
    return {
        "fixture": {"id": 123, "date": kickoff, "status": {"short": "NS"}},
        "teams": {"home": {"name": "Alpha FC"}, "away": {"name": "Beta FC"}},
        "league": {"name": "Test League", "code": "PL"},
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
    dc_shadow = prediction["poisson_dc_shadow"]
    assert dc_shadow["status"] == "SHADOW_RESEARCH"
    dc_markets = dc_shadow["markets"]
    assert abs(sum(dc_markets["1x2"].values()) - 1.0) < 1e-10
    assert abs(sum(dc_markets["btts"].values()) - 1.0) < 1e-10
    for totals in dc_markets["totals"].values():
        assert abs(sum(totals.values()) - 1.0) < 1e-10
    assert prediction["recent_form"]["home_team"]["overall"]["last_5"]["matches"] == 5
    assert prediction["recent_form"]["home_team"]["home_venue"]["last_10"]["matches"] == 6
    assert prediction["recent_form"]["away_team"]["overall"]["last_5"]["matches"] == 5
    assert prediction["recent_form"]["away_team"]["away_venue"]["last_10"]["matches"] == 6
    assert prediction["recent_form"]["as_of"] == "2026-10-23"
    assert prediction["data_availability"]["live_bookmaker_odds"] == "NOT_FETCHED_IN_THIS_RUN_API_FOOTBALL_ODDS_ENRICHMENT_NOT_CONFIRMED"


def test_sparse_team_history_uses_adaptive_forecast_with_low_evidence():
    fixture = _fixture()
    fixture["league"]["id"] = 39
    fixture["teams"]["home"]["name"] = "Unknown Club"
    result = predict_fixtures([fixture], _history(), as_of=date(2026, 10, 23), now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")))
    assert result[0]["status"] == "LOW_HISTORY_FORECAST"
    assert result[0]["probabilities"]
    assert result[0]["historical_matches"] == {"home": 0, "away": 6}
    assert result[0]["evidence_grade"] in {"LOW", "MODERATE"}
    assert result[0]["value_bet_screen"]["status"] == "NOT_ELIGIBLE_LOW_EVIDENCE"
    diagnostics = result[0]["team_history_diagnostics"]
    assert diagnostics["home"]["fixture_name"] == "Unknown Club"
    assert diagnostics["home"]["history_match_found"] is False
    assert diagnostics["home"].get("match_status") in {None, "NO_HISTORY_MATCH"}
    assert diagnostics["away"]["prior_matches"] == 6


def test_unmapped_competition_uses_global_prior_without_cross_competition_team_matching():
    fixture = _fixture()
    fixture["league"].pop("id", None)
    fixture["league"].pop("code", None)
    fixture["teams"]["home"]["name"] = "Unknown Club"
    result = predict_fixtures(
        [fixture], _history(), as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "LOW_HISTORY_FORECAST"
    assert result[0]["probabilities"]
    assert result[0]["historical_matches"] == {"home": 0, "away": 0}
    assert result[0]["data_availability"]["fallback_prior"] == "GLOBAL"



def test_team_history_and_baselines_are_isolated_by_competition():
    fixture = _fixture()
    base = _history()
    other_division = [
        {
            "date": date(2026, 10, day), "division": "F1",
            "home": f"French Home {day}", "away": f"French Away {day}",
            "home_key": f"frenchhome{day}", "away_key": f"frenchaway{day}",
            "home_goals": 8, "away_goals": 7,
        }
        for day in range(1, 7)
    ]
    baseline = predict_fixtures(
        [fixture], base, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )[0]
    with_other_league = predict_fixtures(
        [fixture], base + other_division, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )[0]
    assert baseline["status"] == "EXPERIMENTAL_ONLY"
    assert with_other_league["status"] == "EXPERIMENTAL_ONLY"
    assert with_other_league["historical_matches"] == baseline["historical_matches"]
    assert with_other_league["expected_goals"] == baseline["expected_goals"]


def test_unmapped_competition_uses_global_rates_but_never_borrows_team_history():
    fixture = _fixture()
    fixture["league"].pop("code", None)
    result = predict_fixtures(
        [fixture], _history(), as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )[0]
    assert result["status"] == "LOW_HISTORY_FORECAST"
    assert result["historical_matches"] == {"home": 0, "away": 0}
    assert result["probabilities"]
    assert result["data_availability"]["fallback_prior"] == "GLOBAL"

def test_history_from_prediction_date_is_not_used():
    rows = _history()
    rows.append({
        "date": date(2026, 10, 23), "division": "E0", "home": "Alpha FC", "away": "Beta FC",
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


def test_past_kickoffs_remain_visible_without_pre_match_forecasts():
    past = _fixture("2026-10-23T11:00:00+01:00")
    past["fixture"]["id"] = 100
    future = _fixture("2026-10-23T15:00:00+01:00")
    future["fixture"]["id"] = 200
    result = predict_fixtures(
        [past, future], _history(), as_of=date(2026, 10, 23),
        timezone_name="Africa/Lagos",
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert [item["fixture_id"] for item in result] == [100, 200]
    assert result[0]["status"] == "KICKOFF_PASSED"
    assert "probabilities" not in result[0]
    assert result[1]["kickoff_local"].startswith("2026-10-23T15:00:00")



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
            {"date": d, "division": "E0", "home": "Manchester United", "away": f"Opponent {day}",
             "home_key": _name_key("Manchester United"), "away_key": _name_key(f"Opponent {day}"),
             "home_goals": 2, "away_goals": 0},
            {"date": d, "division": "E0", "home": f"Rival {day}", "away": "Beta FC",
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
            "date": d, "division": "E0", "home": "Alpha FC", "away": f"Opponent {day}",
            "home_key": _name_key("Alpha FC"), "away_key": f"opponent{day}",
            "home_goals": 3, "away_goals": 0,
        })
        rows.append({
            "date": d, "division": "E0", "home": f"Rival {day}", "away": "Beta FC",
            "home_key": f"rival{day}", "away_key": _name_key("Beta FC"),
            "home_goals": 1, "away_goals": 1,
        })
    # Add away-only Alpha matches and home-only Beta matches. Their weaker
    # performance should not erase the relevant venue-specific signal.
    for day in range(7, 13):
        d = date(2026, 10, day)
        rows.append({
            "date": d, "division": "E0", "home": f"Opponent Away {day}", "away": "Alpha FC",
            "home_key": f"opponentaway{day}", "away_key": "alpha",
            "home_goals": 3, "away_goals": 0,
        })
        rows.append({
            "date": d, "division": "E0", "home": "Beta FC", "away": f"Rival Away {day}",
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
            handle, fieldnames=["match_date", "division", "home_team", "away_team", "home_goals", "away_goals"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "match_date": row["date"].isoformat(),
                "division": row.get("division", "E0"),
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
    assert report["same_day_pre_match_fixtures"] == 1
    assert report["past_kickoffs_excluded"] == 1
    assert report["past_kickoffs_retained"] == 1
    assert report["future_fixtures_considered"] == 1
    assert report["same_day_fixtures_retained"] == 3
    assert report["fixtures_excluded_other_date_or_status"] == 1
    assert len(report["predictions"]) == 3
    assert report["predictions"][0]["fixture_id"] == 100
    assert report["predictions"][0]["status"] == "KICKOFF_PASSED"
    assert "probabilities" not in report["predictions"][0]
    by_fixture = {row["fixture_id"]: row for row in report["predictions"]}
    assert by_fixture[200]["status"] == "EXPERIMENTAL_ONLY"
    assert by_fixture[400]["status"] == "FIXTURE_NOT_PREMATCH"
    assert "probabilities" not in by_fixture[400]
    assert report["primary_model_counts"] == {"experimental_elo_by_competition": 1}
    assert report["possible_team_name_mismatches"] == 1
    assert len(report["team_history_match_diagnostics"]) == 1
    assert report["team_history_match_diagnostics"][0]["historical_matches"] == {"home": 6, "away": 6}
    assert report["teams_below_history_minimum"] == 0
    assert report["poisson_alternative_available"] == 1
    assert report["elo_alternative_available"] == 0



def test_empty_history_generates_conservative_neutral_prior_forecast():
    fixture = _fixture("2026-10-23T15:00:00+01:00")
    result = predict_fixtures(
        [fixture], [], as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert len(result) == 1
    assert result[0]["status"] == "LOW_HISTORY_FORECAST"
    assert result[0]["historical_matches"] == {"home": 0, "away": 0}
    assert result[0]["probabilities"]
    assert result[0]["evidence_grade"] == "VERY_LOW"
    assert result[0]["value_bet_screen"]["status"] == "NOT_ELIGIBLE_LOW_EVIDENCE"



def test_daily_report_counts_adaptive_low_history_forecasts_correctly(tmp_path):
    history_path = tmp_path / "missing-history.csv"
    history_path.write_text("match_date,home_team,away_team,home_goals,away_goals\n", encoding="utf-8")
    report = build_daily_report(
        {"response": [_fixture("2026-10-23T15:00:00+01:00")]},
        history_path,
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
        market_odds_by_fixture={123: {
            "model": "market_consensus",
            "probabilities": {"home": 0.4, "draw": 0.3, "away": 0.3},
            "bookmakers_count": 3,
        }},
    )

    assert report["fixture_status_counts"]["LOW_HISTORY_FORECAST"] == 1
    assert report["predictions"][0]["market_probabilities"] == {"home": 0.4, "draw": 0.3, "away": 0.3}
    assert report["predictions_created"] == 1
    assert report["low_history_forecasts"] == 1
    assert report["forecast_coverage"]["forecast_rows"] == 1
    assert report["forecast_coverage"]["coverage_rate"] == 1.0
    assert report["model_status"] == "EVIDENCE_WEIGHTED_NOT_CERTIFIED"
    assert "experimental" not in report["notice"].lower()


def test_empty_history_retains_past_fixture_and_excludes_other_day_fixture():
    past = _fixture("2026-10-23T11:00:00+01:00")
    tomorrow = _fixture("2026-10-24T15:00:00+01:00")
    result = predict_fixtures(
        [past, tomorrow], [], as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert len(result) == 1
    assert result[0]["status"] == "KICKOFF_PASSED"
    assert "probabilities" not in result[0]



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
    assert "has not certified the model for betting" in report["notice"]
    assert "value-bet alerts remain locked" in report["notice"]
    assert report["model_status"] == "EVIDENCE_WEIGHTED_NOT_CERTIFIED"
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
    fixture["league"].pop("code", None)
    fixture["league"]["id"] = 128  # API-Football's Argentina league ID
    fixture["_veltrix_source"] = "5DollarFootballAPI"
    parts = _fixture_parts(fixture)
    assert parts is not None
    assert parts["division_code"] is None

    # Legacy/API-Football-shaped fixtures retain the existing ID mapping.
    api_fixture = _fixture()
    api_fixture["league"].pop("code", None)
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

    # Even when team names have senior historical matches, never borrow those
    # results for a women's competition; use only a neutral category prior.
    predictions = predict_fixtures(
        [womens_fixture],
        _history(),
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert predictions[0]["status"] == "LOW_HISTORY_FORECAST"
    assert predictions[0]["probabilities"]
    assert predictions[0]["evidence_scope"] == "CATEGORY_NEUTRAL_PRIOR"

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




def test_non_senior_competition_uses_neutral_prior_when_category_history_is_empty():
    fixture = _fixture()
    fixture["league"]["name"] = "England Women's League"
    result = predict_fixtures(
        [fixture], [], as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "LOW_HISTORY_FORECAST"
    assert result[0]["probabilities"]
    assert result[0]["evidence_scope"] == "CATEGORY_NEUTRAL_PRIOR"


def test_senior_competition_with_empty_history_uses_neutral_prior():
    fixture = _fixture()
    result = predict_fixtures(
        [fixture], [], as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    assert result[0]["status"] == "LOW_HISTORY_FORECAST"
    assert result[0]["probabilities"]
    assert result[0]["evidence_grade"] == "VERY_LOW"
    assert result[0]["historical_matches"] == {"home": 0, "away": 0}


def test_french_ligue_one_provider_aliases_match_historical_team_keys():
    from app.live_predictions import _name_key
    assert _name_key("LOSC Lille") == _name_key("Lille")
    assert _name_key("RC Lens") == _name_key("Lens")


def test_mapped_competition_prior_is_not_published_when_team_history_is_sparse():
    fixture = _fixture("2026-10-23T15:00:00+01:00")
    fixture["league"] = {"name": "Bundesliga", "code": "BL1"}
    fixture["teams"]["home"]["name"] = "Newly Promoted Club"
    fixture["teams"]["away"]["name"] = "Unfamiliar Opponent"
    history = []
    for index in range(50):
        history.append({
            "date": date(2026, 8, 1 + (index % 20)),
            "home": f"League Home {index}",
            "away": f"League Away {index}",
            "home_key": f"leaguehome{index}",
            "away_key": f"leagueaway{index}",
            "home_goals": 2 if index % 2 == 0 else 1,
            "away_goals": 1 if index % 3 == 0 else 0,
            "division": "D1",
        })
    result = predict_fixtures(
        [fixture], history, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    prediction = result[0]
    assert prediction["status"] == "LOW_HISTORY_FORECAST"
    assert prediction["data_availability"]["competition_specific_history"] == "AVAILABLE"
    assert prediction["data_availability"]["fallback_prior"] == "COMPETITION"
    assert prediction["probabilities"]
    assert "btts_yes" in prediction
    assert "over_2_5" in prediction


def test_build_daily_report_retains_scheduled_fixture_without_kickoff():
    fixture = _fixture(None)
    report = build_daily_report(
        {"response": [fixture]}, "unused.csv",
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 8, 0, tzinfo=ZoneInfo("Africa/Lagos")),
        base_historical_matches=_history(),
    )
    assert len(report["predictions"]) == 1
    row = report["predictions"][0]
    assert row["fixture_id"] == 123
    assert row["status"] == "KICKOFF_UNVERIFIED"
    assert report["kickoff_unverified_fixtures"] == 1
    assert report["future_fixtures_considered"] == 1
    assert "probabilities" not in row


def test_common_fixture_aliases_normalize_for_cross_provider_deduplication():
    assert _name_key("Newcastle United") == _name_key("Newcastle")
    assert _name_key("Deportivo La Coruña") == _name_key("Deportivo A Coruna")
    assert _name_key("CA Osasuna") == _name_key("Osasuna")


def test_started_fixture_parts_can_be_read_for_visibility_only():
    from app.live_predictions import _fixture_parts
    fixture = _fixture("2026-10-23T11:00:00+01:00")
    fixture["fixture"]["status"]["short"] = "FT"
    assert _fixture_parts(fixture) is None
    parts = _fixture_parts(fixture, include_started=True)
    assert parts["fixture_status"] == "FT"


def test_unmapped_senior_fixture_with_global_history_is_withheld_without_team_evidence():
    fixture = _fixture()
    fixture["league"] = {"name": "Unmapped Senior Competition"}
    fixture["teams"]["home"]["name"] = "Unknown Home"
    fixture["teams"]["away"]["name"] = "Unknown Away"
    history = []
    for index in range(40):
        history.append({
            "date": date(2026, 8, 1) + __import__("datetime").timedelta(days=index),
            "home": f"Historical Home {index}",
            "away": f"Historical Away {index}",
            "home_key": f"historicalhome{index}",
            "away_key": f"historicalaway{index}",
            "home_goals": 1 + index % 2,
            "away_goals": index % 2,
            "division": "",
            "source_provider": "5DollarFootballAPI",
        })
    result = predict_fixtures(
        [fixture], history, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )
    prediction = result[0]
    assert prediction["status"] == "LOW_HISTORY_FORECAST"
    assert prediction["data_availability"]["fallback_prior"] == "GLOBAL"
    assert prediction["probabilities"]
    assert "btts_yes" in prediction
    assert "over_2_5" in prediction


def test_one_match_history_is_used_with_strong_shrinkage():
    rows = [{
        "date": date(2026, 10, 1), "division": "E0",
        "home": "Alpha FC", "away": "Opponent",
        "home_key": _name_key("Alpha FC"), "away_key": _name_key("Opponent"),
        "home_goals": 4, "away_goals": 0,
    }]
    fixture = _fixture()
    fixture["teams"]["away"]["name"] = "New Club"
    result = predict_fixtures(
        [fixture], rows, as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
    )[0]
    assert result["status"] == "LOW_HISTORY_FORECAST"
    assert result["historical_matches"] == {"home": 1, "away": 0}
    assert result["probabilities"]
    assert result["evidence_grade"] == "LOW"
    assert "One team has no matched history" in result["prediction_basis"]


def test_swapping_fixture_sides_swaps_forecast_without_home_preference():
    fixture = _fixture()
    fixture["league"]["id"] = 39
    reversed_fixture = _fixture()
    reversed_fixture["league"]["id"] = 39
    reversed_fixture["teams"] = {
        "home": fixture["teams"]["away"],
        "away": fixture["teams"]["home"],
    }
    now = datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    forward = predict_fixtures([fixture], _history(), as_of=date(2026, 10, 23), now=now)[0]
    reverse = predict_fixtures([reversed_fixture], _history(), as_of=date(2026, 10, 23), now=now)[0]

    assert abs(forward["expected_goals"]["home"] - reverse["expected_goals"]["away"]) < 1e-9
    assert abs(forward["expected_goals"]["away"] - reverse["expected_goals"]["home"]) < 1e-9
    assert abs(forward["probabilities"]["home_win"] - reverse["probabilities"]["away_win"]) < 1e-4
    assert abs(forward["probabilities"]["away_win"] - reverse["probabilities"]["home_win"]) < 1e-4
    assert abs(forward["probabilities"]["draw"] - reverse["probabilities"]["draw"]) < 1e-4
    assert forward["btts_yes"] == reverse["btts_yes"]
    assert forward["over_2_5"] == reverse["over_2_5"]


def test_sparse_history_is_symmetric_when_fixture_sides_are_swapped():
    fixture = _fixture()
    fixture["league"]["id"] = 39
    fixture["teams"]["home"]["name"] = "Unknown Club"
    reversed_fixture = _fixture()
    reversed_fixture["league"]["id"] = 39
    reversed_fixture["teams"] = {
        "home": fixture["teams"]["away"],
        "away": fixture["teams"]["home"],
    }
    now = datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    forward = predict_fixtures([fixture], _history(), as_of=date(2026, 10, 23), now=now)[0]
    reverse = predict_fixtures([reversed_fixture], _history(), as_of=date(2026, 10, 23), now=now)[0]

    assert forward["status"] == reverse["status"] == "LOW_HISTORY_FORECAST"
    assert abs(forward["expected_goals"]["home"] - reverse["expected_goals"]["away"]) < 1e-9
    assert abs(forward["expected_goals"]["away"] - reverse["expected_goals"]["home"]) < 1e-9
    assert abs(forward["probabilities"]["home_win"] - reverse["probabilities"]["away_win"]) < 1e-4
    assert abs(forward["probabilities"]["away_win"] - reverse["probabilities"]["home_win"]) < 1e-4
    assert abs(forward["probabilities"]["draw"] - reverse["probabilities"]["draw"]) < 1e-4

def test_strict_publication_withholds_identical_generic_fallbacks_for_distinct_fixtures():
    from app.live_predictions import build_daily_report

    first = _fixture("2026-10-23T15:00:00+01:00")
    first["fixture"]["id"] = 123
    first["teams"]["home"]["name"] = "Unseen Iraq Club"
    first["teams"]["away"]["name"] = "Unseen Iraq Opponent"
    first["league"] = {"name": "Iraq Premier League", "code": "PL"}

    second = _fixture("2026-10-23T16:00:00+01:00")
    second["fixture"]["id"] = 456
    second["teams"]["home"]["name"] = "Unseen Israel Women"
    second["teams"]["away"]["name"] = "Unseen Israel Women Opponent"
    second["league"] = {"name": "Israel Women's League", "code": "PL"}

    report = build_daily_report(
        {"response": [first, second]},
        "unused.csv",
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
        base_historical_matches=[],
        additional_historical_matches=[],
        strict_publication=True,
    )

    assert len(report["predictions"]) == 2
    by_id = {row["fixture_id"]: row for row in report["predictions"]}
    assert set(by_id) == {123, 456}
    for row in by_id.values():
        assert row["status"] in {"INSUFFICIENT_HISTORY", "UNSUPPORTED_COMPETITION"}
        assert row["historical_matches"] == {"home": 0, "away": 0}
        for field in (
            "probabilities", "market_probabilities", "expected_goals",
            "btts_yes", "over_1_5", "over_2_5", "over_3_5",
            "most_likely_scorelines", "poisson_probabilities",
            "elo_probabilities", "poisson_dc_shadow",
        ):
            assert field not in row
        assert row["betting_recommendation"] is False

    # The distinct fixtures must not expose the same generic probability vector.
    assert all("probabilities" not in row for row in by_id.values())

