import unittest

from app.prediction import LegacyModelDisabled, match_probabilities


class LegacyPredictionQuarantineTests(unittest.TestCase):
    def test_legacy_probability_head_is_disabled(self):
        with self.assertRaises(LegacyModelDisabled):
            match_probabilities(1.2, 0.9)


if __name__ == "__main__":
    unittest.main()
