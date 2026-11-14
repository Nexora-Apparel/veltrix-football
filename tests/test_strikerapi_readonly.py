import unittest

from scripts.verify_strikerapi import MAX_PAGES_PER_CHECK, collect_pages, validate_game


def game(game_id="g-1", status="final"):
    row = {
        "game_id": game_id,
        "date": "2026-10-01",
        "starts_at": "2026-10-01T18:00:00.000Z",
        "status": status,
        "home": {"team_id": "h1", "name": "Home", "score": 1 if status == "final" else None},
        "away": {"team_id": "a1", "name": "Away", "score": 0 if status == "final" else None},
    }
    return row


class StrikerPaginationTests(unittest.TestCase):
    def test_follows_next_offset_until_last_page(self):
        calls = []

        def fake_call(_key, _league, _status, _start, _end, offset):
            calls.append(offset)
            if offset == 0:
                return {"games": [game("g-1")], "count": 2, "next_offset": 1}
            return {"games": [game("g-2")], "count": 2}

        rows, pages, truncated, _counts = collect_pages(
            "test", "soccer", "final", "2026-09-01", "2026-11-09", fake_call
        )
        self.assertEqual(calls, [0, 1])
        self.assertEqual([row["game_id"] for row in rows], ["g-1", "g-2"])
        self.assertEqual(pages, 2)
        self.assertFalse(truncated)

    def test_reports_truncation_at_page_cap(self):
        calls = []

        def fake_call(_key, _league, _status, _start, _end, offset):
            calls.append(offset)
            return {"games": [game(f"g-{offset}")], "next_offset": offset + 1}

        rows, pages, truncated, _counts = collect_pages(
            "test", "soccer", "final", "2026-09-01", "2026-11-09", fake_call
        )
        self.assertEqual(pages, MAX_PAGES_PER_CHECK)
        self.assertEqual(len(rows), MAX_PAGES_PER_CHECK)
        self.assertTrue(truncated)

    def test_rejects_non_advancing_offset(self):
        def fake_call(_key, _league, _status, _start, _end, _offset):
            return {"games": [game()], "next_offset": 0}

        with self.assertRaisesRegex(Exception, "did not advance"):
            collect_pages(
                "test", "soccer", "final", "2026-09-01", "2026-11-09", fake_call
            )

    def test_rejects_invalid_final_score(self):
        row = game()
        row["home"]["score"] = "1"
        valid, reason = validate_game(row, "final")
        self.assertFalse(valid)
        self.assertEqual(reason, "invalid_final_score")

    def test_rejects_timezone_naive_kickoff(self):
        row = game()
        row["starts_at"] = "2026-10-01T18:00:00"
        valid, reason = validate_game(row, "final")
        self.assertFalse(valid)
        self.assertEqual(reason, "timezone_missing_from_kickoff_timestamp")

    def test_accepts_scheduled_fixture_without_scores(self):
        valid, reason = validate_game(game(status="scheduled"), "scheduled")
        self.assertTrue(valid)
        self.assertEqual(reason, "valid")




class StrikerSeasonFilterTests(unittest.TestCase):
    def test_collect_pages_forwards_season_and_stage_filters(self):
        received = []

        def fake_call(_key, league, status, start, end, offset, **filters):
            received.append((league, status, start, end, offset, filters))
            return {"games": [], "count": 0}

        rows, pages, truncated, _counts = collect_pages(
            "test", "nwsl", "final", None, None, fake_call,
            extra_params={"season": 2026, "stage": "knockout"},
        )
        self.assertEqual(rows, [])
        self.assertEqual(pages, 1)
        self.assertFalse(truncated)
        self.assertEqual(
            received,
            [("nwsl", "final", None, None, 0, {"season": 2026, "stage": "knockout"})],
        )


if __name__ == "__main__":
    unittest.main()
