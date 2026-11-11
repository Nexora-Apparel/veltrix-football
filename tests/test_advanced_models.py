import unittest

from app.advanced_models import LegacyModelDisabled, dixon_coles_1x2, recency_weighted_mean


class LegacyAdvancedModelQuarantineTests(unittest.TestCase):
    def test_legacy_dixon_coles_head_is_disabled(self):
        with self.assertRaises(LegacyModelDisabled):
            dixon_coles_1x2(1.2, 0.9)

    def test_legacy_recency_weighted_mean_is_disabled(self):
        with self.assertRaises(LegacyModelDisabled):
            recency_weighted_mean([1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
