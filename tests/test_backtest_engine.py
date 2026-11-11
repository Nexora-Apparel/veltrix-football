import unittest

from app.backtest_engine import LegacyBacktestDisabled, chronological_backtest, write_report


class LegacyBacktestQuarantineTests(unittest.TestCase):
    def test_legacy_backtest_cannot_run(self):
        with self.assertRaises(LegacyBacktestDisabled):
            chronological_backtest([])

    def test_legacy_backtest_cannot_write_reports(self):
        with self.assertRaises(LegacyBacktestDisabled):
            write_report({}, "unused.json")


if __name__ == "__main__":
    unittest.main()
