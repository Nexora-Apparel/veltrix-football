from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.probe_fivedollar_account import probe as probe_account, validate_report
from scripts.probe_oddspapi_safe import probe as probe_oddspapi, validate_report as validate_odds


class FakeResponse:
    def __init__(self, data, headers=None):
        self.data = data
        self.headers = headers or {}


class AccountProbeTests(unittest.TestCase):
    def test_account_plan_and_competition_catalogue_are_reported_without_secrets(self):
        calls = []
        def fake_request(path, key):
            calls.append((path, key))
            if path == "/status":
                return ({"plan": "community", "limits": {"rate_limit": 300, "burst_per_minute": 20},
                         "usage": {"today": 12}}, FakeResponse(None, {"X-RateLimit-Limit": "300"}).headers)
            return ([{"id": 1, "name": "Premier League", "country": {"name": "England"}}],
                    {"X-RateLimit-Limit": "300"})
        report = probe_account("not-a-real-secret", fake_request)
        validate_report(report)
        self.assertEqual(report["plan"], "community")
        self.assertEqual(report["competition_count_page_1"], 1)
        self.assertEqual(report["request_count"], 2)
        self.assertNotIn("not-a-real-secret", str(report))
        self.assertEqual(len(calls), 2)

    def test_account_schema_failure_is_fail_closed(self):
        def fake_request(path, key):
            return ([], {}) if path == "/status" else ([], {})
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
        if path == "fixtures":
            return [{"sportId": 10, "fixtureId": "fx-1", "hasOdds": True, "tournamentName": "Premier League"}]
        if path == "odds":
            return {"bookmakerOdds": {"book-a": {"markets": {
                "1": {"outcomes": {"yes": {"players": {"p": {"active": True, "price": 1.8}}}}},
                "2": {"outcomes": {"over": {"players": {"p": {"active": True, "price": 1.9}}}}},
            }}}}
        raise AssertionError(path)


class OddsPapiProbeTests(unittest.TestCase):
    def test_soccer_btts_and_totals_quotes_are_counted(self):
        report = probe_oddspapi(
            FakeOddsPapi(),
            datetime(2026, 11, 12, tzinfo=timezone.utc),
        )
        validate_odds(report)
        self.assertEqual(report["btts_active_price_count"], 1)
        self.assertEqual(report["over_under_active_price_count"], 1)
        self.assertEqual(report["request_count"], 4)
        self.assertEqual(report["side_effects"]["database_writes"], 0)


if __name__ == "__main__":
    unittest.main()
