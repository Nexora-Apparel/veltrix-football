import unittest
from datetime import date, timedelta

from app.source_payload_provenance import canonical_payload_sha256
from app.results_training_dataset_adapter import (
    assemble_results_history_dataset,
    build_results_history_snapshot,
)


def attach_evidence(row):
    normalized = {key: row[key] for key in (
        "fixture_id", "competition_id", "kickoff_at", "settled_at",
        "home_team_id", "away_team_id", "home_score", "away_score",
        "normalized_status",
    )}
    payload = {"provider_fixture": dict(normalized), "source_version": 1}
    row["payload_sha256"] = canonical_payload_sha256(payload)
    row["source_payload"] = {
        "provider": row["provider"], "endpoint": row["endpoint"],
        "source_id": row["source_id"], "run_id": row["run_id"],
        "retrieved_at": row["retrieved_at"], "payload": payload,
        "payload_sha256": row["payload_sha256"],
        "normalized_record": normalized,
        "normalized_record_sha256": canonical_payload_sha256(normalized),
    }
    return row


def history_rows():
    pairings = [
        [("A", "B"), ("C", "D")],
        [("B", "C"), ("D", "A")],
        [("A", "C"), ("B", "D")],
        [("A", "D"), ("B", "C")],
        [("A", "B"), ("C", "D")],
        [("A", "C"), ("B", "D")],
    ]
    rows = []
    start = date(2026, 8, 1)
    for day_index, pair in enumerate(pairings):
        day = start + timedelta(days=day_index * 3)
        for match_index, (home, away) in enumerate(pair):
            hour = 12 + match_index * 3
            fixture_id = f"history-{day_index}-{match_index}"
            rows.append(attach_evidence({
                "fixture_id": fixture_id,
                "provider": "fivedollar",
                "source_id": fixture_id,
                "competition_id": "4160026622",
                "kickoff_at": f"{day.isoformat()}T{hour:02d}:00:00Z",
                "settled_at": f"{day.isoformat()}T{hour + 2:02d}:00:00Z",
                "home_team_id": home,
                "away_team_id": away,
                "home_score": (day_index + match_index) % 4,
                "away_score": (day_index * 2 + match_index + 1) % 3,
                "endpoint": "/fixtures",
                "retrieved_at": f"{day.isoformat()}T{hour + 3:02d}:00:00Z",
                "payload_sha256": "",
                "run_id": "history-acquisition-run-1",
                "normalized_status": "finished",
            }))
    return rows


TARGET = {
    "fixture_id": "target-2026-09-01",
    "competition_id": "4160026622",
    "kickoff_at": "2026-09-01T18:00:00Z",
    "home_team_id": "A",
    "away_team_id": "B",
}
LABEL = {
    "fixture_id": TARGET["fixture_id"],
    "competition_key": "4160026622",
    "kickoff_at": TARGET["kickoff_at"],
    "settled_at": "2026-09-01T20:00:00Z",
    "home_score": 2,
    "away_score": 1,
    "label_source": "fivedollar",
    "label_source_id": "result-target-2026-09-01",
    "label_retrieved_at": "2026-09-01T21:00:00Z",
    "payload_sha256": "f" * 64,
}
POLICY = {
    "train_end_date": "2026-09-30",
    "validation_start_date": "2026-10-08",
    "validation_end_date": "2026-10-20",
    "test_start_date": "2026-10-28",
    "test_end_date": "2026-11-30",
    "embargo_days": 7,
}


class ResultsTrainingDatasetAdapterTests(unittest.TestCase):
    def test_builds_pit_snapshot_with_reconstruction_source_provenance(self):
        snapshot = build_results_history_snapshot(
            historical_matches=history_rows(), target_fixture=TARGET,
        )
        self.assertEqual(snapshot["fixture_id"], TARGET["fixture_id"])
        self.assertEqual(snapshot["feature_count"], 11)
        self.assertTrue(all(
            feature["source"] == "veltrix_results_feature_reconstruction"
            for feature in snapshot["features"]
        ))
        self.assertTrue(all(
            feature["retrieved_at"] <= snapshot["prediction_as_of"]
            for feature in snapshot["features"]
        ))

    def test_assembles_snapshot_and_settled_label_into_chronological_dataset(self):
        result = assemble_results_history_dataset(
            historical_matches=history_rows(),
            target_fixtures=[TARGET],
            settled_labels=[LABEL],
            split_policy=POLICY,
        )
        self.assertEqual(result["feature_reconstruction"]["snapshot_count"], 1)
        self.assertEqual(result["dataset"]["quality"]["included_fixture_count"], 1)
        self.assertEqual(result["dataset"]["rows"][0]["split"], "train")
        self.assertFalse(result["dataset"]["training_readiness"]["ready_for_model_training"])
        self.assertEqual(result["feature_reconstruction"]["database_writes"], 0)

    def test_withholds_history_retrieved_after_target_feature_cutoff(self):
        history = history_rows()
        for row in history:
            if "A" in (row["home_team_id"], row["away_team_id"]):
                row["retrieved_at"] = "2026-09-01T13:00:00Z"
                attach_evidence(row)
        result = assemble_results_history_dataset(
            historical_matches=history,
            target_fixtures=[TARGET],
            settled_labels=[LABEL],
            split_policy=POLICY,
        )
        self.assertEqual(result["feature_reconstruction"]["snapshot_count"], 0)
        self.assertEqual(result["feature_reconstruction"]["withheld_count"], 1)
        self.assertEqual(result["dataset"]["quality"]["included_fixture_count"], 0)


if __name__ == "__main__":
    unittest.main()
