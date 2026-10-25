import pytest

from app.advanced_models import blend_1x2, dixon_coles_1x2, recency_weighted_mean, rest_congestion_context


def test_recency_weighted_mean_gives_more_weight_to_recent_values():
    assert recency_weighted_mean([0, 10], decay=0.5) == pytest.approx(20 / 3)
    assert recency_weighted_mean([0, 10], decay=1.0) == pytest.approx(5.0)


def test_recency_weighted_mean_rejects_bad_inputs():
    with pytest.raises(ValueError):
        recency_weighted_mean([])
    with pytest.raises(ValueError):
        recency_weighted_mean([1, 2], decay=0)


def test_dixon_coles_probabilities_are_valid_and_normalized():
    probs = dixon_coles_1x2(1.45, 1.1, rho=-0.05)
    assert set(probs) == {"H", "D", "A"}
    assert sum(probs.values()) == pytest.approx(1.0)
    assert all(0 <= value <= 1 for value in probs.values())


def test_dixon_coles_zero_rho_matches_independent_poisson():
    from app.backtest_engine import poisson_1x2
    dc = dixon_coles_1x2(1.45, 1.1, rho=0)
    independent = poisson_1x2(1.45, 1.1)
    for outcome in ("H", "D", "A"):
        assert dc[outcome] == pytest.approx(independent[outcome], abs=1e-10)


def test_dixon_coles_rejects_invalid_parameters():
    with pytest.raises(ValueError):
        dixon_coles_1x2(-1, 1)
    with pytest.raises(ValueError):
        dixon_coles_1x2(1, 1, rho=0.5)


def test_blend_1x2_normalizes_valid_weighted_models():
    result = blend_1x2(
        {"elo": {"H": 0.5, "D": 0.25, "A": 0.25},
         "dc": {"H": 0.4, "D": 0.3, "A": 0.3}},
        {"elo": 1, "dc": 3},
    )
    assert result == pytest.approx({"H": 0.425, "D": 0.2875, "A": 0.2875})


def test_blend_1x2_rejects_invalid_probability_vectors():
    with pytest.raises(ValueError):
        blend_1x2({"bad": {"H": 0.5, "D": 0.5, "A": 0.5}}, {"bad": 1})


def test_rest_congestion_context_uses_only_matches_before_target_date():
    from datetime import date

    history = [
        {"date": date(2026, 10, 1), "home_key": "alpha", "away_key": "beta"},
        {"date": date(2026, 10, 15), "home_key": "gamma", "away_key": "alpha"},
        {"date": date(2026, 10, 25), "home_key": "alpha", "away_key": "delta"},
    ]
    context = rest_congestion_context(
        history, "alpha", "beta", date(2026, 10, 25), window_days=14
    )
    assert context["home"]["days_since_last_match"] == 10
    assert context["home"]["matches_in_previous_14_days"] == 1
    assert context["away"]["days_since_last_match"] == 24
    assert context["away"]["matches_in_previous_14_days"] == 0


def test_rest_congestion_context_rejects_invalid_window():
    from datetime import date

    with pytest.raises(ValueError):
        rest_congestion_context([], "alpha", "beta", date(2026, 10, 25), window_days=0)
