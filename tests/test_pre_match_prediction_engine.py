import copy
import unittest

from app.point_in_time_feature_contract import build_point_in_time_feature_snapshot
from app.pre_match_prediction_engine import (
    MODEL_VERSION,
    ModelInferenceError,
    build_model_parameter_set,
    infer_pre_match_forecast,
    validate_pre_match_forecast,
)


CUTOFF = "2026-11-10T05:00:00Z"
FEATURES = [
    ("home_team_elo", 1600.0),
    ("away_team_elo", 1500.0),
    ("home_rolling_xg_for", 1.55),
    ("home_rolling_xg_against", 1.10),
    ("away_rolling_xg_for", 1.25),
    ("away_rolling_xg_against", 1.35),
]


def make_snapshot(features=FEATURES):
    values = []
    for name, value in features:
        values.append({
            "name": name,
            "value": value,
            "source": "veltrix_point_in_time_feature_store",
            "source_id": f"observation-{name}",
            "observed_at": "2026-11-09T04:00:00Z",
            "available_at": "2026-11-09T04:00:00Z",
            "retrieved_at": "2026-11-09T04:05:00Z",
            "payload_sha256": "a" * 64,
        })
    return build_point_in_time_feature_snapshot(
        fixture_id="fixture-2026-11-10-001",
        prediction_as_of=CUTOFF,
        features=values,
    )


def make_params(**overrides):
    values = {
        "training_dataset_sha256": "b" * 64,
        "training_data_cutoff_at": "2026-11-09T00:00:00Z",
        "trained_until": "2026-11-08T22:00:00Z",
        "trained_at": "2026-11-09T01:00:00Z",
        "home_advantage_multiplier": 1.05,
        "elo_goal_coefficient": 0.0005,
        "rho": -0.05,
        "max_goals": 15,
        "calibration_id": "calibration-2026-11-09",
    }
    values.update(overrides)
    return build_model_parameter_set(**values)


class PreMatchPredictionEngineTests(unittest.TestCase):
    def test_dixon_coles_engine_emits_all_markets_without_publication(self):
        snapshot = make_snapshot()
        params = make_params()
        forecast = infer_pre_match_forecast(snapshot=snapshot, model_parameters=params)
        verified = validate_pre_match_forecast(
            forecast=forecast, snapshot=snapshot, model_parameters=params,
        )
        self.assertTrue(verified["valid"])
        self.assertEqual(forecast["model_version"], MODEL_VERSION)
        self.assertEqual(forecast["status"], "inference_complete_validation_required")
        self.assertFalse(forecast["publication_allowed"])
        self.assertFalse(forecast["value_betting_enabled"])
        self.assertFalse(forecast["fallback_prior_used"])
        self.assertFalse(forecast["favourite_filter_used"])
        self.assertAlmostEqual(sum(forecast["probabilities"]["1x2"].values()), 1.0, places=8)
        self.assertAlmostEqual(sum(forecast["probabilities"]["btts"].values()), 1.0, places=8)
        self.assertAlmostEqual(sum(forecast["probabilities"]["over_2_5"].values()), 1.0, places=8)
        self.assertAlmostEqual(sum(sum(row) for row in forecast["score_matrix"]), 1.0, places=8)

    def test_missing_required_features_withhold_without_generic_prior(self):
        snapshot = make_snapshot(FEATURES[:-1])
        forecast = infer_pre_match_forecast(snapshot=snapshot, model_parameters=make_params())
        self.assertEqual(forecast["status"], "withheld")
        self.assertIsNone(forecast["probabilities"])
        self.assertIn("away_rolling_xg_against", forecast["missing_features"])
        self.assertFalse(forecast["fallback_prior_used"])

    def test_nonpositive_rolling_xg_withholds_forecast(self):
        features = list(FEATURES)
        features[2] = ("home_rolling_xg_for", 0.0)
        forecast = infer_pre_match_forecast(
            snapshot=make_snapshot(features), model_parameters=make_params(),
        )
        self.assertEqual(forecast["status"], "withheld")
        self.assertIn("rolling_xg_feature_out_of_supported_range", forecast["withheld_reasons"])

    def test_future_training_data_or_model_training_time_is_rejected(self):
        with self.assertRaisesRegex(ModelInferenceError, "temporal_leakage"):
            infer_pre_match_forecast(
                snapshot=make_snapshot(),
                model_parameters=make_params(training_data_cutoff_at="2026-11-10T06:00:00Z"),
            )
        with self.assertRaisesRegex(ModelInferenceError, "temporal_leakage"):
            infer_pre_match_forecast(
                snapshot=make_snapshot(),
                model_parameters=make_params(trained_at="2026-11-08T23:00:00Z"),
            )

    def test_dixon_coles_negative_low_score_cell_withholds_forecast(self):
        features = [
            ("home_team_elo", 1500.0), ("away_team_elo", 1500.0),
            ("home_rolling_xg_for", 3.0), ("home_rolling_xg_against", 3.0),
            ("away_rolling_xg_for", 3.0), ("away_rolling_xg_against", 3.0),
        ]
        forecast = infer_pre_match_forecast(
            snapshot=make_snapshot(features),
            model_parameters=make_params(
                home_advantage_multiplier=1.0,
                elo_goal_coefficient=0.0,
                rho=0.2,
            ),
        )
        self.assertEqual(forecast["status"], "withheld")
        self.assertIn("dixon_coles_correction_invalid", forecast["withheld_reasons"])

    def test_parameter_hash_tampering_is_rejected(self):
        params = make_params()
        params["rho"] = 0.1
        with self.assertRaisesRegex(ModelInferenceError, "parameter_hash_invalid"):
            infer_pre_match_forecast(snapshot=make_snapshot(), model_parameters=params)

    def test_forecast_hash_tampering_is_rejected(self):
        snapshot = make_snapshot()
        params = make_params()
        forecast = infer_pre_match_forecast(snapshot=snapshot, model_parameters=params)
        changed = copy.deepcopy(forecast)
        changed["probabilities"]["1x2"]["home"] = 0.99
        with self.assertRaisesRegex(ModelInferenceError, "forecast_hash_mismatch"):
            validate_pre_match_forecast(
                forecast=changed, snapshot=snapshot, model_parameters=params,
            )


if __name__ == "__main__":
    unittest.main()
