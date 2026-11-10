import unittest

from app.bookmaker_odds_evidence import append_odds_observations, validate_odds_observation
from app.the_odds_api_evidence_adapter import (
    OddsProviderAdapterError, adapt_the_odds_api_event,
)


class TheOddsApiEvidenceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "id": "event-123",
            "commence_time": "2026-11-10T12:00:00Z",
            "home_team": "Home FC",
            "away_team": "Away FC",
            "bookmakers": [{
                "key": "book-a",
                "last_update": "2026-11-10T10:00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Home FC", "price": 2.0},
                        {"name": "Draw", "price": 3.2},
                        {"name": "Away FC", "price": 4.0},
                    ]},
                    {"key": "btts", "outcomes": [
                        {"name": "Yes", "price": 1.8},
                        {"name": "No", "price": 2.0},
                    ]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over", "point": 2.5, "price": 1.9},
                        {"name": "Under", "point": 2.5, "price": 1.9},
                        {"name": "Over", "point": 3.5, "price": 2.5},
                        {"name": "Under", "point": 3.5, "price": 1.5},
                    ]},
                ],
            }],
        }
        self.crosswalk = {
            "provider_event_id": "event-123",
            "fixture_id": "veltrix:fixture-900",
            "kickoff_at": "2026-11-10T12:00:00Z",
            "home_team": "Home FC",
            "away_team": "Away FC",
            "mapping_status": "verified",
            "crosswalk_evidence_sha256": "f" * 64,
        }

    def adapt(self, **kwargs):
        return adapt_the_odds_api_event(
            event_payload=kwargs.get("event_payload", self.event),
            crosswalk=kwargs.get("crosswalk", self.crosswalk),
            retrieved_at=kwargs.get("retrieved_at", "2026-11-10T11:00:00Z"),
            max_quote_age_seconds=kwargs.get("max_quote_age_seconds", 86400),
        )

    def test_extracts_all_supported_markets_with_explicit_crosswalk(self):
        result = self.adapt()
        self.assertEqual(result["observation_count"], 3)
        self.assertEqual(
            {item["market"] for item in result["observations"]},
            {"1x2", "btts", "over_2_5"},
        )
        for item in result["observations"]:
            self.assertEqual(item["fixture_id"], "veltrix:fixture-900")
            self.assertEqual(item["crosswalk_evidence_sha256"], "f" * 64)
            self.assertTrue(validate_odds_observation(item)["valid"])
        ledger = append_odds_observations(
            {"schema_version": 1, "observations": []},
            result["observations"],
        )
        self.assertEqual(ledger["added_count"], 3)

    def test_rejects_unverified_crosswalk(self):
        crosswalk = dict(self.crosswalk, mapping_status="pending")
        with self.assertRaisesRegex(OddsProviderAdapterError, "crosswalk_not_verified"):
            self.adapt(crosswalk=crosswalk)

    def test_rejects_event_id_or_team_mismatch(self):
        event = dict(self.event, id="other-event")
        with self.assertRaisesRegex(OddsProviderAdapterError, "event_crosswalk_id_mismatch"):
            self.adapt(event_payload=event)
        event = dict(self.event, home_team="Different FC")
        with self.assertRaisesRegex(OddsProviderAdapterError, "team_mismatch"):
            self.adapt(event_payload=event)

    def test_rejects_kickoff_mismatch(self):
        crosswalk = dict(self.crosswalk, kickoff_at="2026-11-10T12:05:00Z")
        with self.assertRaisesRegex(OddsProviderAdapterError, "kickoff_mismatch"):
            self.adapt(crosswalk=crosswalk)

    def test_rejects_retrieval_after_kickoff(self):
        with self.assertRaisesRegex(OddsProviderAdapterError, "retrieved_after_kickoff"):
            self.adapt(retrieved_at="2026-11-10T12:01:00Z")

    def test_quarantines_quote_after_kickoff_and_stale_quotes(self):
        event = {
            **self.event,
            "bookmakers": [{
                **self.event["bookmakers"][0],
                "last_update": "2026-11-10T12:01:00Z",
            }],
        }
        result = self.adapt(event_payload=event)
        self.assertEqual(result["observation_count"], 0)
        self.assertIn("quote_after_kickoff", result["rejected"][0]["reason"])
        stale = self.adapt(max_quote_age_seconds=60)
        self.assertEqual(stale["observation_count"], 0)
        self.assertIn("quote_stale", stale["rejected"][0]["reason"])

    def test_ignores_unsupported_and_nonstandard_total_lines(self):
        event = {
            **self.event,
            "bookmakers": [{
                **self.event["bookmakers"][0],
                "markets": [
                    {"key": "totals", "outcomes": [
                        {"name": "Over", "point": 3.5, "price": 2.0},
                        {"name": "Under", "point": 3.5, "price": 2.0},
                    ]},
                    {"key": "unknown_market", "outcomes": []},
                ],
            }],
        }
        result = self.adapt(event_payload=event)
        self.assertEqual(result["observation_count"], 0)

    def test_rejects_crosswalk_digest_that_is_not_a_sha256(self):
        crosswalk = dict(self.crosswalk, crosswalk_evidence_sha256="bad")
        with self.assertRaisesRegex(OddsProviderAdapterError, "crosswalk_evidence_digest_invalid"):
            self.adapt(crosswalk=crosswalk)


if __name__ == "__main__":
    unittest.main()
