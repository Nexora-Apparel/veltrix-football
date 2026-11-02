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
                "poisson": {"matches": 900, "result_accuracy": 0.46, "brier_score": 0.63, "log_loss": 1.04},
                "elo": {"matches": 900, "result_accuracy": 0.48, "brier_score": 0.62, "log_loss": 1.03},
                "market": {"matches": 900, "result_accuracy": 0.50, "brier_score": 0.60, "log_loss": 1.00}
            },
        },
        "live_pipeline": {
            "one_x_two_calibration": {
                "live_poisson": {
                    "status": "ROLLING_ORIGIN_DIAGNOSTIC_ONLY",
                    "folds_requested": 4,
                    "folds_evaluated": 4,
                    "raw": {"matches": 100, "brier_score": 0.64, "log_loss": 1.06, "predicted_class_counts": {"H": 70, "D": 0, "A": 30}, "actual_class_counts": {"H": 43, "D": 26, "A": 31}},
                    "calibrated": {"matches": 100, "brier_score": 0.63, "log_loss": 1.05, "predicted_class_counts": {"H": 60, "D": 10, "A": 30}, "actual_class_counts": {"H": 43, "D": 26, "A": 31}, "class_precision_recall": {"D": {"precision": 0.3, "recall": 0.1}}},
                    "market_on_same_odds_covered_fixtures": {"matches": 95},
                    "beats_market_on_same_fixtures": False,
                    "market_anchor_blend_beats_market": False,
                    "calibration_diagnostic_pass": True,
                },
                "note": "diagnostic only",
            },
            "outcome_balance_audit": {
                "poisson": {
                    "status": "CHRONOLOGICAL_CLASS_BALANCE_DIAGNOSTIC",
                    "matches": 100,
                    "home_bias_flag": "HOME_CLASS_OVERPREDICTED",
                    "classes": {"H": {"actual_share": 0.43, "predicted_share": 0.65, "prediction_share_gap_percentage_points": 22.0, "mean_predicted_probability": 0.44, "observed_frequency": 0.43, "probability_minus_observed_percentage_points": 1.0}},
                }
            },
            "confidence_selection_audit": {
                "elo": {"status": "CHRONOLOGICAL_SELECTIVE_ACCURACY_DIAGNOSTIC", "total_matches": 100, "thresholds": [{"minimum_top_probability": 0.7, "selected_matches": 2, "coverage": 0.02, "accuracy": 1.0, "predicted_class_counts": {"H": 2, "D": 0, "A": 0}}]}
            },
            "favourite_underdog_audit": {
                "elo": {"status": "diagnostic_only", "overall": {"matches": 100, "accuracy": 0.48}, "favourite_wins": {"matches": 50, "accuracy": 0.8}, "underdog_wins": {"matches": 20, "accuracy": 0.2}, "matches_with_market_classification": 90}
            },
            "draw_margin_experiment": {
                "elo": {"status": "DIAGNOSTIC_ONLY_NOT_APPLIED", "holdout_matches": 100, "selected_draw_margin": 0.0, "raw_argmax_holdout": {"matches": 100, "accuracy": 0.48, "predicted_class_counts": {"H": 70, "D": 0, "A": 30}}, "draw_margin_holdout": {"matches": 100, "accuracy": 0.48, "predicted_class_counts": {"H": 70, "D": 0, "A": 30}}, "holdout_accuracy_delta": 0.0, "improved_unseen_holdout_accuracy": False}
            },
            "recent_holdout": {"method": "latest 20% of unique dates", "start_date": "2025-01-01", "end_date": "2026-09-03", "matches": 100, "metrics": {"matches": 100, "result_accuracy": 0.48, "brier_score": 0.62, "log_loss": 1.03}},
            "dixon_coles_alternative": {"model": "experimental_recency_weighted_dixon_coles", "rho": -0.05, "metrics": {"matches": 100, "result_accuracy": 0.44, "brier_score": 0.64, "log_loss": 1.06}, "model_validated": False},
            "elo_alternative": {"model": "experimental_elo_by_competition", "matches": 100, "metrics": {"matches": 100, "result_accuracy": 0.48, "brier_score": 0.62, "log_loss": 1.03}},
            "metrics_by_competition": {"E0": {"live_eligible_matches": 20, "poisson": {"matches": 20, "result_accuracy": 0.45}, "elo": {"matches": 20, "result_accuracy": 0.48}, "historical_odds_matches": 18, "same_match_market_comparison": {"poisson": {"matches": 18, "result_accuracy": 0.44}, "market": {"matches": 18, "result_accuracy": 0.5}}, "elo_same_match_market_comparison": {"elo": {"matches": 18, "result_accuracy": 0.48}, "market": {"matches": 18, "result_accuracy": 0.5}}}},
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
    assert result["rolling_origin_1x2_calibration"]["live_poisson"]["calibrated"]["predicted_class_counts"]["D"] == 10
    assert result["rolling_origin_1x2_calibration"]["live_poisson"]["calibrated"]["class_precision_recall"]["D"]["recall"] == 0.1
    assert result["rolling_origin_goal_market_calibration"]["markets"]["btts_yes"]["diagnostic_only"] is True
    assert result["rolling_origin_goal_market_calibration"]["betting_certification"] is False
    assert result["release_controls"]["value_betting"] == "LOCKED_INSUFFICIENT_EVIDENCE"
    assert result["release_controls"]["alerts_enabled"] is False
    assert result["class_balance_audit"]["poisson"]["home_bias_flag"] == "HOME_CLASS_OVERPREDICTED"\n    assert result["class_balance_audit"]["poisson"]["classes"]["H"]["mean_predicted_probability"] == 0.44\n    assert result["class_balance_audit"]["poisson"]["classes"]["H"]["probability_minus_observed_percentage_points"] == 1.0
    assert result["confidence_selection_audit"]["elo"]["thresholds"][0]["coverage"] == 0.02
    assert result["favourite_underdog_audit"]["elo"]["underdog_wins"]["accuracy"] == 0.2
    assert result["draw_margin_experiment"]["models"]["elo"]["improved_unseen_holdout_accuracy"] is False
    assert result["recent_holdout"]["matches"] == 100
    assert result["alternative_models"]["dixon_coles"]["production_applied"] is False
    assert result["metrics_by_competition"]["E0"]["elo_market_comparison"]["market"]["matches"] == 18


def test_model_validation_summary_rejects_dataset_fingerprint_mismatch():
    coverage = sample_coverage()
    coverage["sha256"] = "different"
    try:
        build_summary(sample_backtest(), coverage)
    except ValueError as exc:
        assert "fingerprints do not match" in str(exc)
    else:
        raise AssertionError("Mismatched dataset fingerprints must be rejected.")
