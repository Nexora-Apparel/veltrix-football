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
