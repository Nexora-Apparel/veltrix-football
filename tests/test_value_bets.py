import pytest

from app.value_bets import devig_probabilities, screen_value_bets


def test_devig_removes_proportional_margin():
    probabilities = devig_probabilities({"home": 2.0, "draw": 3.5, "away": 4.0})
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert probabilities["home"] == pytest.approx((1 / 2) / (1 / 2 + 1 / 3.5 + 1 / 4))


def test_candidates_disabled_until_model_validated():
    result = screen_value_bets(
        {"home": 0.60, "draw": 0.22, "away": 0.18},
        {"home": 2.0, "draw": 3.5, "away": 4.0},
    )
    assert result == []


def test_high_edge_candidate_passes_thresholds():
    result = screen_value_bets(
        {"home": 0.70, "draw": 0.18, "away": 0.12},
        {"home": 2.0, "draw": 3.5, "away": 4.0},
        model_validated=True,
    )
    assert result
    assert result[0]["selection"] == "home"
    assert result[0]["edge"] >= 0.04
    assert result[0]["expected_return_per_unit"] >= 0.05
    assert result[0]["status"] == "CANDIDATE_NOT_GUARANTEED"


def test_no_candidate_when_edge_or_return_is_too_small():
    result = screen_value_bets(
        {"home": 0.51, "draw": 0.27, "away": 0.22},
        {"home": 2.0, "draw": 3.5, "away": 4.0},
        model_validated=True,
    )
    assert result == []


def test_invalid_odds_rejected_by_devig():
    with pytest.raises(ValueError):
        devig_probabilities({"home": 1.0, "away": 2.0})


def test_missing_or_invalid_market_data_produces_no_candidate():
    assert screen_value_bets({"home": 0.8}, {"home": 2.0}, model_validated=True) == []
    assert screen_value_bets(
        {"home": float("nan"), "draw": 0.1},
        {"home": 2.0, "draw": 3.0},
        model_validated=True,
    ) == []


def test_1x2_value_screen_supports_home_draw_away_outcomes():
    result = screen_value_bets(
        {"home_win": 0.70, "draw": 0.18, "away_win": 0.12},
        {"home_win": 2.0, "draw": 4.5, "away_win": 7.0},
        model_validated=True,
    )
    assert result
    assert result[0]["selection"] == "home_win"
    assert result[0]["edge"] >= 0.04
    assert result[0]["expected_return_per_unit"] >= 0.05


def test_1x2_value_screen_stays_disabled_without_validation():
    result = screen_value_bets(
        {"home_win": 0.70, "draw": 0.18, "away_win": 0.12},
        {"home_win": 2.0, "draw": 4.5, "away_win": 7.0},
    )
    assert result == []


def test_fixture_value_screen_covers_1x2_btts_and_totals_but_stays_locked():
    from app.value_bets import screen_fixture_value_bets

    prediction = {
        "home_team": "Home FC",
        "away_team": "Away FC",
        "probabilities": {"home_win": 0.70, "draw": 0.18, "away_win": 0.12},
        "btts_yes": 0.60,
        "over_2_5": 0.65,
        "the_odds_api_market_odds": {"markets": {
            "h2h": [{"bookmaker": "Book A", "outcomes": [
                {"name": "Home FC", "price": 2.0},
                {"name": "Draw", "price": 4.5},
                {"name": "Away FC", "price": 7.0},
            ]}],
            "btts": [{"bookmaker": "Book A", "outcomes": [
                {"name": "Yes", "price": 2.0}, {"name": "No", "price": 2.0},
            ]}],
            "totals": [{"bookmaker": "Book A", "outcomes": [
                {"name": "Over", "point": 2.5, "price": 2.0},
                {"name": "Under", "point": 2.5, "price": 2.0},
            ]}],
        }},
    }
    result = screen_fixture_value_bets(prediction)
    assert result["status"] == "DISABLED_UNVALIDATED"
    assert result["markets"]["1X2"]["bookmaker_price_sets"] == 1
    assert result["markets"]["BTTS"]["bookmaker_price_sets"] == 1
    assert result["markets"]["OVER_UNDER_2_5"]["bookmaker_price_sets"] == 1
    assert result["candidate_count"] == 0


def test_fixture_value_screen_can_rank_1x2_candidates_after_explicit_validation():
    from app.value_bets import screen_fixture_value_bets

    prediction = {
        "home_team": "Home FC",
        "away_team": "Away FC",
        "probabilities": {"home_win": 0.70, "draw": 0.18, "away_win": 0.12},
        "the_odds_api_market_odds": {"markets": {"h2h": [{
            "bookmaker": "Book A", "outcomes": [
                {"name": "Home FC", "price": 2.0},
                {"name": "Draw", "price": 4.5},
                {"name": "Away FC", "price": 7.0},
            ],
        }]}},
    }
    certificate = {
        "schema_version": 1, "status": "VALIDATED",
        "betting_validation": True, "approved_markets": ["1X2"],
    }
    result = screen_fixture_value_bets(prediction, validation_certificate=certificate)
    candidates = result["markets"]["1X2"]["candidates"]
    assert candidates
    assert candidates[0]["selection"] == "home_win"
    assert candidates[0]["market"] == "1X2"
    assert candidates[0]["provider"] == "The Odds API"


def test_attach_value_screen_writes_report_level_validation_gate():
    from app.value_bets import attach_value_bet_screens

    report = {"predictions": [{"home_team": "A", "away_team": "B"}]}
    attached = attach_value_bet_screens(report)
    assert attached["value_bet_screen"]["status"] == "DISABLED_UNVALIDATED"
    assert attached["value_bet_screen"]["markets"] == ["1X2", "BTTS", "OVER_UNDER_2_5"]
    assert attached["predictions"][0]["value_bet_screen"]["candidate_count"] == 0


def test_value_validation_certificate_fails_closed_without_backtest_and_paper_evidence():
    from app.value_bets import build_value_validation_certificate

    certificate = build_value_validation_certificate({}, {})
    assert certificate["status"] == "LOCKED_INSUFFICIENT_EVIDENCE"
    assert certificate["betting_validation"] is False
    assert certificate["approved_markets"] == []
    assert certificate["alerts_enabled"] is False
    assert all(
        item["status"] == "LOCKED"
        for item in certificate["market_diagnostics"].values()
    )


def test_value_screen_rejects_partial_or_unapproved_market_certificate():
    from app.value_bets import screen_fixture_value_bets

    prediction = {
        "home_team": "Home FC", "away_team": "Away FC",
        "probabilities": {"home_win": 0.70, "draw": 0.18, "away_win": 0.12},
        "the_odds_api_market_odds": {"markets": {"h2h": [{
            "bookmaker": "Book A", "outcomes": [
                {"name": "Home FC", "price": 2.0},
                {"name": "Draw", "price": 4.5},
                {"name": "Away FC", "price": 7.0},
            ],
        }]}},
    }
    certificate = {
        "schema_version": 1, "status": "PARTIALLY_VALIDATED",
        "betting_validation": True, "approved_markets": ["BTTS"],
    }
    result = screen_fixture_value_bets(prediction, validation_certificate=certificate)
    assert result["markets"]["1X2"]["status"] == "DISABLED_UNVALIDATED"
    assert result["candidate_count"] == 0
