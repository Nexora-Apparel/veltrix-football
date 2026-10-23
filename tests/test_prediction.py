import math
import pytest

from app.prediction import evaluate_decimal_odds, match_probabilities, poisson_pmf


def test_poisson_distribution_is_finite_and_bounded():
    probs = poisson_pmf(1.4, 12)
    assert len(probs) == 13
    assert all(math.isfinite(p) and 0 <= p <= 1 for p in probs)
    assert sum(probs) <= 1.0000001


def test_market_probabilities_are_valid_and_1x2_sums_to_one():
    result = match_probabilities(1.45, 0.95)
    outcomes = result["one_x_two"]
    assert sum(outcomes.values()) == pytest.approx(1.0)
    assert all(0 <= p <= 1 for p in outcomes.values())
    assert result["btts_yes"] + result["btts_no"] == pytest.approx(1.0)
    for over, under in [("over_1_5", "under_1_5"), ("over_2_5", "under_2_5"), ("over_3_5", "under_3_5")]:
        assert result["totals"][over] + result["totals"][under] == pytest.approx(1.0)
    assert len(result["most_likely_scorelines"]) == 5


def test_equal_expected_goals_produce_symmetric_win_probabilities():
    outcomes = match_probabilities(1.2, 1.2)["one_x_two"]
    assert outcomes["home_win"] == pytest.approx(outcomes["away_win"])


def test_zero_expected_goals_is_supported():
    result = match_probabilities(0, 0)
    assert result["one_x_two"]["draw"] == pytest.approx(1.0)
    assert result["btts_yes"] == pytest.approx(0.0)
    assert result["totals"]["under_1_5"] == pytest.approx(1.0)


@pytest.mark.parametrize("home,away", [(-1, 1), (1, -0.1), (float("nan"), 1), (float("inf"), 1)])
def test_invalid_expected_goals_are_rejected(home, away):
    with pytest.raises(ValueError):
        match_probabilities(home, away)


def test_odds_value_math():
    result = evaluate_decimal_odds(0.60, 2.0)
    assert result["raw_implied_probability"] == pytest.approx(0.5)
    assert result["edge_percentage_points"] == pytest.approx(10.0)
    assert result["expected_return_per_unit"] == pytest.approx(0.2)
    assert result["positive_model_edge"] is True


def test_invalid_odds_are_rejected():
    with pytest.raises(ValueError):
        evaluate_decimal_odds(0.5, 1.0)
    with pytest.raises(ValueError):
        evaluate_decimal_odds(1.2, 2.0)
