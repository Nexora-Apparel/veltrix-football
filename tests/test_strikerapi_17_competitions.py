import unittest
from datetime import datetime, timezone

from scripts.verify_strikerapi_17_competitions import (
    COMPETITIONS, MAX_CALLS, qualify, collect_bounded,
)
from scripts.verify_strikerapi import ProbeError


def game(game_id, status="final", date="2026-11-01"):
    row = {
        "game_id": game_id, "date": date, "starts_at": f"{date}T15:00:00Z",
        "status": status,
        "home": {"team_id": "h1", "name": "Home", "score": 1 if status == "final" else None},
        "away": {"team_id": "a1", "name": "Away", "score": 0 if status == "final" else None},
    }
    return row


class AllCompetitionCoverageTests(unittest.TestCase):
    def test_exact_seventeen_competition_enum_is_unique(self):
        keys = [x[0] for x in COMPETITIONS]
        self.assertEqual(len(keys), 17)
        self.assertEqual(len(set(keys)), 17)
        self.assertEqual(MAX_CALLS, 102)

    def test_qualify_covers_all_competition_status_pairs(self):
        calls = []
        def fake_call(api_key, league, status, start, end, offset, **kwargs):
            calls.append((league, status, start, end, offset))
            if offset:
                return {"games": [], "count": 0, "next_offset": None}
            return {"games": [game(f"{league}-{status}", status)], "count": 1, "next_offset": None}
        report = qualify("test-key", datetime(2026, 11, 9, tzinfo=timezone.utc), fake_call)
        self.assertEqual(report["check_count"], 34)
        self.assertEqual(len(calls), 34)
        self.assertEqual(report["totals"]["valid"], 34)
        self.assertTrue(report["acceptance_pass"])
        self.assertEqual(report["database_writes"], 0)

    def test_collect_bounded_marks_truncation_at_page_cap(self):
        budget = {"calls": 0}
        def fake_call(api_key, league, status, start, end, offset, **kwargs):
            return {"games": [game(f"id-{offset}", status)], "count": 50, "next_offset": offset + 50}
        rows, pages, truncated, counts = collect_bounded(
            "key", "soccer", "final", "2026-08-01", "2026-11-09", fake_call, budget
        )
        self.assertEqual(pages, 3)
        self.assertTrue(truncated)
        self.assertEqual(len(rows), 3)
        self.assertEqual(budget["calls"], 3)

    def test_duplicate_ids_across_status_checks_are_counted(self):
        def fake_call(api_key, league, status, start, end, offset, **kwargs):
            # Deliberately return the same ID for final and scheduled; status
            # validation will catch the mismatch for the non-final row.
            return {"games": [game("shared-id", status)], "count": 1, "next_offset": None}
        report = qualify("key", datetime(2026, 11, 9, tzinfo=timezone.utc), fake_call)
        self.assertGreater(report["totals"]["duplicate_ids"], 0)
        self.assertFalse(report["acceptance_pass"])

    def test_scheduled_rows_need_no_scores(self):
        row = game("scheduled-1", "scheduled")
        self.assertIsNone(row["home"]["score"])
        self.assertIsNone(row["away"]["score"])

    def test_budget_exhaustion_fails_closed(self):
        budget = {"calls": MAX_CALLS}
        with self.assertRaises(ProbeError):
            collect_bounded(
                "key", "soccer", "final", "2026-08-01", "2026-11-09",
                lambda *args, **kwargs: {}, budget,
            )

    def test_http_429_uses_bounded_cooldown_retry(self):
        calls = {"count": 0}
        sleeps = []
        def fake_call(api_key, league, status, start, end, offset):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ProbeError("HTTP 429")
            return {"games": [game("retry-id", status)], "count": 1, "next_offset": None}
        budget = {"calls": 0}
        rows, pages, truncated, counts = collect_bounded(
            "key", "soccer", "final", "2026-08-01", "2026-11-09",
            fake_call, budget, pause_seconds=0, sleep=sleeps.append,
        )
        self.assertEqual(calls["count"], 2)
        self.assertEqual(budget["calls"], 2)
        self.assertEqual(sleeps, [65.0])
        self.assertEqual(len(rows), 1)
        self.assertFalse(truncated)

    def test_inter_page_requests_are_paced(self):
        sleeps = []
        def fake_call(api_key, league, status, start, end, offset):
            next_offset = None if offset >= 50 else offset + 50
            return {"games": [game(f"id-{offset}", status)], "count": 50, "next_offset": next_offset}
        rows, pages, truncated, counts = collect_bounded(
            "key", "soccer", "final", "2026-08-01", "2026-11-09",
            fake_call, {"calls": 0}, pause_seconds=7, sleep=sleeps.append,
        )
        self.assertEqual(pages, 2)
        self.assertEqual(sleeps, [7])


if __name__ == "__main__":
    unittest.main()
