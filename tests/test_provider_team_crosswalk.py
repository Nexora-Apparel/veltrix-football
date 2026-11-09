import unittest

from scripts.audit_provider_team_crosswalk import audit_crosswalk


def fixture(source_id, home_id, home, away_id, away, kickoff):
    return {
        "source_id": source_id, "home_id": str(home_id), "home": home,
        "away_id": str(away_id), "away": away, "kickoff": kickoff,
    }


class AnchoredCrosswalkTests(unittest.TestCase):
    def report(self):
        strict_s1 = fixture("s0", 10, "Anchor FC", 20, "Known FC", "2026-08-01T12:00:00Z")
        strict_d1 = fixture("d0", 110, "Anchor FC", 120, "Known FC", "2026-08-01T12:00:00+00:00")
        strict_s2 = fixture("s9", 11, "Second Anchor", 21, "Known Two", "2026-08-02T12:00:00Z")
        strict_d2 = fixture("d9", 111, "Second Anchor", 121, "Known Two", "2026-08-02T12:00:00+00:00")
        # Candidate club appears twice, anchored by two already strict-matched clubs.
        s1 = fixture("s1", 10, "Anchor FC", 30, "Candidate FC", "2026-08-08T12:00:00Z")
        d1 = fixture("d1", 110, "Anchor FC", 130, "Candidate", "2026-08-08T12:00:00+00:00")
        s2 = fixture("s2", 30, "Candidate FC", 11, "Second Anchor", "2026-08-15T12:00:00Z")
        d2 = fixture("d2", 130, "Candidate", 111, "Second Anchor", "2026-08-15T12:00:00+00:00")
        return {
            "schema_version": 1, "mode": "read_only_no_merge",
            "decisions": [
                {"outcome": "MATCHED_UNIQUE", "striker": strict_s1, "fivedollar": strict_d1},
                {"outcome": "MATCHED_UNIQUE", "striker": strict_s2, "fivedollar": strict_d2},
                {"outcome": "UNMATCHED_STRIKER_ONLY", "striker": s1, "fivedollar": None},
                {"outcome": "UNMATCHED_STRIKER_ONLY", "striker": s2, "fivedollar": None},
                {"outcome": "UNMATCHED_5DOLLAR_ONLY", "striker": None, "fivedollar": d1},
                {"outcome": "UNMATCHED_5DOLLAR_ONLY", "striker": None, "fivedollar": d2},
            ],
        }

    def test_infers_pair_from_two_independent_strict_anchors(self):
        result = audit_crosswalk(self.report(), minimum_support=2)
        pairs = {(x["striker_team_id"], x["fivedollar_team_id"]): x
                 for x in result["crosswalks"]}
        self.assertIn(("30", "130"), pairs)
        self.assertEqual(pairs[("30", "130")]["anchored_crosswalk_fixture_count"], 2)
        self.assertEqual(pairs[("30", "130")]["status"],
                         "REPEATED_ANCHORED_CROSSWALK_SUPPORTED")
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
        candidate = next(
            x for x in result["crosswalks"]
            if (x["striker_team_id"], x["fivedollar_team_id"]) == ("30", "130")
        )
        self.assertEqual(candidate["anchored_crosswalk_fixture_count"], 1)
        self.assertEqual(candidate["status"], "INSUFFICIENT_ANCHORED_SUPPORT")
        self.assertFalse(result["all_crosswalks_repeatedly_supported"])

    def test_timezone_offsets_are_normalized(self):
        result = audit_crosswalk(self.report(), minimum_support=2)
        self.assertEqual(result["anchored_fixture_pairs_used"], 2)

    def test_strict_matches_remain_seed_evidence(self):
        result = audit_crosswalk(self.report(), minimum_support=2)
        seeds = [x for x in result["crosswalks"] if x["strict_seed"]]
        self.assertEqual(len(seeds), 4)
        self.assertTrue(all(x["status"] == "STRICT_NAME_MATCH_SEED" for x in seeds))

    def test_registry_and_production_are_never_modified(self):
        result = audit_crosswalk(self.report(), minimum_support=2)
        self.assertFalse(result["production_registry_modified"])
        self.assertEqual(result["database_writes"], 0)
        self.assertEqual(result["imports"], 0)
        self.assertEqual(result["canonical_merges"], 0)


if __name__ == "__main__":
    unittest.main()
