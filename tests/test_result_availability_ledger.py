import copy
import unittest

from app.result_availability_ledger import (
    ResultAvailabilityLedgerError, append_observations,
    build_result_observation, first_terminal_observation,
    validate_result_observation,
)


class ResultAvailabilityLedgerTests(unittest.TestCase):
    def observation(self, status, observed_at, run_id="run-1"):
        return build_result_observation(
            provider="fivedollar", competition_id="4160026622",
            fixture_id="fivedollar:fixture-1", source_id="fixture-1",
            endpoint="/v1/fixtures", run_id=run_id, observed_at=observed_at,
            payload={"id": "fixture-1", "status": status, "goals": {"home": 2, "away": 1}},
        )

    def test_records_first_observation_not_settlement_time(self):
        ledger = {"schema_version": 1, "observations": []}
        first = self.observation("scheduled", "2026-11-10T17:00:00Z")
        final = self.observation("finished", "2026-11-10T19:03:12Z", "run-2")
        result = append_observations(ledger, [first, final])
        evidence = first_terminal_observation(
            result["ledger"], provider="fivedollar", fixture_id="fivedollar:fixture-1"
        )
        self.assertEqual(evidence["first_observed_at"], "2026-11-10T19:03:12Z")
        self.assertFalse(evidence["is_settlement_timestamp"])
        self.assertFalse(evidence["historical_availability_reconstructed"])

    def test_duplicate_append_is_idempotent(self):
        item = self.observation("finished", "2026-11-10T19:03:12Z")
        result = append_observations({"schema_version": 1, "observations": []}, [item, item])
        self.assertEqual(result["added_count"], 1)
        self.assertEqual(result["total_observation_count"], 1)

    def test_rejects_naive_observation_time(self):
        with self.assertRaisesRegex(ResultAvailabilityLedgerError, "timezone_missing"):
            self.observation("finished", "2026-11-10T19:03:12")

    def test_rejects_mutated_raw_payload(self):
        item = self.observation("finished", "2026-11-10T19:03:12Z")
        altered = copy.deepcopy(item)
        altered["raw_payload"]["goals"]["home"] = 3
        with self.assertRaisesRegex(ResultAvailabilityLedgerError, "integrity_mismatch"):
            validate_result_observation(altered)

    def test_rejects_time_regression_for_fixture(self):
        first = self.observation("scheduled", "2026-11-10T19:03:12Z")
        earlier = self.observation("finished", "2026-11-10T19:02:12Z", "run-2")
        with self.assertRaisesRegex(ResultAvailabilityLedgerError, "time_regression"):
            append_observations({"schema_version": 1, "observations": [first]}, [earlier])

    def test_no_terminal_observation_returns_none(self):
        item = self.observation("scheduled", "2026-11-10T17:00:00Z")
        ledger = append_observations({"schema_version": 1, "observations": []}, [item])["ledger"]
        self.assertIsNone(first_terminal_observation(
            ledger, provider="fivedollar", fixture_id="fivedollar:fixture-1"
        ))


if __name__ == "__main__":
    unittest.main()
