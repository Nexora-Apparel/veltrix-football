import unittest

from app.dataset_bound_market_training import fit_models_from_chronological_dataset
from app.heldout_market_evaluation import (
    HeldoutEvaluationError,
    evaluate_calibrated_model_on_test_partition,
)
from app.market_probability_calibration import calibrate_model_on_validation_split
from test_dataset_bound_market_training import dataset_fixture


class HeldoutMarketEvaluationTests(unittest.TestCase):
    def calibrated(self):
        dataset = dataset_fixture()
        model = fit_models_from_chronological_dataset(
            dataset=dataset, trained_at="2026-10-02T00:00:00Z", epochs=150,
        )["model"]
        calibrated = calibrate_model_on_validation_split(
            model=model, dataset=dataset, calibrated_at="2026-11-18T00:00:00Z",
        )["model"]
        return dataset, calibrated

    def test_evaluates_only_sealed_test_partition(self):
        dataset, model = self.calibrated()
        report = evaluate_calibrated_model_on_test_partition(
            model=model, dataset=dataset, evaluated_at="2026-12-15T00:00:00Z",
        )
        self.assertEqual(report["test_fixture_count"], 20)
        self.assertEqual(report["test_distinct_wat_dates"], 20)
        self.assertEqual(report["evaluation_type"], "single_chronological_heldout_test_partition")
        self.assertFalse(report["full_walk_forward_certified"])
        self.assertFalse(report["value_bet_certified"])
        self.assertFalse(report["publication_allowed"])
        self.assertEqual(report["bookmaker_comparison"], "unavailable_timestamped_odds_not_supplied")
        self.assertEqual(set(report["metrics"]), {"1x2", "btts", "over_2_5"})

    def test_rejects_evaluation_before_test_labels_are_retrieved(self):
        dataset, model = self.calibrated()
        with self.assertRaisesRegex(HeldoutEvaluationError, "test_label_retrieved_after_evaluation"):
            evaluate_calibrated_model_on_test_partition(
                model=model, dataset=dataset, evaluated_at="2026-11-24T17:30:00Z",
            )

    def test_rejects_changed_dataset(self):
        dataset, model = self.calibrated()
        dataset["rows"][0]["predictors"]["elo_difference_home"] += 0.5
        with self.assertRaisesRegex(HeldoutEvaluationError, "dataset_rejected"):
            evaluate_calibrated_model_on_test_partition(
                model=model, dataset=dataset, evaluated_at="2026-12-15T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
