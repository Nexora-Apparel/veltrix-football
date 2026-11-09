import unittest

from scripts.audit_provider_team_crosswalk import audit_crosswalk


def fixture(source_id, home_id, home, away_id, away, kickoff):
    return {
        "source_id": source_id, "home_id": str(home_id), "home": home,
        "away_id": str(away_id), "away": away, "kickoff": kickoff,
    }


class AnchoredCrosswalkTests(unittest.TestCase):
    def report(self):
        # One strict exact-name match establishes the anchor club IDs.
        strict_s = fixture("s0", 10, "Anchor FC", 20, "Known FC", "2026-08-01T12:00:00Z")
        strict_d = fixture("d0", 110, "Anchor FC", 120, "Known FC", "2026-08-01T12:00:00+00:00")
        # Two different opponents are mapped only because the anchor ID is
        # already proven and kickoff/home-away position agrees.
        s1 = fixture("s1", 10, "Anchor FC", 30, "Candidate FC", "2026-08-08T12:00:00Z")
        d1 = fixture("d1", 110, "Anchor FC", 130, "Candidate", "2026-08-08T12:00:00+00:00")
        s2 = fixture("s2", 40, "Other Candidate", 10, "Anchor FC", "2026-08-15T12:00:00Z")
        d2 = fixture("d2", 140, "Other Candidate", 110, "Anchor FC", "2026-08-15T12:00:00+00:00")
        s3 = fixture("s3", 50, "Third Candidate", 10, "Anchor FC", "2026-08-22T12:00:00Z")
        d3 = fixture("d3", 150, "Third Candidate", 110, "Anchor FC", "2026-08-22T12:00:00+00:00")
        return {
            "schema_version": 1, "mode": "read_only_no_merge",
            "decisions": [
                {"outcome": "MATCHED_UNIQUE", "striker": strict_s, "fivedollar": strict_d},
                *[
                    {"outcome": "UNMATCHED_STRIKER_ONLY", "striker": x, "fivedollar": None}
                    for x in (s1, s2, s3)
                ],
                *[
                    {"outcome": "UNMATCHED_5DOLLAR_ONLY", "striker": None, "fivedollar": x}
                    for x in (d1, d2, d3)
                ],
            ],
        }

    def test_infers_team_pairs_from_repeated_known_opponent_anchor(self):
        result = audit_crosswalk(self.report(), minimum_support=2)
        pairs = {(x["striker_team_id"], x["fivedollar_team_id"]) for x in result["crosswalks"]}
        self.assertIn(("30", "130"), pairs)
        self.assertIn(("40", "140"), pairs)
        self.assertIn(("50", "150"), pairs)
        self.assertEqual(result["anchored_fixture_pairs_used"], 3)
        self.assertTrue(result["all_crosswalks_repeatedly_supported"])

    def test_does_not_infer_from_unanchored_same_kickoff(self):
        report = self.report()
        for x in report["decisions"]:
            if x["outcome"] == "MATCHED_UNIQUE":
                x["outcome"] = "UNMATCHED_STRIKER_ONLY"
                x["fivedollar"] = None
        result = audit_crosswalk(report, minimum_support=2)
        self.assertEqual(result["crosswalk_team_count"], 0)
        self.assertEqual(result["anchored_fixture_pairs_used"], 0)

    def test_wrong_orientation_does_not_create_crosswalk(self):
        report = self.report()
        for x in report["decisions"]:
            if x["outcome"] == "UNMATCHED_5DOLLAR_ONLY" and x["fivedollar"]["source_id"] == "d1":
                x["fivedollar"]["home_id"], x["fivedollar"]["away_id"] = (
                    x["fivedollar"]["away_id"], x["fivedollar"]["home_id"]
                )
        result = audit_crosswalk(report, minimum_support=2)
        self.assertNotIn(("30", "130"), {
            (x["striker_team_id"], x["fivedollar_team_id"]) for x in result["crosswalks"]
        })

    def test_timezone_offsets_are_normalized(self):
        result = audit_crosswalk(self.report(), minimum_support=2)
        self.assertEqual(result["anchored_fixture_pairs_used"], 3)

    def test_registry_and_production_are_never_modified(self):
        result = audit_crosswalk(self.report(), minimum_support=2)
        self.assertFalse(result["production_registry_modified"])
        self.assertEqual(result["database_writes"], 0)
        self.assertEqual(result["imports"], 0)
        self.assertEqual(result["canonical_merges"], 0)


if __name__ == "__main__":
    unittest.main()
