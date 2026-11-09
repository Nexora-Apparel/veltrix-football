import copy
import hashlib
import json
import unittest

from app.fivedollar_qualification_report import (
    build_fivedollar_qualification_report,
    validate_fivedollar_qualification_report,
)


class FiveDollarQualificationReportTests(unittest.TestCase):
    def build(self, **overrides):
        args = {
            "run_id": "qualification-run-1",
            "retrieved_at": "2026-11-09T12:00:00Z",
            "window_start_utc": "2026-08-11T00:00:00Z",
            "window_end_utc": "2026-11-09T00:00:00Z",
            "max_requests": 20,
            "actual_requests": 4,
            "endpoint_requests": [{"endpoint": "leagues", "requests": 1},
                                  {"endpoint": "leagues/39/fixtures", "requests": 1},
                                  {"endpoint": "leagues/140/fixtures", "requests": 2}],
            "competitions": [
                {"competition_id": "39", "competition_name": "EPL",
                 "pages_fetched": 1, "source_rows": 10, "accepted_rows": 10,
                 "invalid_rows": 0, "duplicate_ids": 0, "missing_team_ids": 0,
                 "pagination_complete": True},
                {"competition_id": "140", "competition_name": "La Liga",
                 "pages_fetched": 2, "source_rows": 20, "accepted_rows": 20,
                 "invalid_rows": 0, "duplicate_ids": 0, "missing_team_ids": 0,
                 "pagination_complete": True},
            ],
        }
        args.update(overrides)
        return build_fivedollar_qualification_report(**args)

    @staticmethod
    def rehash(report):
        report.pop("report_sha256", None)
        raw = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
        report["report_sha256"] = hashlib.sha256(raw.encode()).hexdigest()

    def test_valid_report_passes_and_aggregates_exactly(self):
        report = self.build()
        result = validate_fivedollar_qualification_report(report)
        self.assertTrue(result["valid"])
        self.assertEqual(result["aggregates"]["source_rows"], 30)
        self.assertTrue(result["acceptance_pass"])

    def test_truncated_competition_fails_acceptance(self):
        comps = self.build()["competitions"]
        comps[0]["pagination_complete"] = False
        report = self.build(competitions=comps)
        self.assertFalse(report["acceptance_pass"])
        self.assertFalse(validate_fivedollar_qualification_report(report)["acceptance_pass"])

    def test_duplicate_ids_rejected(self):
        comps = self.build()["competitions"]
        comps[1]["competition_id"] = comps[0]["competition_id"]
        with self.assertRaisesRegex(ValueError, "duplicate_competition_id"):
            self.build(competitions=comps)

    def test_request_budget_enforced(self):
        with self.assertRaisesRegex(ValueError, "request_budget_exceeded"):
            self.build(max_requests=2)

    def test_endpoint_accounting_must_equal_actual_requests(self):
        with self.assertRaisesRegex(ValueError, "endpoint_request_accounting_mismatch"):
            self.build(actual_requests=5)

    def test_endpoint_page_counts_must_match_competition_report(self):
        report = self.build()
        report["request_budget"]["endpoint_accounting"][1]["requests"] = 1
        self.rehash(report)
        with self.assertRaisesRegex(ValueError, "competition_request_accounting_mismatch"):
            validate_fivedollar_qualification_report(report)

    def test_invalid_rows_prevent_acceptance(self):
        comps = self.build()["competitions"]
        comps[0]["invalid_rows"] = 1
        comps[0]["accepted_rows"] -= 1
        report = self.build(competitions=comps)
        self.assertFalse(report["acceptance_pass"])

    def test_missing_team_ids_prevent_acceptance(self):
        comps = self.build()["competitions"]
        comps[0]["missing_team_ids"] = 1
        comps[0]["accepted_rows"] -= 1
        report = self.build(competitions=comps)
        self.assertFalse(report["acceptance_pass"])

    def test_side_effects_must_be_zero(self):
        with self.assertRaisesRegex(ValueError, "side_effect_boundary_invalid"):
            self.build(database_writes=1)

    def test_tampering_is_detected(self):
        report = self.build()
        report["competitions"][0]["accepted_rows"] = 999
        with self.assertRaisesRegex(ValueError, "report_hash_mismatch"):
            validate_fivedollar_qualification_report(report)

    def test_each_competition_requires_accepted_results(self):
        comps = self.build()["competitions"]
        comps[1]["accepted_rows"] = 0
        comps[1]["invalid_rows"] = comps[1]["source_rows"]
        report = self.build(competitions=comps)
        self.assertFalse(report["acceptance_pass"])

    def test_scope_is_fixed_to_5dollar_provider(self):
        report = self.build()
        report["provider"] = "another-provider"
        self.rehash(report)
        with self.assertRaisesRegex(ValueError, "provider_scope_invalid"):
            validate_fivedollar_qualification_report(report)


if __name__ == "__main__":
    unittest.main()
