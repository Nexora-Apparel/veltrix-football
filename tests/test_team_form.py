import unittest

from app.team_form import LegacyModelDisabled, summarize_team_form


class LegacyTeamFormQuarantineTests(unittest.TestCase):
    def test_legacy_team_form_feature_engine_is_disabled(self):
        with self.assertRaises(LegacyModelDisabled):
            summarize_team_form([], "Team A")


if __name__ == "__main__":
    unittest.main()
