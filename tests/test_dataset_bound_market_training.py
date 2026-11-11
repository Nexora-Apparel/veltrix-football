import unittest
from datetime import date, timedelta

from app.dataset_bound_market_training import (
    DatasetTrainingError,
    fit_models_from_chronological_dataset,
)
from app.chronological_training_dataset import assemble_chronological_training_dataset
from app.point_in_time_feature_contract import build_point_in_time_feature_snapshot
from app.independent_market_models import FEATURES, predict_independent_markets


POLICY = {
    "train_end_date": "2026-09-30",
    "validation_start_date": "2026-10-08",
    "validation_end_date": "2026-11-16",
    "test_start_date": "2026-11-24",
    "test_end_date": "2026-12-13",
    "embargo_days": 7,
}


def dataset_fixture(late_retrieval=False):
    snapshots, labels = [], []
    windows = [
        ("train", date(2026, 7, 20), 120, 1),
        ("validation", date(2026, 10, 8), 120, 1),
        ("test", date(2026, 11, 24), 20, 1),
    ]
    index = 0
    for split, start, count, step in windows:
        for offset in range(count):
            day = start + timedelta(days=(offset % 60) if split == "train" else (offset % 40) if split == "validation" else offset * step)
            kickoff = f"{day.isoformat()}T15:00:00Z"
            cutoff = f"{day.isoformat()}T09:00:00Z"
            observed = f"{(day - timedelta(days=1)).isoformat()}T09:00:00Z"
            digest = f"{index + 1:064x}"
            features = {
                "home_attack_goals_rate": 1.0 + (index % 5) * 0.2,
                "home_defence_conceded_rate": 0.8 + (index % 4) * 0.15,
                "away_attack_goals_rate": 0.9 + (index % 6) * 0.17,
                "away_defence_conceded_rate": 0.85 + (index % 3) * 0.2,
                "elo_difference_home": float((index % 9) * 80 - 320),
                "home_form_points_rate": (index % 10) / 10,
                "away_form_points_rate": ((index * 3) % 10) / 10,
                "home_rest_days": float(3 + index % 6),
                "away_rest_days": float(2 + (index * 2) % 7),
                "competition_home_goals_rate": 1.4 + (index % 3) * 0.1,
                "competition_away_goals_rate": 1.1 + (index % 4) * 0.08,
            }
            feature_rows = [{
                "name": name,
                "value": value,
                "source": "veltrix_test_source",
                "source_id": f"source-{index}",
                "observed_at": observed,
                "available_at": cutoff,
                "retrieved_at": cutoff,
                "payload_sha256": digest,
            } for name, value in features.items()]
            fixture_id = f"{split}-{index:04d}"
            snapshots.append(build_point_in_time_feature_snapshot(
                fixture_id=fixture_id, prediction_as_of=cutoff,
                features=feature_rows,
            ))
            home_score = (index * 3 + index // 4) % 4
            away_score = (index * 5 + index // 7) % 3
            labels.append({
                "fixture_id": fixture_id,
                "competition_key": "4160026622",
                "kickoff_at": kickoff,
                "settled_at": f"{day.isoformat()}T17:00:00Z",
                "home_score": home_score,
                "away_score": away_score,
                "label_source": "fivedollar",
                "label_source_id": f"result-{index}",
                "label_retrieved_at": (
                    "2026-10-02T01:00:00Z"
                    if late_retrieval and split == "train" and offset == 119
                    else f"{day.isoformat()}T18:00:00Z"
                ),
                "payload_sha256": digest,
            })
            index += 1
    return assemble_chronological_training_dataset(
        snapshots=snapshots, settled_labels=labels, split_policy=POLICY,
    )


class DatasetBoundTrainingTests(unittest.TestCase):
    def test_fits_train_split_only_and_binds_all_split_digests(self):
        dataset = dataset_fixture()
        result = fit_models_from_chronological_dataset(
            dataset=dataset, trained_at="2026-10-02T00:00:00Z", epochs=150,
        )
        model = result["model"]
        audit = result["training_audit"]
        self.assertEqual(audit["train_rows_used"], 120)
        self.assertEqual(audit["validation_rows_held_out"], 120)
        self.assertEqual(audit["test_rows_held_out"], 20)
        self.assertFalse(audit["validation_and_test_passed_to_optimizer"])
        self.assertEqual(model["training_dataset_sha256"], dataset["dataset_sha256"])
        self.assertEqual(set(model["training_split_manifest"]), {"train", "validation", "test"})
        self.assertFalse(model["publication_allowed"])
        self.assertFalse(model["value_betting_enabled"])
        row = next(row for row in dataset["rows"] if row["split"] == "test")
        prediction = predict_independent_markets(
            model=model, features=row["predictors"],
            prediction_as_of="2026-11-25T00:00:00Z",
        )
        self.assertEqual(prediction["model_sha256"], model["model_sha256"])

    def test_rejects_dataset_digest_tampering(self):
        dataset = dataset_fixture()
        dataset["rows"][0]["predictors"]["elo_difference_home"] += 1
        with self.assertRaisesRegex(DatasetTrainingError, "dataset_rejected"):
            fit_models_from_chronological_dataset(
                dataset=dataset, trained_at="2026-10-02T00:00:00Z", epochs=150,
            )


    def test_rejects_labels_retrieved_after_training_timestamp(self):
        dataset = dataset_fixture(late_retrieval=True)
        with self.assertRaisesRegex(
            DatasetTrainingError, "label_retrieved_after_model_training"
        ):
            fit_models_from_chronological_dataset(
                dataset=dataset, trained_at="2026-10-02T00:00:00Z", epochs=150,
            )

    def test_rejects_missing_holdout_partition(self):
        dataset = dataset_fixture()
        dataset["rows"] = [row for row in dataset["rows"] if row["split"] != "test"]
        # The hash is intentionally not resealed: the immutable dataset guard
        # must reject this before the trainer can inspect or fit any rows.
        with self.assertRaisesRegex(DatasetTrainingError, "dataset_rejected"):
            fit_models_from_chronological_dataset(
                dataset=dataset, trained_at="2026-10-02T00:00:00Z", epochs=150,
            )


if __name__ == "__main__":
    unittest.main()
