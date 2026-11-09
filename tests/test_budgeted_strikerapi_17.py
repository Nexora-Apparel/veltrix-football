import unittest
from datetime import datetime, timezone

from app.provider_request_budget import BudgetError
from scripts.run_budgeted_strikerapi_17 import (
    build_ledger,
    run_budgeted_qualification,
)
from scripts.verify_strikerapi_17_competitions import MAX_CALLS


class BudgetedStrikerQualificationTests(unittest.TestCase):
    def test_missing_balance_is_rejected_before_transport(self):
        calls = []
        with self.assertRaises(BudgetError):
            run_budgeted_qualification(
                "test-key", None, 204, datetime(2026, 11, 9, tzinfo=timezone.utc),
                transport=lambda *a, **k: calls.append(a),
            )
        self.assertEqual(calls, [])

    def test_missing_approved_ceiling_is_rejected(self):
        with self.assertRaises(BudgetError):
            build_ledger(500, None)

    def test_full_scan_must_fit_both_limits(self):
        with self.assertRaises(BudgetError):
            build_ledger(500, 203)
        with self.assertRaises(BudgetError):
            build_ledger(203, 204)

    def test_preflight_accepts_exact_documented_maximum(self):
        ledger = build_ledger(204, 204)
        self.assertEqual(ledger.plan.max_calls, MAX_CALLS)
        self.assertEqual(ledger.plan.reserved_cost, 204)

    def test_metered_transport_charges_each_actual_request(self):
        def fake_transport(api_key, league, status, start, end, offset):
            return {"games": [], "count": 0, "next_offset": None}

        report = run_budgeted_qualification(
            "test-key", 204, 204,
            datetime(2026, 11, 9, tzinfo=timezone.utc),
            transport=fake_transport,
            pause_seconds=0,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(report["request_budget"]["actual_calls"], 34)
        self.assertEqual(report["request_budget"]["actual_documented_credits"], 68)
        self.assertTrue(report["request_budget"]["preflight_passed"])
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["imports"], 0)


if __name__ == "__main__":
    unittest.main()
