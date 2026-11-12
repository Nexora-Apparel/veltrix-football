from __future__ import annotations

import unittest

from scripts.probe_strikerapi_features import probe, validate_report


class StrikerAPIFeatureProbeTests(unittest.TestCase):
    def test_all_feature_and_timestamp_endpoints_are_summarized(self):
        def fake_send(key, tool, params):
            if tool == "list_games":
                return 200, {"data": {"games": [{
                    "game_id": "g-1", "status": "final", "starts_at": "2026-11-01T12:00:00Z",
                    "season": 2026, "competition": "English Premier League"
                }]}}, {}
            if tool == "get_game":
                return 200, {"data": {"game": {"game_id": "g-1"}, "players": [{"id": "p1"}],
                                      "team_stats": [{"xg": 1.2}]}}, {}
            if tool == "get_lineups":
                return 200, {"data": {"home": {"starters": [{"id": "p1"}], "bench": [{"id": "p2"}]},
                                      "away": {"starters": [{"id": "p3"}]}}}, {}
            if tool == "get_events":
                return 200, {"data": {"events": [{"type": "shot", "shot": {"xg": 0.25, "x": 0.2, "y": 0.4}}]}}, {}
            if tool == "get_shot_map":
                return 200, {"data": {"shots_total": 1, "shots": [{"xg": 0.25, "x": 0.2, "y": 0.4}]}}, {}
            if tool == "get_team_stats":
                return 200, {"data": {"teams": [{"xg_for": 1.5, "xg_against": 0.8}]}}, {}
            if tool == "get_odds":
                return 200, {"data": {"games": [{"books": [{"captured_at": "2026-11-01T11:00:00Z", "source": "archive",
                    "home_ml_open": 100, "total_close": 2.5, "over_odds": -110},
                    {"captured_at": "2026-11-12T11:00:00Z", "source": "final",
                     "home_ml_close": -110}]}]}}, {}
            if tool == "get_market_odds":
                return 200, {"data": {"books": [{"opening_captured_at": "2026-11-01T11:00:00Z",
                    "closing_captured_at": "2026-11-01T11:50:00Z", "opening": [{"price": 1.9}],
                    "closing": [{"price": 1.8}]}]}}, {}
            if tool == "get_line_movement":
                return 200, {"data": {"movement": {"book-a": [{"captured_at": "2026-11-01T10:00:00Z"}]}}}, {}
            raise AssertionError(tool)
        report = probe("not-a-real-key", fake_send, sleep=lambda _: None)
        validate_report(report)
        self.assertEqual(report["status"], "ALL_FEATURE_ENDPOINTS_RESPONDED")
        self.assertEqual(report["credits_spent_estimate"], 62)
        self.assertEqual(report["calls"][5]["xg_for_rows"], 1)
        self.assertEqual(report["calls"][6]["timestamped_archive_book_rows"], 1)
        self.assertEqual(report["calls"][6]["final_rows_with_ingest_timestamp"], 1)
        self.assertEqual(report["calls"][7]["timestamped_open_close_rows"], 1)
        self.assertEqual(report["calls"][8]["timestamped_snapshot_rows"], 1)
        self.assertNotIn("not-a-real-key", str(report))

    def test_missing_secret_returns_integrity_checked_report(self):
        report = probe("", lambda *args: (_ for _ in ()).throw(AssertionError("no network")), sleep=lambda _: None)
        validate_report(report)
        self.assertEqual(report["status"], "MISSING_SECRET")
        self.assertEqual(report["credits_spent_estimate"], 0)

    def test_402_stops_probe_without_spending_remaining_endpoint_credits(self):
        def fake_send(key, tool, params):
            if tool == "list_games":
                return 402, {"error": "Insufficient credits"}, {}
            raise AssertionError("later endpoint must not be called")
        report = probe("not-a-real-key", fake_send, sleep=lambda _: None)
        validate_report(report)
        self.assertEqual(report["status"], "INSUFFICIENT_CREDITS")
        self.assertEqual(report["credits_spent_estimate"], 0)
        self.assertEqual(len(report["calls"]), 1)


if __name__ == "__main__":
    unittest.main()
