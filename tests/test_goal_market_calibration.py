from app.goal_market_calibration import apply_goal_market_calibration


def _backtest():
    markets = {
        "btts_yes": (0.09, 0.23),
        "over_1_5": (0.78, 0.27),
        "over_2_5": (0.01, 0.27),
        "over_3_5": (-0.65, 0.29),
    }
    return {
        "live_pipeline": {
            "goal_markets": {
                "chronological_calibration_experiment": {
                    "status": "DIAGNOSTIC_ONLY_NOT_APPLIED",
                    "method": "frozen train window evaluated on later dates",
                    "calibration_cutoff_date": "2025-01-12",
                    "markets": {
                        key: {
                            "status": "CALIBRATION_FIT_EVALUATED_ON_LATER_DATES",
                            "platt_intercept": intercept,
                            "platt_slope": slope,
                            "improved_brier_and_log_loss": True,
                        }
                        for key, (intercept, slope) in markets.items()
                    },
                },
            },
        },
    }


def test_applies_frozen_calibration_and_preserves_raw_probabilities():
    report = {
        "predictions": [{
            "btts_yes": 0.64,
            "over_1_5": 0.82,
            "over_2_5": 0.61,
            "over_3_5": 0.39,
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
        }],
    }
    apply_goal_market_calibration(report, _backtest())
    row = report["predictions"][0]
    assert row["goal_market_calibration"]["status"] == "APPLIED_PROSPECTIVELY"
    assert row["goal_market_calibration"]["training_cutoff_date"] == "2025-01-12"
    assert row["raw_goal_market_probabilities"]["btts_yes"] == 0.64
    assert row["btts_yes"] != 0.64
    assert row["probabilities"]["home_win"] == 0.5
    assert report["goal_market_calibration"]["status"] == "APPLIED_PROSPECTIVELY"
    assert len(report["goal_market_calibration"]["model_version"]) > 10


def test_incomplete_calibration_does_not_claim_full_application():
    backtest = _backtest()
    del backtest["live_pipeline"]["goal_markets"]["chronological_calibration_experiment"]["markets"]["over_3_5"]
    report = {"predictions": [{"btts_yes": 0.6, "over_1_5": 0.8, "over_2_5": 0.6, "over_3_5": 0.4}]}
    apply_goal_market_calibration(report, backtest)
    assert report["goal_market_calibration"]["status"] == "PARTIAL_OR_UNAVAILABLE"
