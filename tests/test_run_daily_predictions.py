import unittest

from scripts.run_daily_predictions import main


class LegacyDailyRunnerQuarantineTests(unittest.TestCase):
    def test_legacy_runner_exits_before_any_provider_or_publication_work(self):
        with self.assertRaisesRegex(SystemExit, "LEGACY_PREDICTION_PIPELINE_DISABLED"):
            main()


if __name__ == "__main__":
    unittest.main()
