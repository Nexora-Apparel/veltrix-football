import unittest

from app.prospective_result_collector import (
    ProspectiveCollectorError, collect_fivedollar_observations,
    merge_collected_observations,
)


COMPETITION = "4160026622"


class ProspectiveResultCollectorTests(unittest.TestCase):
    def row(self, source_id, status, competition=COMPETITION):
        return {
            "id": source_id,
            "status": status,
            "league": {"id": int(competition)},
            "goals": {"home": 1, "away": 0},
        }

    def collect(self, rows):
        return collect_fivedollar_observations(
            response_rows=rows, competition_id=COMPETITION,
            endpoint="leagues/4160026622/fixtures", run_id="run-2026-11-10-01",
            observed_at="2026-11-10T14:00:00Z",
        )

    def test_collects_scheduled_and_finished_states(self):
        result = self.collect([self.row(1, "scheduled"), self.row(2, "finished")])
        self.assertEqual(result["observation_count"], 2)
        self.assertEqual(result["terminal_result_count"], 1)
        self.assertEqual(result["provider_requests_made"], 0)
        self.assertEqual(result["settlement_timestamps_created"], 0)

    def test_unqualified_competition_rejected(self):
        with self.assertRaisesRegex(ProspectiveCollectorError, "competition_not_qualified"):
            collect_fivedollar_observations(
                response_rows=[], competition_id="999", endpoint="fixtures",
                run_id="run", observed_at="2026-11-10T14:00:00Z",
            )

    def test_cross_competition_rows_are_quarantined(self):
        result = self.collect([self.row(1, "finished", "3405541143")])
        self.assertEqual(result["observation_count"], 0)
        self.assertEqual(result["rejected"][0]["reason"], "competition_scope_mismatch")

    def test_duplicate_ids_and_unexpected_status_are_rejected(self):
        result = self.collect([
            self.row(1, "scheduled"), self.row(1, "finished"),
            self.row(2, "in_play"),
        ])
        self.assertEqual(result["observation_count"], 1)
        self.assertEqual(result["rejected_count"], 2)
        self.assertEqual(
            {item["reason"] for item in result["rejected"]},
            {"duplicate_source_id", "status_not_collectable"},
        )

    def test_merge_into_ledger_is_idempotent(self):
        collection = self.collect([self.row(1, "finished")])
        empty = {"schema_version": 1, "observations": []}
        first = merge_collected_observations(ledger=empty, collection=collection)
        second = merge_collected_observations(ledger=first["ledger"], collection=collection)
        self.assertEqual(first["added_count"], 1)
        self.assertEqual(second["added_count"], 0)
        self.assertEqual(second["total_observation_count"], 1)

    def test_merge_rejects_tampered_collection_scope(self):
        collection = self.collect([self.row(1, "finished")])
        collection["competition_id"] = "999"
        with self.assertRaisesRegex(ProspectiveCollectorError, "competition_not_qualified"):
            merge_collected_observations(
                ledger={"schema_version": 1, "observations": []}, collection=collection
            )


if __name__ == "__main__":
    unittest.main()
