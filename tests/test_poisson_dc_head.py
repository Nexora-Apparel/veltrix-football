import unittest

from app.poisson_dc_head import LegacyModelDisabled, dixon_coles_markets


class LegacyPoissonHeadQuarantineTests(unittest.TestCase):
    def test_legacy_poisson_dixon_coles_head_is_disabled(self):
        with self.assertRaises(LegacyModelDisabled):
            dixon_coles_markets(1.2, 0.9)


if __name__ == "__main__":
    unittest.main()
