from scripts.build_value_certificate_runtime_v2 import apply_calibration_from_artifact


def test_runtime_adapter_reads_sample_counts_from_real_backtest_shape():
    
    markets = {
        "btts_yes": (0.1, 0.2),
        "over_1_5": (0.2, 0.3),
        "over_2_5": (0.3, 0.4),
        "over_3_5": (0.4, 0.5),
    }
    experiment = {
        "calibration_cutoff_date": "2025-01-12",
        "calibration_matches": 2000,
        "test_matches": 2000,
        "markets": {
            key: {
                "status": "CALIBRATION_FIT_EVALUATED_ON_LATER_DATES",
                "platt_intercept": intercept,
                "platt_slope": slope,
                "improved_brier_and_log_loss": True,
            }
            for key, (intercept, slope) in markets.items()
        },
    }
    rolling = {
        "markets": {
            key: {
                "status": "CALIBRATION_DIAGNOSTIC_PASS",
                "folds_evaluated": 4,
                "raw": {"matches": 2000},
            }
            for key in markets
        }
    }
    backtest = {
        "dataset_provenance": {"sha256": "b" * 64},
        "live_pipeline": {
            "goal_markets": {
                "chronological_calibration_experiment": experiment,
                "rolling_origin_calibration": rolling,
            }
        },
    }
    report = {
        "predictions": [{
            "goal_markets_model": "experimental_recent_goals_poisson",
            "btts_yes": 0.64,
            "over_1_5": 0.82,
            "over_2_5": 0.61,
            "over_3_5": 0.39,
        }],
    }
    apply_calibration_from_artifact(report, backtest)
    assert report["goal_market_calibration"]["status"] == "APPLIED_PROSPECTIVELY"
    assert report["goal_market_calibration"]["markets"] == sorted(markets)
    assert report["goal_market_calibration"]["compatible_forecasts"] == 1
    assert report["goal_market_calibration"]["applied_forecasts"] == 1
