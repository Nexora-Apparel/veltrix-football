import unittest

from app.provider_fixture_batch import process_observations


def striker(source_id="1", competition="soccer", kickoff="2026-11-10T18:00:00Z"):
    return {
        "provider": "strikerapi",
        "row": {
            "game_id": source_id, "starts_at": kickoff, "status": "final",
            "home": {"team_id": 10, "name": "Home", "score": 1},
            "away": {"team_id": 20, "name": "Away", "score": 0},
        },
        "options": {
            "competition_key": competition, "endpoint": "list_games",
            "retrieved_at": "2026-11-09T12:00:00Z", "run_id": "batch-1",
        },
    }


class ProviderFixtureBatchTests(unittest.TestCase):
    def test_valid_rows_are_accepted(self):
        result = process_observations([striker("1"), striker("2")])
        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(result["quarantined_count"], 0)
        self.assertTrue(result["acceptance_pass"])

    def test_duplicate_identity_quarantines_both_observations(self):
        result = process_observations([striker("same"), striker("same")])
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["quarantined_count"], 2)
        self.assertEqual(result["duplicate_identity_count"], 1)
        self.assertFalse(result["acceptance_pass"])

    def test_same_source_id_in_different_competitions_does_not_collide(self):
        result = process_observations([
            striker("same", "soccer"), striker("same", "ucl")
        ])
        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(result["quarantined_count"], 0)

    def test_invalid_timezone_is_quarantined_not_repaired(self):
        result = process_observations([striker("1", kickoff="2026-11-10T18:00:00")])
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["quarantined"][0]["reason"], "kickoff_timezone_missing")

    def test_non_object_input_is_quarantined(self):
        result = process_observations([None])
        self.assertEqual(result["quarantined_count"], 1)
        self.assertEqual(result["quarantined"][0]["reason"], "observation_not_object")

    def test_quarantine_does_not_retain_raw_provider_payload(self):
        raw = striker("bad")
        raw["row"]["private_provider_field"] = "raw-secret-like-value"
        raw["row"]["starts_at"] = "not-a-timestamp"
        result = process_observations([raw])
        rendered = str(result["quarantined"])
        self.assertNotIn("raw-secret-like-value", rendered)
        self.assertIn("payload_sha256", rendered)

    def test_accepted_rows_carry_recomputable_raw_source_evidence(self):
        result = process_observations([striker("evidence-row")])
        record = result["accepted"][0]
        self.assertEqual(record["source_evidence"]["raw_payload"]["game_id"], "evidence-row")
        self.assertEqual(
            record["source_evidence"]["raw_payload_sha256"], record["payload_sha256"]
        )
        self.assertEqual(
            record["source_evidence"]["normalized_record"]["source_id"], "evidence-row"
        )

    def test_report_proves_no_side_effects(self):
        result = process_observations([striker()])
        self.assertEqual(result["database_writes"], 0)
        self.assertEqual(result["imports"], 0)
        self.assertEqual(result["canonical_merges"], 0)

    def test_duplicate_after_invalid_row_is_still_quarantined(self):
        result = process_observations([
            striker("dup", kickoff="not-a-date"),
            striker("dup"),
            striker("dup"),
        ])
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["duplicate_identity_count"], 1)
        self.assertEqual(result["quarantined_count"], 3)

    def test_all_rows_in_three_way_duplicate_group_are_quarantined(self):
        result = process_observations([
            striker("triple"), striker("triple"), striker("triple")
        ])
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["duplicate_identity_count"], 1)
        self.assertEqual(result["quarantined_count"], 3)
        self.assertTrue(all(item["source"] is not None for item in result["quarantined"]))


if __name__ == "__main__":
    unittest.main()
