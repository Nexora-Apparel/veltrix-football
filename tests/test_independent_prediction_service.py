import unittest
from datetime import date, timedelta

from app.independent_market_models import (
    FEATURES, fit_independent_market_models,
)
from app.independent_prediction_service import (
    IndependentInferenceError, infer_independent_fixture,
)
from app.point_in_time_feature_contract import (
    build_point_in_time_feature_snapshot,
)


def _training_rows(count=120):
    rows = []
    start = date(2026, 7, 1)
    for index in range(count):
        day = start + timedelta(days=index % 90)
        home_score = (index * 3 + index // 4) % 4
        away_score = (index * 5 + index // 7) % 3
        features = {
            "home_attack_goals_rate": 1.0 + (index % 5) * 0.2,
            "home_defence_conceded_rate": 0.8 + (index % 4) * 0.15,
            "away_attack_goals_rate": 0.9 + (index % 6) * 0.17,
            "away_defence_conceded_rate": 0.85 + (index % 3) * 0.2,
            "elo_difference_home": float((index % 9) * 80 - 320),
            "home_form_points_rate": (index % 10) / 10,
            "away_form_points_rate": ((index * 3) % 10) / 10,
            "home_rest_days": float(3 + index % 6),
            "away_rest_days": float(2 + (index * 2) % 7),
            "competition_home_goals_rate": 1.4 + (index % 3) * 0.1,
            "competition_away_goals_rate": 1.1 + (index % 4) * 0.08,
        }
        rows.append({
            "fixture_id": f"fixture-{index:04d}",
            "kickoff_at": f"{day.isoformat()}T15:00:00Z",
            "feature_as_of": f"{(day - timedelta(days=1)).isoformat()}T12:00:00Z",
            "settled_at": f"{(day + timedelta(hours=1)).isoformat()}T18:00:00Z",
            "features": features,
            "home_score": home_score,
            "away_score": away_score,
            "source_record_sha256": f"{index + 1:064x}",
        })
    return rows


def _fixture_and_snapshot():
    fixture = {
        "fixture_id": "upcoming-001",
        "competition_key": "EPL",
        "home_team_id": "team-home",
        "away_team_id": "team-away",
        "kickoff_at": "2026-10-04T15:00:00Z",
        "feature_as_of": "2026-10-03T12:00:00Z",
    }
    rows = []
    for index, name in enumerate(FEATURES):
        value = {
            "home_attack_goals_rate": 1.5,
            "home_defence_conceded_rate": 1.0,
            "away_attack_goals_rate": 1.2,
            "away_defence_conceded_rate": 1.1,
            "elo_difference_home": 75.0,
            "home_form_points_rate": 0.6,
            "away_form_points_rate": 0.4,
            "home_rest_days": 6.0,
            "away_rest_days": 4.0,
            "competition_home_goals_rate": 1.45,
            "competition_away_goals_rate": 1.2,
        }[name]
        rows.append({
            "name": name,
            "value": value,
            "source": "qualified-test-source",
            "source_id": f"source-{index}",
            "observed_at": "2026-10-03T10:00:00Z",
            "available_at": "2026-10-03T10:30:00Z",
            "retrieved_at": "2026-10-03T11:00:00Z",
            "payload_sha256": f"{index + 1:064x}",
        })
    snapshot = build_point_in_time_feature_snapshot(
        fixture_id=fixture["fixture_id"],
        prediction_as_of=fixture["feature_as_of"],
        features=rows,
    )
    return fixture, snapshot


class IndependentPredictionServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = fit_independent_market_models(
            training_rows=_training_rows(),
            training_cutoff_at="2026-10-01T00:00:00Z",
            trained_at="2026-10-02T00:00:00Z",
            epochs=150,
        )

    def test_returns_shadow_candidates_without_legacy_or_ensemble(self):
        fixture, snapshot = _fixture_and_snapshot()
        result = infer_independent_fixture(
            fixture=fixture, feature_snapshot=snapshot,
            results_model=self.model,
        )
        self.assertEqual(result["fixture_id"], fixture["fixture_id"])
        self.assertIn("results_history_logistic", result["candidates"])
        self.assertEqual(result["ensemble_status"], "not_fitted_no_out_of_fold_weights")
        self.assertFalse(result["publication_allowed"])
        self.assertFalse(result["value_betting_enabled"])
        self.assertFalse(result["legacy_model_dependency"])
        self.assertFalse(result["fallback_prior_used"])

    def test_rejects_fixture_snapshot_identity_mismatch(self):
        fixture, snapshot = _fixture_and_snapshot()
        fixture["fixture_id"] = "different-fixture"
        with self.assertRaisesRegex(IndependentInferenceError, "fixture_mismatch"):
            infer_independent_fixture(
                fixture=fixture, feature_snapshot=snapshot,
                results_model=self.model,
            )

    def test_rejects_feature_cutoff_mismatch(self):
        fixture, snapshot = _fixture_and_snapshot()
        fixture["feature_as_of"] = "2026-10-03T13:00:00Z"
        with self.assertRaisesRegex(IndependentInferenceError, "cutoff_mismatch"):
            infer_independent_fixture(
                fixture=fixture, feature_snapshot=snapshot,
                results_model=self.model,
            )

    def test_rejects_missing_model_features_instead_of_imputing(self):
        fixture, snapshot = _fixture_and_snapshot()
        snapshot["features"] = [
            item for item in snapshot["features"]
            if item["name"] != FEATURES[0]
        ]
        from app.point_in_time_feature_contract import _hash
        snapshot["feature_count"] = len(snapshot["features"])
        snapshot.pop("snapshot_sha256")
        snapshot["snapshot_sha256"] = _hash(snapshot)
        with self.assertRaisesRegex(IndependentInferenceError, "feature_snapshot_rejected"):
            infer_independent_fixture(
                fixture=fixture, feature_snapshot=snapshot,
                results_model=self.model,
            )


if __name__ == "__main__":
    unittest.main()
