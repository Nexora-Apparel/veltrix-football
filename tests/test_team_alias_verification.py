import unittest

from scripts.verify_strikerapi_team_aliases import (
    CANDIDATES, build_report, unwrap_dollar, unwrap_striker, ProbeError, striker_request_body, MAX_PROVIDER_CALLS,
)


class TeamAliasVerificationTests(unittest.TestCase):
    def test_striker_request_uses_only_documented_season_parameter(self):
        self.assertEqual(striker_request_body(), {"season": 2026})
        self.assertEqual(MAX_PROVIDER_CALLS, 21)

    def test_striker_catalogue_unwraps_rest_envelope(self):
        rows = [{"team_id": "360", "name": "Manchester United"}]
        self.assertEqual(unwrap_striker({"data": {"teams": rows}}), rows)

    def test_striker_catalogue_rejects_missing_teams(self):
        with self.assertRaises(ProbeError):
            unwrap_striker({"data": {}})

    def test_fivedollar_catalogue_requires_expected_id(self):
        self.assertEqual(
            unwrap_dollar({"success": 1, "data": {"id": 762247077, "name": "Man Utd"}}, "762247077")["name"],
            "Man Utd",
        )
        with self.assertRaises(ProbeError):
            unwrap_dollar({"success": 1, "data": {"id": 1, "name": "Wrong"}}, "762247077")

    def test_all_provider_catalogue_pairs_are_reported(self):
        striker = [
            {"team_id": sid, "name": f"Striker {sid}", "short_name": f"S{sid}"}
            for sid, _ in CANDIDATES
        ]
        dollar = {
            did: {"id": int(did), "name": f"Dollar {did}"}
            for _, did in CANDIDATES
        }
        report = build_report(striker, dollar)
        self.assertEqual(report["candidate_count"], 20)
        self.assertEqual(report["verified_count"], 20)
        self.assertTrue(report["all_candidates_verified"])
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["canonical_merges"], 0)

    def test_missing_provider_team_is_not_verified(self):
        report = build_report([], {})
        self.assertEqual(report["verified_count"], 0)
        self.assertFalse(report["all_candidates_verified"])
        self.assertTrue(all(x["status"] == "NOT_VERIFIED" for x in report["candidates"]))


if __name__ == "__main__":
    unittest.main()
