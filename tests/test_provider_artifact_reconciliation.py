import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.provider_acquisition_report import build_acquisition_report
from app.provider_artifact_reconciliation import reconcile_artifact_files, reconcile_artifact_records
from app.provider_team_aliases import load_registry


def row(provider, source_id, competition, home_id="sh", away_id="sa",
        home="Arsenal", away="Chelsea", season="2026-27",
        kickoff="2026-08-15T16:30:00Z", status="finished", hs=2, aws=0):
    return {
        "schema_version": 1, "provider": provider, "source_id": source_id,
        "competition_key": competition, "season": season,
        "home_team_source_id": home_id, "away_team_source_id": away_id,
        "home_team_name": home, "away_team_name": away,
        "kickoff_at": kickoff, "source_status": status, "normalized_status": status,
        "home_score": hs, "away_score": aws, "endpoint": "/fixtures",
        "retrieved_at": "2026-11-09T00:00:00Z", "payload_sha256": "a" * 64,
        "run_id": "test-run",
    }


class ArtifactReconciliationTests(unittest.TestCase):
    def test_exact_identity_and_utc_kickoff_match(self):
        s = row("strikerapi", "s1", "soccer")
        d = row("fivedollar", "d1", "39", home_id="dh", away_id="da",
                kickoff="2026-08-15T17:30:00+01:00")
        result = reconcile_artifact_records([s], [d], {"soccer": "39"})
        self.assertTrue(result["acceptance_pass"])
        self.assertEqual(result["counts"]["striker"]["matched"], 1)

    def test_approved_alias_matches_only_scoped_ids(self):
        registry = load_registry(Path("data/provider_team_aliases.json"))
        s = row("strikerapi", "s1", "soccer", "360", "306",
                "Manchester United", "Hull City")
        d = row("fivedollar", "d1", "39", "762247077", "2133281510",
                "Man Utd", "Hull")
        result = reconcile_artifact_records(
            [s], [d], {"soccer": "39"}, alias_registry=registry,
            alias_competition_key="england_premier_league", season="2026-27")
        self.assertTrue(result["acceptance_pass"])
        self.assertEqual(result["decisions"][0]["identity_evidence"],
                         {"home": "approved_alias", "away": "approved_alias"})

    def test_alias_cannot_cross_season(self):
        registry = load_registry(Path("data/provider_team_aliases.json"))
        s = row("strikerapi", "s1", "soccer", "360", "306",
                "Manchester United", "Hull City", season="2025-26")
        d = row("fivedollar", "d1", "39", "762247077", "2133281510",
                "Man Utd", "Hull", season="2025-26")
        result = reconcile_artifact_records(
            [s], [d], {"soccer": "39"}, alias_registry=registry,
            alias_competition_key="england_premier_league", season="2025-26")
        self.assertEqual(result["counts"]["striker"]["matched"], 0)

    def test_reversed_orientation_is_quarantined(self):
        s = row("strikerapi", "s1", "soccer")
        d = row("fivedollar", "d1", "39", home="Chelsea", away="Arsenal")
        result = reconcile_artifact_records([s], [d], {"soccer": "39"})
        self.assertEqual(result["decisions"][0]["outcome"], "IDENTITY_CONFLICT")
        self.assertFalse(result["acceptance_pass"])

    def test_kickoff_mismatch_is_unmatched(self):
        s = row("strikerapi", "s1", "soccer")
        d = row("fivedollar", "d1", "39", kickoff="2026-08-15T16:30:01Z")
        result = reconcile_artifact_records([s], [d], {"soccer": "39"})
        self.assertEqual(result["counts"]["striker"]["unmatched"], 1)
        self.assertEqual(result["counts"]["fivedollar"]["unmatched"], 1)

    def test_score_and_status_conflicts_are_quarantined(self):
        s = row("strikerapi", "s1", "soccer")
        d = row("fivedollar", "d1", "39", hs=1)
        result = reconcile_artifact_records([s], [d], {"soccer": "39"})
        self.assertEqual(result["decisions"][0]["outcome"], "RESULT_CONFLICT")
        d2 = row("fivedollar", "d2", "39", status="scheduled", hs=None, aws=None)
        result2 = reconcile_artifact_records([s], [d2], {"soccer": "39"})
        self.assertEqual(result2["decisions"][0]["outcome"], "STATUS_CONFLICT")

    def test_ambiguous_candidates_quarantine_all_involved_rows(self):
        s = row("strikerapi", "s1", "soccer")
        d1 = row("fivedollar", "d1", "39")
        d2 = row("fivedollar", "d2", "39")
        result = reconcile_artifact_records([s], [d1, d2], {"soccer": "39"})
        self.assertEqual(result["counts"]["striker"]["quarantined"], 1)
        self.assertEqual(result["counts"]["fivedollar"]["quarantined"], 2)
        self.assertTrue(all(x["balanced"] for x in result["counts"].values()))

    def test_duplicate_source_ids_quarantined(self):
        s = row("strikerapi", "s1", "soccer")
        result = reconcile_artifact_records([s, copy.deepcopy(s)], [row("fivedollar", "d1", "39")],
                                            {"soccer": "39"})
        self.assertEqual(result["counts"]["striker"]["quarantined"], 2)
        self.assertFalse(result["acceptance_pass"])

    def test_no_fuzzy_team_matching(self):
        s = row("strikerapi", "s1", "soccer", home="Arsenal Women")
        d = row("fivedollar", "d1", "39", home="Arsenal")
        result = reconcile_artifact_records([s], [d], {"soccer": "39"})
        self.assertEqual(result["counts"]["striker"]["matched"], 0)

    def test_competition_and_season_isolation(self):
        s = row("strikerapi", "s1", "soccer")
        d = row("fivedollar", "d1", "wrong")
        result = reconcile_artifact_records([s], [d], {"soccer": "39"})
        self.assertEqual(result["counts"]["striker"]["matched"], 0)
        d2 = row("fivedollar", "d2", "39", season="2025-26")
        result2 = reconcile_artifact_records([s], [d2], {"soccer": "39"})
        self.assertEqual(result2["counts"]["striker"]["matched"], 0)

    def test_artifact_hash_tampering_is_rejected(self):
        srow = row("strikerapi", "s1", "soccer")
        drow = row("fivedollar", "d1", "39")
        def report(provider, record):
            return build_acquisition_report(
                run_id=provider + "-run", provider_scope=[provider],
                competition_scope=[record["competition_key"]], window={},
                retrieved_at="2026-11-09T00:00:00Z",
                batch_result={"accepted": [record], "quarantined": [],
                              "input_count": 1, "acceptance_pass": True})
        with tempfile.TemporaryDirectory() as tmp:
            sp, dp, mp = (Path(tmp) / name for name in ("s.json", "d.json", "map.json"))
            sreport, dreport = report("strikerapi", srow), report("fivedollar", drow)
            sreport["records"][0]["home_team_name"] = "Tampered"
            sp.write_text(json.dumps(sreport), encoding="utf-8")
            dp.write_text(json.dumps(dreport), encoding="utf-8")
            mp.write_text(json.dumps({"soccer": "39"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                reconcile_artifact_files(str(sp), str(dp), str(mp))

    def test_report_is_deterministic_and_declares_zero_side_effects(self):
        s, d = row("strikerapi", "s1", "soccer"), row("fivedollar", "d1", "39")
        first = reconcile_artifact_records([s], [d], {"soccer": "39"})
        second = reconcile_artifact_records([s], [d], {"soccer": "39"})
        self.assertEqual(first, second)
        self.assertEqual(first["side_effects"]["database_writes"], 0)
        self.assertEqual(first["side_effects"]["network_requests"], 0)


if __name__ == "__main__":
    unittest.main()
