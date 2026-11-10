import unittest

from app.provider_fixture_normalizer import normalize_striker_game
from app.provider_source_evidence import build_source_evidence
from app.provider_acquisition_dataset_bridge import (
    AcquisitionDatasetBridgeError, acquisition_record_to_history_row,
)


class AcquisitionDatasetBridgeTests(unittest.TestCase):
    def test_terminal_status_without_settlement_timestamp_cannot_enter_training_history(self):
        payload = {
            "game_id": "g-1", "starts_at": "2026-11-01T15:00:00Z",
            "status": "final", "status_detail": "FT",
            "home": {"team_id": "h", "name": "Home", "score": 2},
            "away": {"team_id": "a", "name": "Away", "score": 1},
        }
        record = normalize_striker_game(
            payload, competition_key="soccer", endpoint="list_games",
            retrieved_at="2026-11-02T00:00:00Z", run_id="run-1",
        )
        record["source_evidence"] = build_source_evidence(
            provider="strikerapi", payload=payload, normalized_record=record,
        )
        self.assertTrue(record["settlement_evidence"]["terminal_status_confirmed"])
        self.assertIsNone(record["settled_at"])
        with self.assertRaisesRegex(AcquisitionDatasetBridgeError, "settlement_timestamp_unavailable"):
            acquisition_record_to_history_row(record)

    def test_unbound_raw_payload_cannot_enter_training_history(self):
        payload = {
            "game_id": "g-2", "starts_at": "2026-11-01T15:00:00Z",
            "status": "final", "status_detail": "FT",
            "home": {"team_id": "h", "name": "Home", "score": 2},
            "away": {"team_id": "a", "name": "Away", "score": 1},
        }
        record = normalize_striker_game(
            payload, competition_key="soccer", endpoint="list_games",
            retrieved_at="2026-11-02T00:00:00Z", run_id="run-1",
        )
        record["source_evidence"] = build_source_evidence(
            provider="strikerapi", payload=payload, normalized_record=record,
        )
        record["source_evidence"]["raw_payload"]["home"]["score"] = 9
        with self.assertRaises(AcquisitionDatasetBridgeError):
            acquisition_record_to_history_row(record)


if __name__ == "__main__":
    unittest.main()
