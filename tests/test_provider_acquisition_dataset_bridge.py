import unittest

from app.provider_fixture_normalizer import normalize_striker_game
from app.provider_source_evidence import build_source_evidence
from app.settlement_timestamp_source import build_settlement_timestamp_evidence
from app.provider_acquisition_dataset_bridge import (
    AcquisitionDatasetBridgeError, acquisition_record_to_history_row,
)


CONTRACT = {
    "source_id": "qualified-source-a",
    "qualification_status": "qualified",
    "qualification_digest": "a" * 64,
    "timestamp_field": "match.full_time_whistle_at",
    "timestamp_semantics": "final_whistle",
    "supported_competitions": ["soccer"],
}
IDENTITY = {
    "source_fixture_id": "external-match-1",
    "competition_id": "soccer",
    "home_team_id": "h",
    "away_team_id": "a",
    "kickoff_at": "2026-11-01T15:00:00Z",
}
TIMESTAMP_PAYLOAD = {
    "match": {"full_time_whistle_at": "2026-11-01T16:52:13Z"}
}


class AcquisitionDatasetBridgeTests(unittest.TestCase):
    def provider_record(self, retrieved_at="2026-11-02T00:00:00Z"):
        payload = {
            "game_id": "g-1", "starts_at": "2026-11-01T15:00:00Z",
            "status": "final", "status_detail": "FT",
            "home": {"team_id": "h", "name": "Home", "score": 2},
            "away": {"team_id": "a", "name": "Away", "score": 1},
        }
        record = normalize_striker_game(
            payload, competition_key="soccer", endpoint="list_games",
            retrieved_at=retrieved_at, run_id="run-1",
        )
        record["source_evidence"] = build_source_evidence(
            provider="strikerapi", payload=payload, normalized_record=record,
        )
        return record

    def settlement_package(self):
        evidence = build_settlement_timestamp_evidence(
            source_contract=CONTRACT, raw_payload=TIMESTAMP_PAYLOAD,
            fixture_identity=IDENTITY, expected_fixture_identity=IDENTITY,
            kickoff_at=IDENTITY["kickoff_at"],
            observed_at="2026-11-01T16:52:14Z",
            retrieved_at="2026-11-01T16:53:00Z",
        )
        return {
            "source_contract": CONTRACT,
            "raw_payload": TIMESTAMP_PAYLOAD,
            "fixture_identity": IDENTITY,
            "expected_fixture_identity": IDENTITY,
            "evidence": evidence,
        }

    def test_terminal_status_without_settlement_timestamp_cannot_enter_training_history(self):
        record = self.provider_record()
        self.assertTrue(record["settlement_evidence"]["terminal_status_confirmed"])
        self.assertIsNone(record["settled_at"])
        with self.assertRaisesRegex(AcquisitionDatasetBridgeError, "settlement_timestamp_unavailable"):
            acquisition_record_to_history_row(record)

    def test_qualified_external_final_whistle_evidence_is_joined(self):
        row = acquisition_record_to_history_row(
            self.provider_record(),
            settlement_timestamp_package=self.settlement_package(),
        )
        self.assertEqual(row["settled_at"], "2026-11-01T16:52:13Z")
        self.assertEqual(row["settlement_source_id"], "qualified-source-a")
        self.assertEqual(row["settlement_qualification_digest"], "a" * 64)
        self.assertEqual(len(row["settlement_evidence_sha256"]), 64)

    def test_external_timestamp_evidence_tampering_is_rejected(self):
        package = self.settlement_package()
        package["evidence"]["settlement_at"] = "2026-11-01T16:50:00Z"
        with self.assertRaisesRegex(AcquisitionDatasetBridgeError, "qualified_settlement_rejected"):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=package,
            )

    def test_unbound_raw_payload_cannot_enter_training_history(self):
        record = self.provider_record()
        record["source_evidence"]["raw_payload"]["home"]["score"] = 9
        with self.assertRaises(AcquisitionDatasetBridgeError):
            acquisition_record_to_history_row(
                record, settlement_timestamp_package=self.settlement_package(),
            )

    def test_provider_retrieval_before_external_settlement_is_rejected(self):
        record = self.provider_record(retrieved_at="2026-11-01T16:00:00Z")
        with self.assertRaises(AcquisitionDatasetBridgeError):
            acquisition_record_to_history_row(
                record, settlement_timestamp_package=self.settlement_package(),
            )


if __name__ == "__main__":
    unittest.main()
