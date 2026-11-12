from __future__ import annotations

import unittest

from scripts.probe_strikerapi_free_credit import probe, validate_report


class StrikerAPICreditProbeTests(unittest.TestCase):
    def test_success_spends_one_credit_and_records_balance(self):
        def fake_send(key):
            return 200, {"teams": [{"team_id": "1"}]}, {
                "X-Credits-Used": "1",
                "X-Credits-Remaining": "499",
            }
        report = probe("not-a-real-key", fake_send)
        validate_report(report)
        self.assertEqual(report["status"], "AUTH_OK")
        self.assertEqual(report["credits_used"], 1)
        self.assertEqual(report["credits_remaining"], 499)
        self.assertEqual(report["maximum_credits_spent"], 1)
        self.assertNotIn("not-a-real-key", str(report))

    def test_402_is_recorded_without_failing_and_without_credit_spend(self):
        def fake_send(key):
            return 402, {}, {}
        report = probe("not-a-real-key", fake_send)
        validate_report(report)
        self.assertEqual(report["status"], "HTTP_402_CREDITS_EXHAUSTED")
        self.assertEqual(report["credits_remaining"], 0)
        self.assertEqual(report["credits_used"], 0)

    def test_missing_secret_makes_no_request(self):
        def fail_if_called(key):
            raise AssertionError("network call must not occur")
        report = probe("", fail_if_called)
        validate_report(report)
        self.assertEqual(report["status"], "MISSING_SECRET")
        self.assertEqual(report["request_count"], 0)


if __name__ == "__main__":
    unittest.main()
