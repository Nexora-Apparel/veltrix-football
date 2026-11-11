import unittest

from app.live_predictions import (
    LegacyPredictionDisabled,
    build_daily_report,
    predict_fixtures,
)


class LegacyPredictionQuarantineTests(unittest.TestCase):
    def test_legacy_fixture_prediction_entrypoint_is_disabled(self):
        with self.assertRaises(LegacyPredictionDisabled):
            predict_fixtures({}, [])

    def test_legacy_daily_report_entrypoint_is_disabled(self):
        with self.assertRaises(LegacyPredictionDisabled):
            build_daily_report({}, "unused.csv")


if __name__ == "__main__":
    unittest.main()
