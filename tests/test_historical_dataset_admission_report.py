import hashlib
import json
import unittest

from app.point_in_time_feature_contract import build_point_in_time_feature_snapshot
from app.historical_dataset_admission_report import (
    HistoricalAdmissionReportError,
    build_historical_dataset_admission_report,
)


def make_snapshot(fixture_id, predictors):
    return build_point_in_time_feature_snapshot(
        fixture_id=fixture_id,
        prediction_as_of="2026-09-01T12:00:00Z",
        features=[{
            "name": name, "value": value, "source": "test-source",
            "source_id": f"source-{fixture_id}-{name}",
            "observed_at": "2026-09-01T11:00:00Z",
            "available_at": "2026-09-01T11:15:00Z",
            "retrieved_at": "2026-09-01T11:30:00Z",
            "payload_sha256": "a" * 64,
        } for name, value in predictors.items()],
    )


def pipeline():
    first_predictors = {"home_team_elo": 1500, "away_team_elo": 1490}
    second_predictors = {"home_team_elo": 1480}
    first_snapshot = make_snapshot("p:1", first_predictors)
    second_snapshot = make_snapshot("p:2", second_predictors)
    return {
        "pipeline_report_sha256": "a" * 64,
        "historical_availability_proven": False,
        "acquisition_eligibility": {
            "input_record_count": 4,
            "accepted_records": [{"fixture_id": "p:1"}, {"fixture_id": "p:2"}, {"fixture_id": "p:3"}],
            "rejected_records": [{"fixture_id": "p:4"}],
            "rejected_by_reason": {"settlement_timestamp_unavailable": 1},
            "unmatched_settlement_package_ids": [],
        },
        "feature_reconstruction": {
            "target_fixture_count": 3,
            "snapshot_count": 2,
            "snapshots": [first_snapshot, second_snapshot],
            "withheld_count": 1,
            "withheld_by_reason": {"insufficient_team_history": 1},
            "withheld": [{"fixture_id": "p:3", "reason": "insufficient_team_history"}],
        },
        "dataset": {
            "rows": [
                {
                    "fixture_id": "p:1", "competition_key": "league-a", "split": "train",
                    "predictors": first_predictors,
                    "feature_snapshot_sha256": first_snapshot["snapshot_sha256"],
                    "targets": {"1x2": "home", "btts": "yes", "over_2_5": "yes"},
                },
                {
                    "fixture_id": "p:2", "competition_key": "league-a", "split": "test",
                    "predictors": second_predictors,
                    "feature_snapshot_sha256": second_snapshot["snapshot_sha256"],
                    "targets": {"1x2": "draw", "btts": "no", "over_2_5": "no"},
                },
            ],
            "quality": {"excluded_fixture_count": 0},
        },
    }


class HistoricalDatasetAdmissionReportTests(unittest.TestCase):
    def test_reports_separate_settlement_feature_and_split_admission(self):
        report = build_historical_dataset_admission_report(pipeline())
        self.assertEqual(report["settlement_admission"]["eligible_fixtures"], 3)
        self.assertEqual(report["point_in_time_feature_admission"]["snapshots_built"], 2)
        self.assertEqual(report["point_in_time_feature_admission"]["withheld_fixtures"], 1)
        self.assertEqual(report["dataset"]["included_rows"], 2)
        self.assertEqual(report["dataset"]["counts_by_split"]["train"], 1)
        self.assertEqual(report["dataset"]["counts_by_split"]["test"], 1)
        self.assertEqual(report["feature_coverage"]["by_feature"]["home_team_elo"]["coverage_rate"], 1.0)
        self.assertFalse(report["training_readiness"]["ready_for_model_training"])
        self.assertEqual(
            report["feature_coverage"]["by_data_domain"]["injury_availability"]["status"],
            "not_in_feature_catalogue",
        )
        self.assertEqual(
            report["feature_coverage"]["by_data_domain"]["pressing_intensity_ppda"]["status"],
            "not_in_feature_catalogue",
        )
        self.assertTrue(
            report["feature_coverage"]["feature_level_source_timestamps_and_source_ids_in_rows"]
        )
        self.assertEqual(len(report["report_sha256"]), 64)

    def test_rejects_inconsistent_withheld_count(self):
        value = pipeline()
        value["feature_reconstruction"]["withheld_count"] = 2
        with self.assertRaisesRegex(HistoricalAdmissionReportError, "feature_withheld_count_mismatch"):
            build_historical_dataset_admission_report(value)

    def test_rejects_malformed_dataset_rows(self):
        value = pipeline()
        value["dataset"]["rows"][0]["predictors"] = []
        with self.assertRaisesRegex(HistoricalAdmissionReportError, "dataset_row_features_invalid"):
            build_historical_dataset_admission_report(value)

    def test_report_is_deterministic(self):
        first = build_historical_dataset_admission_report(pipeline())
        second = build_historical_dataset_admission_report(pipeline())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
