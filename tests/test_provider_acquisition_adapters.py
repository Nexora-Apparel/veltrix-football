import unittest

from app.provider_acquisition_adapters import (
    AcquisitionAdapterError,
    acquire_fivedollar_day,
    acquire_strikerapi_competition,
)
from app.provider_request_budget import RequestBudgetLedger, RequestBudgetPlan


class FakeFiveDollarClient:
    @staticmethod
    def _local_day_window(day, timezone_name):
        assert timezone_name == "Africa/Lagos"
        return 100, 200

    def __init__(self):
        self.calls = []

    def _get(self, path, params):
        self.calls.append((path, params))
        page = params["page"]
        row = {
            "id": 500 + page,
            "kickoff_utc": "2026-11-09T12:00:00Z",
            "status": "finished",
            "league": {"id": 39, "name": "Premier League"},
            "teams": {
                "home": {"id": 1, "name": "Home FC"},
                "away": {"id": 2, "name": "Away FC"},
            },
            "goals": {"home": 2, "away": 0},
            "season": "2026",
        }
        return {
            "success": 1,
            "data": [row],
            "pagination": {"has_more": page == 1},
        }, {"X-RateLimit-Remaining": "58"}


class AcquisitionAdapterTests(unittest.TestCase):
    def test_fivedollar_adapter_fetches_and_normalizes_original_rows(self):
        client = FakeFiveDollarClient()
        result = acquire_fivedollar_day(
            client=client, day="2026-11-09", run_id="fd-run",
            retrieved_at="2026-11-09T13:00:00Z", max_pages=3,
        )
        self.assertEqual(result["batch"]["accepted_count"], 2)
        self.assertEqual(result["report"]["request_budget"]["calls_made"], 2)
        self.assertEqual(result["report"]["records"][0]["provider"], "fivedollar")
        self.assertEqual(result["side_effects"]["database_writes"], 0)
        self.assertEqual(len(client.calls), 2)

    def test_fivedollar_adapter_accepts_a_genuinely_empty_window(self):
        class EmptyClient(FakeFiveDollarClient):
            def _get(self, path, params):
                return {"success": 1, "data": [], "pagination": {"has_more": False}}, {}

        result = acquire_fivedollar_day(
            client=EmptyClient(), day="2026-11-09", run_id="empty-run",
            retrieved_at="2026-11-09T13:00:00Z",
        )
        self.assertEqual(result["batch"]["accepted_count"], 0)
        self.assertEqual(result["batch"]["quarantined_count"], 0)
        self.assertEqual(result["report"]["competition_scope"], [])

    def test_fivedollar_adapter_fails_if_page_limit_would_truncate(self):
        client = FakeFiveDollarClient()
        with self.assertRaisesRegex(AcquisitionAdapterError, "pagination_truncated"):
            acquire_fivedollar_day(
                client=client, day="2026-11-09", run_id="fd-run",
                retrieved_at="2026-11-09T13:00:00Z", max_pages=1,
            )

    def test_strikerapi_adapter_charges_each_transport_attempt(self):
        ledger = RequestBudgetLedger(RequestBudgetPlan(
            provider="strikerapi", max_calls=2, cost_per_call=2,
            approved_max_cost=4, observed_remaining=20,
        ))
        calls = []

        def fake_transport(key, league, status, start, end, offset):
            calls.append(offset)
            return {"games": [{
                "game_id": 900 + len(calls),
                "starts_at": "2026-11-10T18:00:00Z",
                "status": status,
                "home": {"team_id": 1, "name": "Home", "score": 1},
                "away": {"team_id": 2, "name": "Away", "score": 0},
            }], "next_offset": None, "count": 1}

        result = acquire_strikerapi_competition(
            api_key="test-key", competition_key="soccer",
            competition_label="English Premier League", status="final",
            start="2026-11-01", end="2026-11-09", run_id="sa-run",
            ledger=ledger, transport=fake_transport,
            retrieved_at="2026-11-09T13:00:00Z",
        )
        self.assertEqual(calls, [0])
        self.assertEqual(ledger.calls_made, 1)
        self.assertEqual(ledger.cost_consumed, 2)
        self.assertEqual(result["report"]["quality"]["accepted_count"], 1)

    def test_strikerapi_adapter_stops_before_unbudgeted_second_page(self):
        ledger = RequestBudgetLedger(RequestBudgetPlan(
            provider="strikerapi", max_calls=1, cost_per_call=2,
            approved_max_cost=2, observed_remaining=10,
        ))

        def two_pages(key, league, status, start, end, offset):
            return {
                "games": [{
                    "game_id": 1 + offset, "starts_at": "2026-11-10T18:00:00Z",
                    "status": status,
                    "home": {"team_id": 1, "name": "Home", "score": 1},
                    "away": {"team_id": 2, "name": "Away", "score": 0},
                }],
                "next_offset": 50 if offset == 0 else None,
            }

        with self.assertRaisesRegex(Exception, "request call budget exhausted"):
            acquire_strikerapi_competition(
                api_key="test-key", competition_key="soccer",
                competition_label="English Premier League", status="final",
                start="2026-11-01", end="2026-11-09", run_id="sa-run",
                ledger=ledger, transport=two_pages,
                retrieved_at="2026-11-09T13:00:00Z",
            )
        self.assertEqual(ledger.calls_made, 1)


if __name__ == "__main__":
    unittest.main()
