import json
import tempfile
import unittest
from pathlib import Path

from scripts.ingest_the_odds_api_evidence import (
    OfflineOddsIngestError, ingest,
)


class OfflineOddsEvidenceIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.event_path = self.root / "event.json"
        self.crosswalk_path = self.root / "crosswalk.json"
        self.ledger_path = self.root / "ledger.json"
        self.event_path.write_text(json.dumps({
            "id": "event-1",
            "commence_time": "2026-11-10T12:00:00Z",
            "home_team": "Home",
            "away_team": "Away",
            "bookmakers": [{
                "key": "book-a",
                "last_update": "2026-11-10T10:00:00Z",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Home", "price": 2.0},
                        {"name": "Draw", "price": 3.0},
                        {"name": "Away", "price": 4.0},
                    ],
                }],
            }],
        }))
        self.crosswalk_path.write_text(json.dumps({
            "provider_event_id": "event-1",
            "fixture_id": "veltrix:fixture-1",
            "kickoff_at": "2026-11-10T12:00:00Z",
            "home_team": "Home",
            "away_team": "Away",
            "mapping_status": "verified",
            "crosswalk_evidence_sha256": "f" * 64,
        }))

    def tearDown(self):
        self.temp.cleanup()

    def run_ingest(self):
        return ingest(
            event_path=str(self.event_path),
            crosswalk_path=str(self.crosswalk_path),
            retrieved_at="2026-11-10T11:00:00Z",
            source_payload_sha256="a" * 64,
            ledger_path=str(self.ledger_path),
        )

    def test_writes_local_ledger_atomically_and_is_idempotent(self):
        first = self.run_ingest()
        second = self.run_ingest()
        ledger = json.loads(self.ledger_path.read_text())
        self.assertEqual(first["observations_added"], 1)
        self.assertEqual(second["observations_added"], 0)
        self.assertEqual(len(ledger["observations"]), 1)
        self.assertEqual(first["network_requests"], 0)
        self.assertEqual(first["database_writes"], 0)
        self.assertEqual(first["telegram_deliveries"], 0)

    def test_rejects_invalid_crosswalk_without_modifying_existing_ledger(self):
        self.run_ingest()
        original = self.ledger_path.read_bytes()
        crosswalk = json.loads(self.crosswalk_path.read_text())
        crosswalk["mapping_status"] = "pending"
        self.crosswalk_path.write_text(json.dumps(crosswalk))
        with self.assertRaisesRegex(OfflineOddsIngestError, "crosswalk_not_verified"):
            self.run_ingest()
        self.assertEqual(self.ledger_path.read_bytes(), original)

    def test_rejects_symlink_destination(self):
        target = self.root / "target.json"
        target.write_text('{"schema_version":1,"observations":[]}')
        self.ledger_path.symlink_to(target)
        with self.assertRaisesRegex(OfflineOddsIngestError, "symlink_rejected"):
            self.run_ingest()
        self.assertEqual(json.loads(target.read_text()), {
            "schema_version": 1, "observations": [],
        })


if __name__ == "__main__":
    unittest.main()
