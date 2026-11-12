import json
import unittest
from unittest.mock import patch

from scripts.probe_fivedollar_statistics import probe, validate_report


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode()
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def response_for(url):
    if url.endswith("/leagues?page=1&per_page=100"):
        return FakeResponse({"success": 1, "data": [
            {"id": 10, "name": "League A"}, {"id": 20, "name": "League B"}
        ], "pagination": {"has_more": False}})
    if "/leagues/10/fixtures?" in url:
        return FakeResponse({"success": 1, "data": [{"id": 100, "status": "finished"}]})
    if "/leagues/20/fixtures?" in url:
        return FakeResponse({"success": 1, "data": [{"id": 200, "status": "finished"}]})
    if url.endswith("/fixtures/100/statistics"):
        return FakeResponse({"success": 1, "data": {"fixture_id": 100, "statistics": {
            "attacks": {"home": 10, "away": 8},
            "shots_on_target": {"home": 2, "away": 1},
            "possession": {"home": 55, "away": 45},
            "first_half": {"attacks": {"home": 4, "away": 3}},
        }}})
    if url.endswith("/fixtures/200/statistics"):
        return FakeResponse({"success": 1, "data": {"fixture_id": 200, "statistics": {}}})
    raise AssertionError(url)


class StatisticsProbeTests(unittest.TestCase):
    @patch("scripts.probe_fivedollar_statistics.urlopen")
    def test_probe_records_fields_without_side_effects(self, mocked):
        mocked.side_effect = response_for
        report = probe("test-key", 10, 90, "test-run")
        validate_report(report)
        self.assertEqual(report["request_budget"]["actual_requests"], 5)
        self.assertEqual(report["samples"][0]["statistics_status"], "OK_EMPTY")
        row = next(x for x in report["samples"] if x["fixture_id"] == "100")
        self.assertEqual(row["statistics_status"], "OK_WITH_FIELDS")
        self.assertEqual(set(row["available_fields"]), {"attacks", "shots_on_target", "possession", "first_half"})
        self.assertEqual(report["side_effects"]["database_writes"], 0)

    @patch("scripts.probe_fivedollar_statistics.urlopen")
    def test_hash_tampering_is_rejected(self, mocked):
        mocked.side_effect = response_for
        report = probe("test-key", 10, 90, "test-run")
        report["samples"][0]["statistics_status"] = "OK_WITH_FIELDS"
        with self.assertRaisesRegex(ValueError, "report_hash_invalid"):
            validate_report(report)

    @patch("scripts.probe_fivedollar_statistics.urlopen")
    def test_http_403_is_recorded_without_exposing_body(self, mocked):
        from urllib.error import HTTPError

        def forbidden(request, timeout=20):
            if request.full_url.endswith("/fixtures/100/statistics"):
                raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
            return response_for(request.full_url)

        mocked.side_effect = forbidden
        report = probe("test-key", 10, 90, "test-run")
        row = next(x for x in report["samples"] if x["fixture_id"] == "100")
        self.assertEqual(row["statistics_status"], "HTTP_403")
        self.assertNotIn("body", json.dumps(report).lower())

    @patch("scripts.probe_fivedollar_statistics.urlopen")
    def test_request_budget_is_hard_capped(self, mocked):
        mocked.side_effect = response_for
        report = probe("test-key", 3, 90, "test-run")
        self.assertEqual(report["request_budget"]["actual_requests"], 3)
        self.assertTrue(any(x["statistics_status"] == "REQUEST_BUDGET_EXHAUSTED"
                            for x in report["samples"]))
        validate_report(report)


if __name__ == "__main__":
    unittest.main()
