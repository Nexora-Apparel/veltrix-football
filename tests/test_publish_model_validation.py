from scripts.publish_model_validation import build_summary


def sample_backtest():
    return {
        "test_matches": 1000,
        "first_test_date": "2020-01-01",
        "last_test_date": "2025-01-01",
        "dataset_provenance": {"sha256": "abc123", "rows_loaded": 1200, "bytes": 1234},
        "models": {
            "poisson": {"matches": 1000, "result_accuracy": 0.46, "brier_score": 0.63, "log_loss": 1.04},
            "elo": {"matches": 1000, "result_accuracy": 0.48, "brier_score": 0.62, "log_loss": 1.03},
        },
        "historical_odds_subset": {
            "matches_with_valid_1x2_odds": 900,
            "models_compared_on_same_matches": {
                "market": {"matches": 900, "result_accuracy": 0.50, "brier_score": 0.60, "log_loss": 1.00}
            },
        },
        "live_pipeline": {
            "one_x_two_calibration": {
                "live_poisson": {
                    "status": "ROLLING_ORIGIN_DIAGNOSTIC_ONLY",
                    "folds_requested": 4,
                    "folds_evaluated": 4,
                    "raw": {"matches": 100, "brier_score": 0.64, "log_loss": 1.06},
                    "calibrated": {"matches": 100, "brier_score": 0.63, "log_loss": 1.05},
                    "market_on_same_odds_covered_fixtures": {"matches": 95},
                    "beats_market_on_same_fixtures": False,
                    "market_anchor_blend_beats_market": False,
                    "calibration_diagnostic_pass": True,
                },
                "note": "diagnostic only",
            },
            "goal_markets": {
                "rolling_origin_calibration": {
                    "folds_requested": 4,
                    "folds_evaluated": 4,
                    "markets": {
                        "btts_yes": {
                            "status": "CALIBRATION_DIAGNOSTIC_PASS",
                            "folds_evaluated": 4,
                            "folds_beating_raw_and_baseline": 4,
                            "raw": {"matches": 100, "brier_score": 0.26, "log_loss": 0.70},
                            "calibrated": {"matches": 100, "brier_score": 0.24, "log_loss": 0.68},
                            "expanding_baseline": {"matches": 100, "brier_score": 0.25, "log_loss": 0.69},
                        }
                    },
                    "all_goal_markets_calibration_pass": True,
                }
            },
        },
    }


def sample_coverage():
    return {
        "sha256": "abc123",
        "rows": 1200,
        "valid_rows": 1200,
        "invalid_rows": 0,
        "duplicate_match_keys": 0,
        "competition_count": 4,
        "missing_values": {"home_elo": {"count": 10, "rate": 0.01}},
    }


def test_model_validation_summary_keeps_calibration_separate_from_certification():
    result = build_summary(sample_backtest(), sample_coverage(), "2026-11-02T00:00:00Z")
    assert result["status"] == "RESEARCH_DIAGNOSTIC_ONLY"
    assert result["dataset"]["integrity_status"] == "PASS"
    assert result["historical_1x2"]["market_outperforms_both_on_brier_and_log_loss"] is True
    assert result["rolling_origin_1x2_calibration"]["live_poisson"]["applied_to_production"] is False
    assert result["rolling_origin_goal_market_calibration"]["markets"]["btts_yes"]["diagnostic_only"] is True
    assert result["rolling_origin_goal_market_calibration"]["betting_certification"] is False
    assert result["release_controls"]["value_betting"] == "LOCKED_INSUFFICIENT_EVIDENCE"
    assert result["release_controls"]["alerts_enabled"] is False


def test_model_validation_summary_rejects_dataset_fingerprint_mismatch():
    coverage = sample_coverage()
    coverage["sha256"] = "different"
    try:
        build_summary(sample_backtest(), coverage)
    except ValueError as exc:
        assert "fingerprints do not match" in str(exc)
    else:
        raise AssertionError("Mismatched dataset fingerprints must be rejected.")
