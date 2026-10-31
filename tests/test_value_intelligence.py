import pytest

from app.value_intelligence import (
    closing_line_value, devig, evaluate_price, market_consensus,
    poisson_scoreline_markets, shrink_to_market,
)


def test_devig_removes_overround():
    result = devig({"home": 2.0, "draw": 3.5, "away": 4.0})
    assert sum(result.values()) == pytest.approx(1.0)
    assert result["home"] == pytest.approx((1 / 2.0) / (1 / 2.0 + 1 / 3.5 + 1 / 4.0))


def test_consensus_uses_multiple_complete_book_sets():
    result = market_consensus([
        {"yes": 1.9, "no": 1.9},
        {"yes": 2.0, "no": 1.8},
    ])
    assert result["status"] == "CONSENSUS_READY"
    assert result["bookmaker_count"] == 2
    assert sum(result["probabilities"].values()) == pytest.approx(1.0)


def test_incomplete_books_are_rejected():
    result = market_consensus([{"yes": 1.9}, {"yes": 2.0, "no": 1.8}])
    assert result["rejected_bookmaker_sets"] == 1
    assert result["status"] == "SINGLE_BOOK_ONLY"


def test_shrinkage_moves_model_toward_market_and_haircuts_uncertainty():
    consensus = {"probabilities": {"yes": 0.5, "no": 0.5},
                 "dispersion": {"yes": 0.02, "no": 0.02}}
    result = shrink_to_market({"yes": 0.8, "no": 0.2}, consensus)
    assert result["probabilities"]["yes"] == pytest.approx(0.605)
    assert result["conservative_lower_bound"]["yes"] < result["probabilities"]["yes"]


def test_price_evaluation_uses_probability_passed_in():
    result = evaluate_price(0.60, 2.0)
    assert result["status"] == "SHADOW_CANDIDATE"
    assert result["release_status"] == "LOCKED_SHADOW_MODE"
    assert result["expected_value_per_unit"] == pytest.approx(0.20)


def test_clv_positive_when_taken_price_beats_closing_price():
    result = closing_line_value(2.10, 1.90)
    assert result["status"] == "MEASURED"
    assert result["price_improvement_percent"] > 0


def test_poisson_scoreline_markets_are_coherent():
    result = poisson_scoreline_markets(1.5, 1.0)
    assert result["home_win"] + result["draw"] + result["away_win"] == pytest.approx(1.0)
    assert 0 < result["btts_yes"] < 1
    assert result["over_1_5"] > result["over_2_5"] > result["over_3_5"]


def test_invalid_prices_and_lambdas_fail_closed():
    with pytest.raises(ValueError):
        devig({"home": 1.0, "away": 2.0})
    with pytest.raises(ValueError):
        poisson_scoreline_markets(-1, 1)
