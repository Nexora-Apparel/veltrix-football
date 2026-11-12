import unittest
from datetime import date, datetime

from app.provider_acquisition_adapters import acquire_fivedollar_history_batch
from app.provider_historical_archive import assemble_fivedollar_history_archive
from app.provider_historical_coverage import (
    HistoricalCoverageError,
    profile_fivedollar_historical_coverage,
    validate_fivedollar_coverage_profile,
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
        day = datetime.strptime(str(params["start_time"]), "%Y%m%d").date()
        row = {
            "id": int(competition_id) + int(params["start_time"]),
            "kickoff_utc": f"{day.isoformat()}T12:00:00Z",
            "status": "finished",
            "league": {"id": competition_id, "name": "Qualified"},
            "teams": {
                "home": {"id": 1, "name": "Home"},
                "away": {"id": 2, "name": "Away"},
            },
            "goals": {"home": 1, "away": 0},
        }
        return {"data": [row], "pagination": {"has_more": False}}, {}


def build_archive():
    report = acquire_fivedollar_history_batch(
        client=FakeClient(), competition_ids=COMPETITIONS,
        start_date="2026-11-01", end_date="2026-11-07",
        run_id="coverage-test", retrieved_at="2026-11-08T00:00:00Z",
        max_requests=15, sleep=lambda _: None,
    )["report"]
    return assemble_fivedollar_history_archive(
        reports=[report], target_start_date="2026-11-01", target_end_date="2026-11-07",
    )


class HistoricalCoverageTests(unittest.TestCase):
    def test_profiles_competition_and_month_coverage_without_claiming_completeness(self):
        archive = build_archive()
        report = profile_fivedollar_historical_coverage(archive)
        verified = validate_fivedollar_coverage_profile(report)
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["accepted_finished_matches"], 5)
        self.assertEqual(verified["competition_count"], 5)
        self.assertEqual(report["quality"]["matches_by_month"], {"2026-11": 5})
        self.assertEqual(report["acquisition_coverage"]["provider_page_coverage_complete"], True)
        self.assertFalse(report["acquisition_coverage"]["historical_match_completeness_claimed"])
        self.assertFalse(report["training_readiness"]["ready_for_model_training"])

    def test_coverage_profile_hash_tampering_is_rejected(self):
        report = profile_fivedollar_historical_coverage(build_archive())
        report["quality"]["accepted_finished_matches"] = 999
        with self.assertRaisesRegex(HistoricalCoverageError, "hash_mismatch"):
            validate_fivedollar_coverage_profile(report)

    def test_empty_archive_is_reported_as_zero_coverage_not_training_ready(self):
        archive = build_archive()
        archive["records"] = []
        archive["quality"]["accepted_count"] = 0
        archive["quality"]["accepted_by_competition"] = {
            competition: 0 for competition in COMPETITIONS
        }
        archive["archive_sha256"] = __import__("hashlib").sha256(
            __import__("json").dumps(
                {key: value for key, value in archive.items() if key != "archive_sha256"},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        report = profile_fivedollar_historical_coverage(archive)
        self.assertEqual(report["quality"]["accepted_finished_matches"], 0)
        self.assertFalse(report["training_readiness"]["ready_for_model_training"])


if __name__ == "__main__":
    unittest.main()
