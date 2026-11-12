import unittest

from app.provider_acquisition_report import build_acquisition_report


class AcquisitionReportTests(unittest.TestCase):
    def batch(self):
        return {
            "input_count": 3,
            "acceptance_pass": False,
            "accepted": [
                {"provider": "strikerapi", "competition_key": "soccer",
                 "normalized_status": "finished", "source_id": "1"},
                {"provider": "fivedollar", "competition_key": "39",
                 "normalized_status": "scheduled", "source_id": "2"},
            ],
            "quarantined": [
                {"reason": "duplicate_provider_competition_source_identity"}
            ],
        }

    def build(self, **overrides):
        args = {
            "run_id": "run-001",
            "provider_scope": ["strikerapi", "fivedollar"],
            "competition_scope": ["soccer", "39"],
            "window": {"from": "2026-11-01", "to": "2026-11-09"},
            "retrieved_at": "2026-11-09T12:00:00Z",
            "batch_result": self.batch(),
            "request_budget": {"calls_made": 0, "credits_consumed": 0},
        }
        args.update(overrides)
        return build_acquisition_report(**args)

    def test_report_contains_provider_and_quality_counts(self):
        report = self.build()
        self.assertEqual(report["quality"]["accepted_count"], 2)
        self.assertEqual(report["quality"]["quarantined_count"], 1)
        self.assertEqual(report["quality"]["accepted_by_provider"]["strikerapi"], 1)
        self.assertEqual(report["quality"]["accepted_by_normalized_status"]["finished"], 1)

    def test_report_proves_zero_side_effects(self):
        report = self.build()
        self.assertEqual(report["side_effects"]["database_writes"], 0)
        self.assertEqual(report["side_effects"]["imports"], 0)
        self.assertEqual(report["side_effects"]["canonical_merges"], 0)

    def test_report_hash_is_deterministic(self):
        first, second = self.build(), self.build()
        self.assertEqual(first["report_sha256"], second["report_sha256"])

    def test_naive_retrieval_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "retrieved_at_timezone_missing"):
            self.build(retrieved_at="2026-11-09T12:00:00")

    def test_missing_provider_scope_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "provider_scope_required"):
            self.build(provider_scope=[])

    def test_records_are_not_counted_as_success_if_quarantined(self):
        report = self.build()
        self.assertFalse(report["quality"]["acceptance_pass"])


if __name__ == "__main__":
    unittest.main()
