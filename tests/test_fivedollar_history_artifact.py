import hashlib
import json
import unittest
from datetime import date

from app.provider_acquisition_adapters import acquire_fivedollar_history_batch
from app.provider_acquisition_artifact import (
    ArtifactIntegrityError,
    validate_fivedollar_history_batch_report,
)


COMPETITIONS = [
    "3405541143", "3614399544", "4160026622", "4212821298", "686337048",
]


class FakeClient:
    @staticmethod
    def _local_day_window(day, timezone_name):
        assert timezone_name == "Africa/Lagos"
        value = int(day.strftime("%Y%m%d"))
        return value, value + 1

    def _get(self, path, params, *, retries=0):
        competition_id = path.split("/")[1]
        row = {
            "id": int(competition_id),
            "kickoff_utc": "2026-11-02T12:00:00Z",
            "status": "finished",
            "league": {"id": competition_id, "name": "Qualified"},
            "teams": {
                "home": {"id": 1, "name": "Home"},
                "away": {"id": 2, "name": "Away"},
            },
            "goals": {"home": 1, "away": 0},
        }
        return {"data": [row], "pagination": {"has_more": False}}, {}


def valid_report():
    result = acquire_fivedollar_history_batch(
        client=FakeClient(), competition_ids=COMPETITIONS,
        start_date="2026-11-01", end_date="2026-11-07",
        run_id="artifact-test", retrieved_at="2026-11-08T00:00:00Z",
        max_requests=15,
    )
    return result["report"]


def rehash(report):
    value = dict(report)
    value.pop("report_sha256", None)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    report["report_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()


class HistoricalArtifactTests(unittest.TestCase):
    def test_valid_five_competition_batch_passes_offline_validation(self):
        result = validate_fivedollar_history_batch_report(valid_report())
        self.assertTrue(result["valid"])
        self.assertEqual(result["competition_count"], 5)
        self.assertEqual(result["actual_requests"], 5)
        self.assertEqual(result["accepted_count"], 5)

    def test_offline_validator_rejects_unqualified_competition_scope(self):
        report = valid_report()
        report["competition_scope"] = ["999999"]
        rehash(report)
        with self.assertRaisesRegex(ArtifactIntegrityError, "competition_scope_invalid"):
            validate_fivedollar_history_batch_report(report)

    def test_offline_validator_rejects_request_ledger_mismatch(self):
        report = valid_report()
        report["request_budget"]["actual_requests"] = 4
        rehash(report)
        with self.assertRaisesRegex(ArtifactIntegrityError, "page_accounting_mismatch"):
            validate_fivedollar_history_batch_report(report)

    def test_offline_validator_rejects_records_outside_competition_allowlist(self):
        report = valid_report()
        report["records"][0]["competition_key"] = "999999"
        rehash(report)
        with self.assertRaisesRegex(ArtifactIntegrityError, "record_competition_invalid"):
            validate_fivedollar_history_batch_report(report)

    def test_offline_validator_rejects_records_outside_requested_date_window(self):
        report = valid_report()
        report["records"][0]["kickoff_at"] = "2026-11-08T12:00:00Z"
        rehash(report)
        with self.assertRaisesRegex(ArtifactIntegrityError, "outside_batch_window"):
            validate_fivedollar_history_batch_report(report)


if __name__ == "__main__":
    unittest.main()
