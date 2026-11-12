from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.probe_fivedollar_account import probe as probe_account, validate_report
from scripts.probe_oddspapi_safe import probe as probe_oddspapi, validate_report as validate_odds


class AccountProbeTests(unittest.TestCase):
    def test_account_plan_and_competition_catalogue_are_reported_without_secrets(self):
        calls = []
        def fake_request(path, key):
            calls.append((path, key))
            if path == "/status":
                return ({"data": {"plan": "community", "limits": {"rate_limit": 300, "burst_per_minute": 20},
                                  "usage": {"today": 12}}}, {"X-RateLimit-Limit": "300"})
            if path == "/leagues":
                return ({"data": [{"id": 1, "name": "Premier League", "country": {"name": "England"}}],
                         "pagination": {"has_more": False}}, {"X-RateLimit-Limit": "300"})
            if path.startswith("/leagues/"):
                return ({"data": [{"id": "fx-1"}]}, {})
            if path.startswith("/fixtures/"):
                return ({"data": {"bookmakers": [{"odds": {
                    "1x2": {"opening": {"opened_at": "2026-11-10T10:00:00Z"},
                            "closing": {"home": 1.8, "draw": 3.5, "away": 4.5}},
                    "btts": {"opening": {"yes": 1.9, "no": 1.9}},
                }}]}}, {})
            raise AssertionError(path)
        report = probe_account("not-a-real-secret", fake_request, sleep=lambda _: None)
        validate_report(report)
        self.assertEqual(report["plan"], "community")
        self.assertEqual(report["competition_count_page_1"], 1)
        self.assertFalse(report["pagination"]["has_more"])
        self.assertEqual(report["request_count"], 4)
        self.assertTrue(report["odds_samples"][0]["one_x_two_opened_at"])
        self.assertEqual(report["odds_timestamped_market_blocks_sampled"], 1)
        self.assertNotIn("not-a-real-secret", str(report))
        self.assertEqual(len(calls), 2)

    def test_account_schema_failure_is_fail_closed(self):
        def fake_request(path, key):
            return ({"data": []}, {})
        with self.assertRaises(Exception):
            probe_account("key", fake_request)


class FakeOddsPapi:
    def get(self, path, params=None):
        if path == "sports":
            return [{"sportId": 10, "sportName": "Soccer"}]
        if path == "markets":
            return [
                {"sportId": 10, "marketId": 1, "marketName": "Both Teams to Score"},
                {"sportId": 10, "marketId": 2, "marketName": "Over Under"},
            ]
        if path == "fixtures" and str((params or {}).get("from", "")).startswith("2026-11-12"):
            return [{"sportId": 10, "fixtureId": "fx-1", "hasOdds": True, "tournamentName": "Premier League"}]
        if path == "fixtures":
            return [{"sportId": 10, "fixtureId": "past-fx", "hasOdds": True,
                     "startTime": "2026-11-01T15:00:00Z", "tournamentName": "Premier League"}]
        if path == "odds":
            return {"bookmakerOdds": {"book-a": {"markets": {
                "1": {"outcomes": {"yes": {"players": {"p": {"active": True, "price": 1.8}}}}},
                "2": {"outcomes": {"over": {"players": {"p": {"active": True, "price": 1.9}}}}},
            }}}}
        if path == "historical-odds":
            return {"fixtureId": "past-fx", "bookmakers": {"book-a": {"markets": {
                "1": {"outcomes": {"yes": {"players": {"0": [
                    {"createdAt": "2026-11-01T14:00:00+00:00", "price": 1.8, "active": True},
                    {"createdAt": "2026-11-01T14:30:00+00:00", "price": 1.9, "active": True},
                ]}}}}
            }}}}
        raise AssertionError(path)


class OddsPapiProbeTests(unittest.TestCase):
    def test_soccer_btts_totals_and_timestamped_history_are_counted(self):
        report = probe_oddspapi(
            FakeOddsPapi(),
            datetime(2026, 11, 12, tzinfo=timezone.utc),
        )
        validate_odds(report)
        self.assertEqual(report["btts_active_price_count"], 1)
        self.assertEqual(report["over_under_active_price_count"], 1)
        self.assertEqual(report["historical_odds"]["status"], "OK_WITH_TIMESTAMPED_ROWS")
        self.assertEqual(report["historical_odds"]["timestamped_price_rows"], 2)
        self.assertEqual(report["request_count"], 6)
        self.assertEqual(report["side_effects"]["database_writes"], 0)


if __name__ == "__main__":
    unittest.main()
