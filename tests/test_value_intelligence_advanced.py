from app.value_intelligence import (
    ensemble_probabilities, bayesian_market_update, opportunity_quality_score,
    poisson_scoreline_markets,
)


def test_ensemble_requires_two_compatible_models_and_normalizes():
    result = ensemble_probabilities([
        {"home_win": .5, "draw": .3, "away_win": .2},
        {"home_win": .6, "draw": .2, "away_win": .2},
    ])
    assert result["status"] == "ENSEMBLE_READY"
    assert result["model_count"] == 2
    assert abs(sum(result["probabilities"].values()) - 1) < 1e-9
    assert ensemble_probabilities([{"yes": .6, "no": .4}])["status"] == "INSUFFICIENT_MODELS"


def test_bayesian_inspired_update_is_normalized_and_explicitly_uncalibrated():
    result = bayesian_market_update(
        {"yes": .7, "no": .3}, {"yes": .5, "no": .5}, model_prior_weight=.35
    )
    assert result["status"] == "UPDATED"
    assert result["calibration_status"] == "NOT_CALIBRATED"
    assert abs(sum(result["probabilities"].values()) - 1) < 1e-9


def test_scoreline_simulation_and_quality_score_are_bounded():
    markets = poisson_scoreline_markets(1.4, 1.0)
    assert abs(markets["home_win"] + markets["draw"] + markets["away_win"] - 1) < 1e-9
    quality = opportunity_quality_score(.08, .12, 4, .02)
    assert 0 <= quality["score"] <= 100
    assert quality["release_status"] == "LOCKED_SHADOW_MODE"
