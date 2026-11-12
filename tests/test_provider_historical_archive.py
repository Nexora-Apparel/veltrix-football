import unittest
from datetime import date, datetime

from app.provider_acquisition_adapters import acquire_fivedollar_history_batch
from app.provider_historical_archive import (
    HistoricalArchiveError,
    assemble_fivedollar_history_archive,
    validate_fivedollar_history_archive,
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


def batch(start, end, retrieved, run_id):
    return acquire_fivedollar_history_batch(
        client=FakeClient(), competition_ids=COMPETITIONS,
        start_date=start, end_date=end, run_id=run_id,
        retrieved_at=retrieved, max_requests=15, sleep=lambda _: None,
    )["report"]


class HistoricalArchiveTests(unittest.TestCase):
    def test_two_contiguous_batches_assemble_into_complete_archive(self):
        reports = [
            batch("2026-11-01", "2026-11-07", "2026-11-08T00:00:00Z", "week-1"),
            batch("2026-11-08", "2026-11-14", "2026-11-15T00:00:00Z", "week-2"),
        ]
        archive = assemble_fivedollar_history_archive(
            reports=reports, target_start_date="2026-11-01", target_end_date="2026-11-14",
        )
        result = validate_fivedollar_history_archive(archive)
        self.assertTrue(result["valid"])
        self.assertEqual(result["batch_count"], 2)
        self.assertEqual(result["accepted_count"], 10)
        self.assertEqual(archive["quality"]["accepted_by_competition"]["3405541143"], 2)
        self.assertEqual(archive["side_effects"]["database_writes"], 0)

    def test_assembly_rejects_gaps_and_overlapping_windows(self):
        first = batch("2026-11-01", "2026-11-07", "2026-11-08T00:00:00Z", "first")
        gap = batch("2026-11-09", "2026-11-14", "2026-11-15T00:00:00Z", "gap")
        overlap = batch("2026-11-07", "2026-11-13", "2026-11-14T00:00:00Z", "overlap")
        with self.assertRaisesRegex(HistoricalArchiveError, "historical_window_gap"):
            assemble_fivedollar_history_archive(
                reports=[first, gap], target_start_date="2026-11-01", target_end_date="2026-11-14",
            )
        with self.assertRaisesRegex(HistoricalArchiveError, "overlapping_batch_windows"):
            assemble_fivedollar_history_archive(
                reports=[first, overlap], target_start_date="2026-11-01", target_end_date="2026-11-13",
            )

    def test_archive_hash_tampering_is_rejected(self):
        report = batch("2026-11-01", "2026-11-07", "2026-11-08T00:00:00Z", "single")
        archive = assemble_fivedollar_history_archive(
            reports=[report], target_start_date="2026-11-01", target_end_date="2026-11-07",
        )
        archive["records"][0]["home_score"] = 5
        with self.assertRaisesRegex(HistoricalArchiveError, "archive_hash_mismatch"):
            validate_fivedollar_history_archive(archive)


if __name__ == "__main__":
    unittest.main()
