import unittest

from app.dataset_bound_market_training import fit_models_from_chronological_dataset
from app.market_probability_calibration import (
    MarketCalibrationError,
    calibrate_model_on_validation_split,
)
from app.independent_market_models import predict_independent_markets
from test_dataset_bound_market_training import dataset_fixture


class MarketProbabilityCalibrationTests(unittest.TestCase):
    def fitted(self):
        dataset = dataset_fixture()
        result = fit_models_from_chronological_dataset(
            dataset=dataset, trained_at="2026-10-02T00:00:00Z", epochs=150,
        )
        return dataset, result["model"]

    def test_calibrates_only_validation_and_preserves_test_holdout(self):
        dataset, model = self.fitted()
        result = calibrate_model_on_validation_split(
            model=model, dataset=dataset, calibrated_at="2026-11-18T00:00:00Z",
        )
        calibrated = result["model"]
        audit = result["calibration_audit"]
        self.assertEqual(calibrated["calibration"]["status"], "calibrated")
        self.assertEqual(audit["validation_rows_used"], 120)
        self.assertEqual(audit["validation_dates_used"], 40)
        self.assertEqual(audit["training_rows_used_for_calibration"], 0)
        self.assertEqual(audit["test_rows_used_for_calibration"], 0)
        self.assertFalse(audit["test_partition_opened"])
        self.assertFalse(audit["publication_allowed"])
        self.assertFalse(audit["value_betting_enabled"])
        test_row = next(row for row in dataset["rows"] if row["split"] == "test")
        prediction = predict_independent_markets(
            model=calibrated, features=test_row["predictors"],
            prediction_as_of="2026-11-25T00:00:00Z",
        )
        self.assertEqual(prediction["calibration_status"], "calibrated")
        for market in ("1x2", "btts", "over_2_5"):
            self.assertAlmostEqual(
                sum(prediction["probabilities"][market].values()), 1.0,
            )

    def test_rejects_model_bound_to_another_dataset(self):
        dataset, model = self.fitted()
        altered = dict(dataset)
        altered["dataset_sha256"] = "0" * 64
        with self.assertRaisesRegex(MarketCalibrationError, "dataset_rejected|binding_mismatch"):
            calibrate_model_on_validation_split(
                model=model, dataset=altered, calibrated_at="2026-11-18T00:00:00Z",
            )


    def test_rejects_calibrated_model_before_calibration_timestamp(self):
        dataset, model = self.fitted()
        calibrated = calibrate_model_on_validation_split(
            model=model, dataset=dataset, calibrated_at="2026-11-18T00:00:00Z",
        )["model"]
        row = next(row for row in dataset["rows"] if row["split"] == "test")
        with self.assertRaisesRegex(Exception, "calibrated_after_prediction_cutoff"):
            predict_independent_markets(
                model=calibrated, features=row["predictors"],
                prediction_as_of="2026-11-17T00:00:00Z",
            )

    def test_rejects_calibration_before_validation_labels_are_retrieved(self):
        dataset, model = self.fitted()
        with self.assertRaisesRegex(
            MarketCalibrationError, "validation_label_retrieved_after_calibration"
        ):
            calibrate_model_on_validation_split(
                model=model, dataset=dataset, calibrated_at="2026-10-08T17:30:00Z",
            )


if __name__ == "__main__":
    unittest.main()
