import hashlib
import unittest

from app.chronological_training_dataset import (
    ChronologicalDatasetError,
    assemble_chronological_training_dataset,
    validate_chronological_training_dataset,
)
from app.point_in_time_feature_contract import build_point_in_time_feature_snapshot


POLICY = {
    "train_end_date": "2026-10-01",
    "validation_start_date": "2026-10-09",
    "validation_end_date": "2026-10-20",
    "test_start_date": "2026-10-28",
    "test_end_date": "2026-11-09",
    "embargo_days": 7,
}


def sample(fixture_id, kickoff, scores=(2, 1)):
    kickoff_day = kickoff[:10]
    as_of = f"{kickoff_day}T05:00:00Z"
    snapshot = build_point_in_time_feature_snapshot(
        fixture_id=fixture_id,
        prediction_as_of=as_of,
        features=[{
            "name": "home_team_elo",
            "value": 1500.0,
            "source": "veltrix_elo",
            "source_id": f"elo-{fixture_id}",
            "observed_at": f"{kickoff_day}T04:00:00Z",
            "available_at": f"{kickoff_day}T04:00:00Z",
            "retrieved_at": f"{kickoff_day}T04:05:00Z",
            "payload_sha256": "a" * 64,
        }],
    )
    from datetime import datetime, timedelta, timezone
    start = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    settled = (start + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    retrieved = (start + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    label = {
        "fixture_id": fixture_id,
        "competition_key": "4160026622",
        "kickoff_at": kickoff,
        "settled_at": settled,
        "home_score": scores[0],
        "away_score": scores[1],
        "label_source": "fivedollar",
        "label_source_id": f"result-{fixture_id}",
        "label_retrieved_at": retrieved,
        "payload_sha256": "b" * 64,
    }
    return snapshot, label


class ChronologicalDatasetTests(unittest.TestCase):
    def setUp(self):
        pairs = [
            sample("train-1", "2026-09-15T12:00:00Z", (2, 1)),
            sample("validation-1", "2026-10-15T12:00:00Z", (0, 0)),
            sample("test-1", "2026-11-05T12:00:00Z", (1, 2)),
        ]
        self.snapshots = [pair[0] for pair in pairs]
        self.labels = [pair[1] for pair in pairs]

    def test_builds_strict_chronological_train_validation_test_splits(self):
        dataset = assemble_chronological_training_dataset(
            snapshots=self.snapshots, settled_labels=self.labels, split_policy=POLICY,
        )
        verified = validate_chronological_training_dataset(dataset)
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["counts_by_split"], {
            "train": 1, "validation": 1, "test": 1,
        })
        self.assertEqual(dataset["rows"][0]["split"], "train")
        self.assertEqual(dataset["rows"][1]["split"], "validation")
        self.assertEqual(dataset["rows"][2]["split"], "test")
        self.assertFalse(verified["ready_for_model_training"])
        self.assertTrue(dataset["quality"]["target_labels_separate_from_predictors"])

    def test_embargo_windows_must_be_respected(self):
        bad = dict(POLICY, validation_start_date="2026-10-05")
        with self.assertRaisesRegex(ChronologicalDatasetError, "embargo_not_respected"):
            assemble_chronological_training_dataset(
                snapshots=self.snapshots, settled_labels=self.labels, split_policy=bad,
            )

    def test_prediction_cutoff_must_precede_kickoff(self):
        snapshots = list(self.snapshots)
        bad = build_point_in_time_feature_snapshot(
            fixture_id="train-1",
            prediction_as_of="2026-09-15T12:00:00Z",
            features=[{
                "name": "home_team_elo", "value": 1500,
                "source": "elo", "source_id": "elo-1",
                "observed_at": "2026-09-15T11:00:00Z",
                "available_at": "2026-09-15T11:00:00Z",
                "retrieved_at": "2026-09-15T11:05:00Z",
                "payload_sha256": "a" * 64,
            }],
        )
        snapshots[0] = bad
        with self.assertRaisesRegex(ChronologicalDatasetError, "cutoff_not_before_kickoff"):
            assemble_chronological_training_dataset(
                snapshots=snapshots, settled_labels=self.labels, split_policy=POLICY,
            )

    def test_labels_must_be_retrieved_after_settlement(self):
        labels = [dict(row) for row in self.labels]
        labels[0]["label_retrieved_at"] = "2026-09-15T13:00:00Z"
        with self.assertRaisesRegex(ChronologicalDatasetError, "temporal_order_invalid"):
            assemble_chronological_training_dataset(
                snapshots=self.snapshots, settled_labels=labels, split_policy=POLICY,
            )

    def test_one_to_one_snapshot_label_join_is_required(self):
        with self.assertRaisesRegex(ChronologicalDatasetError, "join_not_one_to_one"):
            assemble_chronological_training_dataset(
                snapshots=self.snapshots, settled_labels=self.labels[:-1], split_policy=POLICY,
            )

    def test_dataset_hash_tampering_is_rejected(self):
        dataset = assemble_chronological_training_dataset(
            snapshots=self.snapshots, settled_labels=self.labels, split_policy=POLICY,
        )
        dataset["rows"][0]["targets"]["1x2"] = "away"
        with self.assertRaisesRegex(ChronologicalDatasetError, "hash_mismatch"):
            validate_chronological_training_dataset(dataset)


if __name__ == "__main__":
    unittest.main()
