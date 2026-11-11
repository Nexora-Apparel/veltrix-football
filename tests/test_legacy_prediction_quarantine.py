import unittest

from scripts.run_daily_predictions import main


class LegacyPredictionQuarantineTests(unittest.TestCase):
    def test_legacy_daily_prediction_cli_fails_closed_before_provider_access(self):
        with self.assertRaisesRegex(SystemExit, "LEGACY_PREDICTION_PIPELINE_DISABLED"):
            main()


if __name__ == "__main__":
    unittest.main()
