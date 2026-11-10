import unittest

from app.bookmaker_odds_evidence import (
    BookmakerOddsEvidenceError, append_odds_observations,
    build_odds_observation, latest_pre_kickoff_snapshot,
    validate_odds_observation,
)


class BookmakerOddsEvidenceTests(unittest.TestCase):
    def observation(self, captured="2026-11-10T10:00:00Z", market="1x2",
                    fixture="fx-1", bookmaker="book-a", odds=None):
        selections = ("home", "draw", "away") if market == "1x2" else ("no", "yes")
        odds = odds or {key: 2.0 for key in selections}
        return build_odds_observation(
            provider="odds-provider", provider_event_id="event-123",
            fixture_id=fixture, market=market, bookmaker=bookmaker,
            captured_at=captured, kickoff_at="2026-11-10T12:00:00Z",
            decimal_odds=odds, raw_payload={"event": "event-123", "odds": odds},
            source_payload_sha256="a" * 64,
        )

    def test_builds_de_vigged_probabilities_and_verifiable_observation(self):
        item = self.observation(odds={"home": 2.0, "draw": 4.0, "away": 4.0})
        self.assertAlmostEqual(item["overround"], 1.0)
        self.assertAlmostEqual(item["implied_probabilities"]["home"], 0.5)
        self.assertTrue(validate_odds_observation(item)["valid"])

    def test_rejects_odds_captured_after_kickoff(self):
        with self.assertRaisesRegex(BookmakerOddsEvidenceError, "captured_after_kickoff"):
            self.observation(captured="2026-11-10T12:01:00Z")

    def test_rejects_incomplete_market_selection_set(self):
        with self.assertRaisesRegex(BookmakerOddsEvidenceError, "selection_set_invalid"):
            self.observation(odds={"home": 2.0, "draw": 3.0})

    def test_append_is_idempotent_and_preserves_order(self):
        first = self.observation()
        later = self.observation(captured="2026-11-10T11:00:00Z")
        ledger = {"schema_version": 1, "observations": []}
        one = append_odds_observations(ledger, [first])
        two = append_odds_observations(one["ledger"], [first, later])
        self.assertEqual(one["added_count"], 1)
        self.assertEqual(two["added_count"], 1)
        self.assertEqual(two["total_observation_count"], 2)
        self.assertEqual(two["database_writes"], 0)

    def test_rejects_observation_time_regression(self):
        later = self.observation(captured="2026-11-10T11:00:00Z")
        earlier = self.observation(captured="2026-11-10T10:00:00Z")
        ledger = {"schema_version": 1, "observations": [later]}
        with self.assertRaisesRegex(BookmakerOddsEvidenceError, "time_regression"):
            append_odds_observations(ledger, [earlier])

    def test_selects_latest_snapshot_before_kickoff(self):
        first = self.observation(captured="2026-11-10T09:00:00Z")
        later = self.observation(captured="2026-11-10T11:00:00Z")
        ledger = append_odds_observations(
            {"schema_version": 1, "observations": []}, [first, later]
        )["ledger"]
        chosen = latest_pre_kickoff_snapshot(
            ledger, fixture_id="fx-1", market="1x2", bookmaker="book-a",
            kickoff_at="2026-11-10T12:00:00Z",
        )
        self.assertEqual(chosen["captured_at"], "2026-11-10T11:00:00+00:00")
        self.assertEqual(chosen["timestamp_semantics"], "latest_observed_pre_kickoff_snapshot")

    def test_rejects_modified_observation(self):
        item = self.observation()
        item["decimal_odds"]["home"] = 99.0
        with self.assertRaises(BookmakerOddsEvidenceError):
            validate_odds_observation(item)


if __name__ == "__main__":
    unittest.main()
