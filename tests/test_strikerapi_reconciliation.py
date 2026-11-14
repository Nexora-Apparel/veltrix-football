import unittest
from pathlib import Path

from app.provider_team_aliases import load_registry
from scripts.reconcile_provider_fixtures import reconcile, normalize_name


def srow(source_id="s1", home="Arsenal", away="Chelsea", kickoff="2026-08-15T16:30:00Z",
         status="final", home_score=2, away_score=0, home_id="s-home", away_id="s-away"):
    return {"provider":"strikerapi","source_id":source_id,"competition_key":"soccer",
            "home_id":home_id,"away_id":away_id,"home":home,"away":away,"kickoff":kickoff,
            "status":status,"home_score":home_score,"away_score":away_score,
            "payload_sha256":"a"*64}


def drow(source_id="d1", home="Arsenal", away="Chelsea", kickoff="2026-08-15T16:32:00+00:00",
         status="finished", home_score=2, away_score=0, home_id="d-home", away_id="d-away"):
    return {"provider":"fivedollar","source_id":source_id,"competition_key":"39",
            "home_id":home_id,"away_id":away_id,"home":home,"away":away,"kickoff":kickoff,
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

    def test_unmapped_competition_never_creates_cross_league_match(self):
        report = reconcile([srow()], [drow()], {"soccer":"999999"})
        self.assertEqual(report["accounting"]["striker"]["matched"], 0)
        self.assertEqual(report["accounting"]["fivedollar"]["matched"], 0)
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

    def test_approved_aliases_match_only_exact_scoped_team_ids(self):
        registry = load_registry(Path("data/provider_team_aliases.json"))
        report = reconcile(
            [srow(home="Manchester United", away="Hull City", home_id="360", away_id="306")],
            [drow(home="Man Utd", away="Hull", home_id="762247077", away_id="2133281510")],
            {"soccer":"39"},
            alias_registry=registry,
            alias_competition_key="england_premier_league",
            season="2026-27",
        )
        self.assertTrue(report["acceptance_pass"])
        self.assertEqual(report["decisions"][0]["outcome"], "MATCHED_UNIQUE")
        self.assertEqual(report["decisions"][0]["identity_evidence"],
                         {"home":"approved_alias", "away":"approved_alias"})
        self.assertEqual(report["alias_usage"]["alias_matched_fixture_count"], 1)
        self.assertEqual(len(report["alias_usage"]["team_pair_uses"]), 2)

    def test_approved_aliases_do_not_cross_season_or_competition(self):
        registry = load_registry(Path("data/provider_team_aliases.json"))
        base = {
            "alias_registry": registry,
            "alias_competition_key": "england_premier_league",
        }
        s = [srow(home="Manchester United", away="Hull City", home_id="360", away_id="306")]
        d = [drow(home="Man Utd", away="Hull", home_id="762247077", away_id="2133281510")]
        wrong_season = reconcile(s, d, {"soccer":"39"}, season="2025-26", **base)
        wrong_competition = reconcile(
            s, d, {"soccer":"39"}, season="2026-27",
            alias_competition_key="england_championship", alias_registry=registry,
        )
        self.assertEqual(wrong_season["accounting"]["striker"]["matched"], 0)
        self.assertEqual(wrong_competition["accounting"]["striker"]["matched"], 0)

    def test_review_only_registry_cannot_authorize_alias(self):
        registry = load_registry(Path("data/provider_team_aliases.json"))
        registry["status"] = "review_only"
        report = reconcile(
            [srow(home="Manchester United", away="Hull City", home_id="360", away_id="306")],
            [drow(home="Man Utd", away="Hull", home_id="762247077", away_id="2133281510")],
            {"soccer":"39"},
            alias_registry=registry,
            alias_competition_key="england_premier_league",
            season="2026-27",
        )
        self.assertEqual(report["accounting"]["striker"]["matched"], 0)
        self.assertFalse(report["acceptance_pass"])

    def test_alias_registry_requires_explicit_scope(self):
        registry = load_registry(Path("data/provider_team_aliases.json"))
        with self.assertRaises(ValueError):
            reconcile([srow()], [drow()], {"soccer":"39"}, alias_registry=registry)


if __name__ == "__main__":
    unittest.main()
