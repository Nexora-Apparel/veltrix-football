import unittest

from app.provider_request_budget import (
    BudgetError,
    RequestBudgetLedger,
    RequestBudgetPlan,
    retry_allowed,
)


class RequestBudgetTests(unittest.TestCase):
    def plan(self, **overrides):
        values = {
            "provider": "strikerapi",
            "max_calls": 10,
            "cost_per_call": 2,
            "approved_max_cost": 24,
            "observed_remaining": 30,
            "retry_reserve_calls": 2,
        }
        values.update(overrides)
        return RequestBudgetPlan(**values)

    def test_unknown_credit_balance_fails_closed(self):
        with self.assertRaisesRegex(BudgetError, "observed remaining balance"):
            RequestBudgetLedger(self.plan(observed_remaining=None))

    def test_plan_over_approved_ceiling_is_rejected(self):
        with self.assertRaisesRegex(BudgetError, "approved cost ceiling"):
            RequestBudgetLedger(self.plan(approved_max_cost=22))

    def test_plan_over_observed_balance_is_rejected(self):
        with self.assertRaisesRegex(BudgetError, "observed remaining balance"):
            RequestBudgetLedger(self.plan(observed_remaining=22))

    def test_retry_reserve_is_included_in_preflight(self):
        with self.assertRaises(BudgetError):
            RequestBudgetLedger(self.plan(retry_reserve_calls=3, approved_max_cost=24))

    def test_every_attempt_consumes_one_call_and_cost(self):
        ledger = RequestBudgetLedger(self.plan())
        ledger.before_request()
        ledger.before_request()  # retry attempt is charged identically
        report = ledger.report()
        self.assertEqual(report["calls_made"], 2)
        self.assertEqual(report["cost_consumed"], 4)
        self.assertEqual(report["remaining_observed_budget"], 26)

    def test_ledger_stops_at_planned_plus_reserved_calls(self):
        ledger = RequestBudgetLedger(self.plan())
        for _ in range(12):
            ledger.before_request()
        with self.assertRaisesRegex(BudgetError, "call budget exhausted"):
            ledger.before_request()

    def test_402_and_401_are_never_retryable(self):
        self.assertFalse(retry_allowed(402, 0, 2))
        self.assertFalse(retry_allowed(401, 0, 2))

    def test_429_retry_is_bounded(self):
        self.assertTrue(retry_allowed(429, 0, 2))
        self.assertTrue(retry_allowed(429, 1, 2))
        self.assertFalse(retry_allowed(429, 2, 2))
        self.assertFalse(retry_allowed(500, 0, 2))

    def test_non_credit_provider_can_explicitly_skip_balance_requirement(self):
        plan = self.plan(
            provider="local_fixture_cache",
            observed_remaining=None,
            requires_observed_balance=False,
        )
        ledger = RequestBudgetLedger(plan)
        ledger.before_request()
        self.assertEqual(ledger.report()["calls_made"], 1)


if __name__ == "__main__":
    unittest.main()
