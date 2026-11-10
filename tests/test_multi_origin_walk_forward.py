import unittest
from datetime import date, timedelta

from app.multi_origin_walk_forward import (
    WalkForwardEvaluationError,
    evaluate_multi_origin_walk_forward,
)
from app.chronological_training_dataset import assemble_chronological_training_dataset
from app.point_in_time_feature_contract import build_point_in_time_feature_snapshot


def walk_forward_dataset():
    snapshots, labels = [], []
    windows = [
        (date(2026, 6, 1), date(2026, 6, 30), 4),
        (date(2026, 7, 8), date(2026, 8, 16), 3),
        (date(2026, 8, 24), date(2026, 9, 22), 1),
        (date(2026, 8, 24), date(2026, 10, 2), 3),
        (date(2026, 10, 10), date(2026, 11, 8), 1),
    ]
    index = 0
    for start, end, per_day in windows:
        day = start
        while day <= end:
            for _ in range(per_day):
                kickoff = f"{day.isoformat()}T15:00:00Z"
                cutoff = f"{day.isoformat()}T09:00:00Z"
                observed = f"{(day - timedelta(days=1)).isoformat()}T09:00:00Z"
                digest = f"{index + 1:064x}"
                values = {
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
                    "name": name, "value": value, "source": "test-source",
                    "source_id": f"source-{index}", "observed_at": observed,
                    "available_at": cutoff, "retrieved_at": cutoff,
                    "payload_sha256": digest,
                } for name, value in values.items()]
                fixture_id = f"fixture-{index:05d}"
                snapshots.append(build_point_in_time_feature_snapshot(
                    fixture_id=fixture_id, prediction_as_of=cutoff,
                    features=feature_rows,
                ))
                home_score = (index * 3 + index // 4) % 4
                away_score = (index * 5 + index // 7) % 3
                labels.append({
                    "fixture_id": fixture_id, "competition_key": "4160026622",
                    "kickoff_at": kickoff,
                    "settled_at": f"{day.isoformat()}T17:00:00Z",
                    "home_score": home_score, "away_score": away_score,
                    "label_source": "fivedollar",
                    "label_source_id": f"result-{index}",
                    "label_retrieved_at": f"{day.isoformat()}T20:00:00Z",
                    "payload_sha256": digest,
                })
                index += 1
            day += timedelta(days=1)
    return assemble_chronological_training_dataset(
        snapshots=snapshots,
        settled_labels=labels,
        split_policy={
            "train_end_date": "2026-06-30",
            "validation_start_date": "2026-07-08",
            "validation_end_date": "2026-10-02",
            "test_start_date": "2026-10-10",
            "test_end_date": "2026-11-08",
            "embargo_days": 7,
        },
    )


ORIGINS = [
    {
        "origin_id": "origin-1",
        "train_end_date": "2026-06-30",
        "validation_start_date": "2026-07-08",
        "validation_end_date": "2026-08-16",
        "test_start_date": "2026-08-24",
        "test_end_date": "2026-09-22",
    },
    {
        "origin_id": "origin-2",
        "train_end_date": "2026-08-16",
        "validation_start_date": "2026-08-24",
        "validation_end_date": "2026-10-02",
        "test_start_date": "2026-10-10",
        "test_end_date": "2026-11-08",
    },
]


class MultiOriginWalkForwardTests(unittest.TestCase):
    def test_runs_separate_train_calibration_and_test_windows(self):
        report = evaluate_multi_origin_walk_forward(
            dataset=walk_forward_dataset(), origins=ORIGINS, epochs=100,
        )
        self.assertEqual(report["origin_count"], 2)
        self.assertEqual(report["pooled_test_fixture_count"], 150)
        self.assertEqual(len(report["origins"]), 2)
        for origin in report["origins"]:
            self.assertGreaterEqual(origin["counts"]["train"], 100)
            self.assertGreaterEqual(origin["counts"]["validation"], 100)
            self.assertGreaterEqual(origin["counts"]["test"], 1)
            self.assertEqual(origin["training_rows_used_for_calibration"], 0)
            self.assertEqual(origin["test_rows_used_for_calibration"], 0)
            self.assertLess(origin["trained_at"], origin["calibrated_at"])
            self.assertLess(origin["calibrated_at"], origin["evaluated_at"])
            self.assertEqual(set(origin["metrics"]), {"1x2", "btts", "over_2_5"})
        self.assertEqual(set(report["per_competition"]), {"4160026622"})
        self.assertEqual(set(report["per_origin"]), {"origin-1", "origin-2"})
        self.assertFalse(report["full_walk_forward_certified"])
        self.assertFalse(report["value_bet_certified"])
        self.assertFalse(report["publication_allowed"])
        self.assertEqual(report["side_effects"]["database_writes"], 0)

    def test_rejects_overlapping_test_windows(self):
        overlapping = [dict(ORIGINS[0]), dict(ORIGINS[1])]
        overlapping[1]["validation_end_date"] = "2026-09-07"
        overlapping[1]["test_start_date"] = "2026-09-15"
        overlapping[1]["test_end_date"] = "2026-10-14"
        with self.assertRaisesRegex(WalkForwardEvaluationError, "test_windows_overlap"):
            evaluate_multi_origin_walk_forward(
                dataset=walk_forward_dataset(), origins=overlapping, epochs=100,
            )

    def test_requires_at_least_two_origins(self):
        with self.assertRaisesRegex(WalkForwardEvaluationError, "at_least_two"):
            evaluate_multi_origin_walk_forward(
                dataset=walk_forward_dataset(), origins=ORIGINS[:1], epochs=100,
            )

    def test_rejects_origin_with_empty_partition(self):
        bad = [dict(ORIGINS[0]), dict(ORIGINS[1])]
        bad[1]["test_start_date"] = "2027-01-01"
        bad[1]["test_end_date"] = "2027-01-30"
        with self.assertRaisesRegex(WalkForwardEvaluationError, "partition_empty"):
            evaluate_multi_origin_walk_forward(
                dataset=walk_forward_dataset(), origins=bad, epochs=100,
            )


if __name__ == "__main__":
    unittest.main()
