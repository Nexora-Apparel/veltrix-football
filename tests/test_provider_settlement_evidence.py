import copy
import unittest

from app.provider_settlement_evidence import (
    SettlementEvidenceError, extract_fivedollar_settlement,
    extract_strikerapi_settlement, validate_settlement_evidence,
)


class ProviderSettlementEvidenceTests(unittest.TestCase):
    def test_strikerapi_actual_documented_fields_confirm_terminal_state_not_time(self):
        payload = {
            "game_id": "740968", "starts_at": "2026-05-24T15:00:00.000Z",
            "status": "final", "status_detail": "FT",
            "home": {"team_id": "384", "name": "Crystal Palace", "score": 1},
            "away": {"team_id": "359", "name": "Arsenal", "score": 2},
        }
        evidence = extract_strikerapi_settlement(payload)
        self.assertTrue(evidence["terminal_status_confirmed"])
        self.assertEqual(evidence["terminal_status_field"], "status")
        self.assertEqual(evidence["terminal_detail_field"], "status_detail")
        self.assertIsNone(evidence["settlement_at"])
        self.assertFalse(evidence["settlement_time_available"])

    def test_fivedollar_actual_documented_fields_confirm_terminal_state_not_time(self):
        payload = {
            "id": 422841891, "kickoff_utc": "2026-07-12T00:00:00+00:00",
            "status": "finished", "status_code": "full",
            "goals": {"home": 3, "away": 1},
        }
        evidence = extract_fivedollar_settlement(payload)
        self.assertTrue(evidence["terminal_status_confirmed"])
        self.assertEqual(evidence["terminal_status_field"], "status")
        self.assertEqual(evidence["terminal_detail_field"], "status_code")
        self.assertIsNone(evidence["settlement_at"])
        self.assertFalse(evidence["settlement_time_available"])

    def test_nonterminal_payload_is_not_confirmed(self):
        self.assertFalse(extract_strikerapi_settlement({"status": "scheduled"})["terminal_status_confirmed"])
        self.assertFalse(extract_fivedollar_settlement({"status": "in_play"})["terminal_status_confirmed"])

    def test_no_retrieval_time_fallback_or_wall_clock_inference(self):
        payload = {"status": "final", "status_detail": "FT", "retrieved_at": "2026-11-10T12:00:00Z"}
        evidence = extract_strikerapi_settlement(payload)
        self.assertIsNone(evidence["settlement_at"])
        self.assertIsNone(evidence["settlement_timestamp_field"])
        with self.assertRaisesRegex(SettlementEvidenceError, "settlement_timestamp_unavailable"):
            validate_settlement_evidence(evidence, provider="strikerapi", payload=payload)

    def test_modified_settlement_evidence_is_rejected(self):
        payload = {"status": "finished", "status_code": "full"}
        evidence = extract_fivedollar_settlement(payload)
        altered = copy.deepcopy(evidence)
        altered["settlement_at"] = "2026-07-12T02:00:00Z"
        with self.assertRaisesRegex(SettlementEvidenceError, "payload_binding_mismatch"):
            validate_settlement_evidence(altered, provider="fivedollar", payload=payload)


if __name__ == "__main__":
    unittest.main()
