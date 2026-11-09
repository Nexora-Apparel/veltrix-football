import unittest

from scripts.reconcile_provider_fixtures import reconcile, normalize_name


def srow(source_id="s1", home="Arsenal", away="Chelsea", kickoff="2026-08-15T16:30:00Z",
         status="final", home_score=2, away_score=0):
    return {"provider":"strikerapi","source_id":source_id,"competition_key":"soccer",
            "home_id":"s-home","away_id":"s-away","home":home,"away":away,"kickoff":kickoff,
            "status":status,"home_score":home_score,"away_score":away_score,
            "payload_sha256":"a"*64}


def drow(source_id="d1", home="Arsenal", away="Chelsea", kickoff="2026-08-15T16:32:00+00:00",
         status="finished", home_score=2, away_score=0):
    return {"provider":"fivedollar","source_id":source_id,"competition_key":"39",
            "home_id":"d-home","away_id":"d-away","home":home,"away":away,"kickoff":kickoff,
            "status":status,"home_score":home_score,"away_score":away_score,
            "payload_sha256":"b"*64}


class ProviderReconciliationTests(unittest.TestCase):
    def test_normalization_is_conservative_and_unicode_aware(self):
        self.assertEqual(normalize_name("  ＡＲＳＥＮＡＬ FC "), "arsenal fc")
        self.assertNotEqual(normalize_name("Arsenal Women"), normalize_name("Arsenal"))

    def test_unique_pair_matches_within_five_minutes(self):
        report = reconcile([srow()], [drow()], {"soccer":"39"})
        self.assertEqual(report["decisions"][0]["outcome"], "MATCHED_UNIQUE")
        self.assertTrue(report["accounting"]["striker"]["balanced"])
        self.assertTrue(report["accounting"]["fivedollar"]["balanced"])
        self.assertTrue(report["acceptance_pass"])

    def test_score_conflict_quarantines_pair_and_fails_acceptance(self):
        report = reconcile([srow()], [drow(home_score=1)], {"soccer":"39"})
        self.assertEqual(report["decisions"][0]["outcome"], "RESULT_CONFLICT")
        self.assertEqual(report["accounting"]["striker"]["quarantined"], 1)
        self.assertFalse(report["acceptance_pass"])

    def test_status_conflict_quarantines_pair_and_fails_acceptance(self):
        report = reconcile([srow(status="final")], [drow(status="scheduled")], {"soccer":"39"})
        self.assertEqual(report["decisions"][0]["outcome"], "STATUS_CONFLICT")
        self.assertFalse(report["acceptance_pass"])

    def test_reversed_home_away_is_not_matched(self):
        report = reconcile([srow()], [drow(home="Chelsea", away="Arsenal")], {"soccer":"39"})
        self.assertEqual(report["decisions"][0]["outcome"], "IDENTITY_CONFLICT")
        self.assertFalse(report["acceptance_pass"])

    def test_outside_kickoff_tolerance_is_unmatched(self):
        report = reconcile([srow()], [drow(kickoff="2026-08-15T16:36:00Z")], {"soccer":"39"})
        outcomes = {x["outcome"] for x in report["decisions"]}
        self.assertEqual(outcomes, {"UNMATCHED_STRIKER_ONLY", "UNMATCHED_5DOLLAR_ONLY"})
        self.assertFalse(report["acceptance_pass"])

    def test_ambiguous_candidate_graph_is_quarantined(self):
        report = reconcile([srow()], [drow("d1"), drow("d2")], {"soccer":"39"})
        self.assertTrue(any(x["outcome"] == "AMBIGUOUS_MULTIPLE_CANDIDATES" for x in report["decisions"]))
        self.assertTrue(report["accounting"]["striker"]["balanced"])
        self.assertTrue(report["accounting"]["fivedollar"]["balanced"])
        self.assertFalse(report["acceptance_pass"])

    def test_duplicate_provider_ids_are_quarantined_and_block_acceptance(self):
        report = reconcile([srow("duplicate"), srow("duplicate")], [drow()], {"soccer":"39"})
        self.assertEqual(report["duplicate_source_ids"]["striker"], ["duplicate"])
        self.assertEqual(report["accounting"]["striker"]["quarantined"], 2)
        self.assertFalse(any(x["outcome"] == "MATCHED_UNIQUE" for x in report["decisions"]))
        self.assertFalse(report["acceptance_pass"])

    def test_competition_mapping_is_required_for_candidate(self):
        report = reconcile([srow()], [drow()], {})
        outcomes = {item["outcome"] for item in report["decisions"]}
        self.assertEqual(outcomes, {"UNMATCHED_STRIKER_ONLY", "UNMATCHED_5DOLLAR_ONLY"})
        self.assertFalse(report["acceptance_pass"])

    def test_missing_timezone_is_invalid_and_accounted(self):
        bad = srow(kickoff="2026-08-15T16:30:00")
        report = reconcile([bad], [drow()], {"soccer":"39"})
        self.assertEqual(report["decisions"][0]["outcome"], "INVALID_SOURCE_ROW")
        self.assertTrue(report["accounting"]["striker"]["balanced"])
        self.assertFalse(report["acceptance_pass"])

    def test_non_string_kickoff_is_invalid_not_exception(self):
        bad = srow(kickoff=1723749000)
        report = reconcile([bad], [drow()], {"soccer":"39"})
        self.assertEqual(report["decisions"][0]["outcome"], "INVALID_SOURCE_ROW")
        self.assertTrue(report["accounting"]["striker"]["balanced"])


if __name__ == "__main__":
    unittest.main()
