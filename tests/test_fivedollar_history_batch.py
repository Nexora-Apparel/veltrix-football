import unittest
from datetime import date

from app.provider_acquisition_adapters import (
    AcquisitionAdapterError,
    acquire_fivedollar_history_batch,
)


COMPETITIONS = [
    "3405541143", "3614399544", "4160026622", "4212821298", "686337048",
]


class FakeHistoryClient:
    @staticmethod
    def _local_day_window(day, timezone_name):
        assert timezone_name == "Africa/Lagos"
        return int(date(day.year, day.month, day.day).strftime("%Y%m%d")), int(
            date(day.year, day.month, day.day).strftime("%Y%m%d")
        ) + 1

    def __init__(self, *, extra_page=False, wrong_competition=None):
        self.calls = []
        self.extra_page = extra_page
        self.wrong_competition = wrong_competition

    def _get(self, path, params, *, retries=2):
        self.calls.append((path, params, retries))
        competition_id = path.split("/")[1]
        row_competition = self.wrong_competition or competition_id
        page = params["page"]
        row = {
            "id": int(competition_id) + page,
            "kickoff_utc": "2026-11-02T12:00:00Z",
            "status": "finished",
            "league": {"id": row_competition, "name": "Qualified League"},
            "teams": {
                "home": {"id": 1, "name": "Home FC"},
                "away": {"id": 2, "name": "Away FC"},
            },
            "goals": {"home": 2, "away": 1},
            "season": "2026",
        }
        return {
            "success": 1,
            "data": [row],
            "pagination": {"has_more": self.extra_page and page == 1},
        }, {}


class HistoricalAcquisitionTests(unittest.TestCase):
    def test_batch_reads_only_five_qualified_competitions_and_emits_audit_report(self):
        client = FakeHistoryClient()
        sleeps = []
        result = acquire_fivedollar_history_batch(
            client=client, competition_ids=COMPETITIONS,
            start_date="2026-11-01", end_date="2026-11-07",
            run_id="history-test", retrieved_at="2026-11-08T00:00:00Z",
            max_requests=15, sleep=sleeps.append,
        )
        self.assertEqual(result["batch"]["accepted_count"], 5)
        self.assertEqual(result["batch"]["quarantined_count"], 0)
        self.assertEqual(result["report"]["competition_scope"], COMPETITIONS)
        self.assertEqual(result["report"]["request_budget"]["actual_requests"], 5)
        self.assertTrue(all(call[2] == 0 for call in client.calls))
        self.assertEqual(sleeps, [3.1, 3.1, 3.1, 3.1])
        self.assertTrue(all(call[1]["start_time"] == 20261101 for call in client.calls))
        self.assertTrue(all(call[1]["end_time"] == 20261108 for call in client.calls))
        self.assertEqual(result["side_effects"]["database_writes"], 0)
        self.assertEqual(result["side_effects"]["imports"], 0)

    def test_batch_rejects_provider_rows_from_an_unqualified_competition(self):
        client = FakeHistoryClient(wrong_competition="999999")
        with self.assertRaisesRegex(AcquisitionAdapterError, "competition_scope_mismatch"):
            acquire_fivedollar_history_batch(
                client=client, competition_ids=COMPETITIONS,
                start_date="2026-11-01", end_date="2026-11-07",
                run_id="scope-test", max_requests=15, sleep=lambda _: None,
            )

    def test_batch_stops_before_request_budget_is_exceeded(self):
        client = FakeHistoryClient(extra_page=True)
        with self.assertRaisesRegex(AcquisitionAdapterError, "request_budget_exhausted"):
            acquire_fivedollar_history_batch(
                client=client, competition_ids=COMPETITIONS,
                start_date="2026-11-01", end_date="2026-11-07",
                run_id="budget-test", max_requests=5, sleep=lambda _: None,
            )
        self.assertEqual(len(client.calls), 5)

    def test_batch_rejects_truncated_pagination(self):
        client = FakeHistoryClient(extra_page=True)
        with self.assertRaisesRegex(AcquisitionAdapterError, "pagination_truncated"):
            acquire_fivedollar_history_batch(
                client=client, competition_ids=COMPETITIONS,
                start_date="2026-11-01", end_date="2026-11-07",
                run_id="pages-test", max_requests=20, sleep=lambda _: None,
                max_pages_per_competition=1,
            )

    def test_batch_rejects_windows_longer_than_seven_calendar_days(self):
        with self.assertRaisesRegex(ValueError, "one_to_seven_days"):
            acquire_fivedollar_history_batch(
                client=FakeHistoryClient(), competition_ids=COMPETITIONS,
                start_date="2026-11-01", end_date="2026-11-08",
                run_id="window-test", max_requests=20, sleep=lambda _: None,
            )

    def test_batch_rejects_duplicate_or_unqualified_competition_ids(self):
        for values in (COMPETITIONS + [COMPETITIONS[0]], ["999999"]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                acquire_fivedollar_history_batch(
                    client=FakeHistoryClient(), competition_ids=values,
                    start_date="2026-11-01", end_date="2026-11-07",
                    run_id="id-test", max_requests=20, sleep=lambda _: None,
                )


if __name__ == "__main__":
    unittest.main()
