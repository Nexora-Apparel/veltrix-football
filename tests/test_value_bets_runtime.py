from app.value_bets_runtime import screen_fixture_value_bets


def _fixture():
    return {
        "fixture_id": "runtime-1",
        "model": "experimental_recent_goals_poisson",
        "goal_markets_model": "experimental_recent_goals_poisson",
        "home_team": "Alpha",
        "away_team": "Beta",
        "kickoff_local": "2026-10-30T18:00:00+01:00",
        "probabilities": {"home_win": 0.70, "draw": 0.18, "away_win": 0.12},
        "btts_yes": 0.64,
        "over_1_5": 0.82,
        "over_2_5": 0.61,
        "over_3_5": 0.55,
        "the_odds_api_market_odds": {
            "fetched_at": "2026-10-30T15:00:00Z",
            "commence_time": "2026-10-30T17:00:00Z",
            "markets": {
                "h2h": [{
                    "bookmaker": "Book A", "last_update": "2026-10-30T14:55:00Z",
                    "outcomes": [
                        {"name": "Alpha", "price": 1.9},
                        {"name": "Draw", "price": 3.5},
                        {"name": "Beta", "price": 4.5},
                    ],
                }],
                "btts": [{
                    "bookmaker": "Book A", "last_update": "2026-10-30T14:55:00Z",
                    "outcomes": [{"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.1}],
                }],
                "totals": [{
                    "bookmaker": "Book A", "last_update": "2026-10-30T14:55:00Z",
                    "outcomes": [
                        {"name": "Over", "point": 1.5, "price": 1.6},
                        {"name": "Under", "point": 1.5, "price": 2.6},
                        {"name": "Over", "point": 2.5, "price": 1.8},
                        {"name": "Under", "point": 2.5, "price": 2.1},
                        {"name": "Over", "point": 3.5, "price": 2.8},
                        {"name": "Under", "point": 3.5, "price": 1.4},
                    ],
                }],
            },
        },
    }


def _certificate():
    markets = ["1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"]
    return {
        "schema_version": 1, "status": "VALIDATED",
        "betting_validation": True, "approved_markets": markets,
        "alerts_enabled": True,
    }


def test_runtime_screen_covers_1x2_btts_and_all_full_time_totals_lines():
    result = screen_fixture_value_bets(_fixture(), validation_certificate=_certificate())
    assert result["status"] == "CANDIDATES_FOUND"
    assert set(result["markets"]) == {
        "1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"
    }
    assert all(result["markets"][market]["bookmaker_price_sets"] == 1 for market in result["markets"])
    assert result["candidate_count"] >= 5
    assert all(
        candidate["status"] == "CANDIDATE_NOT_GUARANTEED"
        for market in result["markets"].values()
        for candidate in market["candidates"]
    )


def test_runtime_screen_rejects_post_kickoff_or_stale_quotes():
    fixture = _fixture()
    fixture["the_odds_api_market_odds"]["fetched_at"] = "2026-10-30T18:01:00Z"
    result = screen_fixture_value_bets(fixture, validation_certificate=_certificate())
    assert result["candidate_count"] == 0
    assert all(market["bookmaker_price_sets"] == 0 for market in result["markets"].values())


def test_runtime_screen_stays_locked_without_market_specific_certificate():
    result = screen_fixture_value_bets(_fixture())
    assert result["status"] == "PAPER_ONLY_CANDIDATES"
    assert result["candidate_count"] == 0
    assert result["paper_candidate_count"] >= 1
    assert result["markets"]["1X2"]["bookmaker_price_sets"] == 1
    assert result["markets"]["1X2"]["candidates"] == []
    assert result["markets"]["1X2"]["paper_candidates"][0]["status"] == "PAPER_ONLY_NOT_APPROVED"
    assert result["markets"]["1X2"]["paper_candidates"][0]["release_status"] == "LOCKED_UNVALIDATED"



def test_runtime_1x2_screen_uses_poisson_alternative_when_elo_is_primary():
    fixture = _fixture()
    fixture["model"] = "experimental_elo_by_competition"
    fixture["probabilities"] = {"home_win": 0.99, "draw": 0.005, "away_win": 0.005}
    fixture["poisson_probabilities"] = {"home_win": 0.70, "draw": 0.18, "away_win": 0.12}
    result = screen_fixture_value_bets(fixture, validation_certificate=_certificate())
    candidate = result["markets"]["1X2"]["candidates"][0]
    assert candidate["model"] == "experimental_recent_goals_poisson"
    assert candidate["model_probability"] == 0.70


def test_runtime_1x2_screen_does_not_use_an_uncertified_model_family():
    fixture = _fixture()
    fixture["model"] = "experimental_competition_prior_poisson"
    fixture["goal_markets_model"] = "experimental_competition_prior_poisson"
    result = screen_fixture_value_bets(fixture, validation_certificate=_certificate())
    assert result["markets"]["1X2"]["candidates"] == []
    assert result["markets"]["1X2"]["status"] == "NO_QUALIFYING_VALUE"

    
def test_paper_candidates_require_prospective_goal_market_calibration():
    fixture = _fixture()
    uncalibrated = screen_fixture_value_bets(fixture)
    assert uncalibrated["markets"]["BTTS"]["paper_candidates"] == []
    assert uncalibrated["markets"]["OVER_UNDER_2_5"]["paper_candidates"] == []

    fixture["goal_market_calibration"] = {
        "status": "APPLIED_PROSPECTIVELY",
        "model_version": "goal-calibration-test",
        "markets": ["btts_yes", "over_1_5", "over_2_5", "over_3_5"],
    }
    result = screen_fixture_value_bets(fixture)
    assert result["candidate_count"] == 0
    assert result["paper_candidate_count"] >= 4
    assert result["markets"]["BTTS"]["paper_candidates"][0]["status"] == "PAPER_ONLY_NOT_APPROVED"
    assert result["model_validated"] is False
