import base64
import copy
import unittest

from app.encrypted_source_evidence import (
    EncryptedEvidenceError, assert_sanitized_report_has_no_raw_payload,
    decrypt_and_verify_source_evidence, encrypt_source_evidence,
)
from app.source_payload_provenance import canonical_payload_sha256, SourcePayloadProvenanceError


class EncryptedSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.key = base64.b64encode(bytes(range(32))).decode()
        payload = {"id": 7, "league": {"id": "3405541143"}, "score": [2, 1]}
        record = {
            "schema_version": 1, "provider": "fivedollar", "source_id": "7",
            "competition_key": "3405541143", "season": "2026",
            "home_team_source_id": "1", "away_team_source_id": "2",
            "home_team_name": "A", "away_team_name": "B",
            "kickoff_at": "2026-11-01T12:00:00Z", "source_status": "finished",
            "normalized_status": "finished", "home_score": 2, "away_score": 1,
            "endpoint": "leagues/3405541143/fixtures",
            "retrieved_at": "2026-11-10T04:00:00Z",
            "payload_sha256": canonical_payload_sha256(payload), "run_id": "run-1",
        }
        self.report = {
            "report_sha256": "a" * 64, "records": [record], "quarantine": [],
            "window": {"start_date": "2026-11-01", "end_date": "2026-11-01",
                       "timezone": "Africa/Lagos"},
        }
        self.evidence = [{
            "provider": "fivedollar", "endpoint": record["endpoint"], "source_id": "7",
            "run_id": "run-1", "retrieved_at": record["retrieved_at"],
            "payload": payload, "payload_sha256": canonical_payload_sha256(payload),
            "normalized_record": record,
            "normalized_record_sha256": canonical_payload_sha256(record),
        }]
        self.envelope, self.manifest = encrypt_source_evidence(
            self.evidence, report=self.report, key=self.key
        )

    def test_round_trip_and_manifest_binding(self):
        result = decrypt_and_verify_source_evidence(
            self.envelope, report=self.report, manifest=self.manifest, key=self.key
        )
        self.assertEqual(result, self.evidence)

    def test_tampered_ciphertext_rejected(self):
        changed = self.envelope[:-3] + bytes([self.envelope[-3] ^ 1]) + self.envelope[-2:]
        with self.assertRaisesRegex(EncryptedEvidenceError, "ciphertext_digest_mismatch"):
            decrypt_and_verify_source_evidence(
                changed, report=self.report, manifest=self.manifest, key=self.key
            )

    def test_wrong_key_rejected(self):
        wrong = base64.b64encode(b"x" * 32).decode()
        with self.assertRaisesRegex(EncryptedEvidenceError, "authentication_failed"):
            decrypt_and_verify_source_evidence(
                self.envelope, report=self.report, manifest=self.manifest, key=wrong
            )

    def test_wrong_report_binding_rejected(self):
        report = copy.deepcopy(self.report)
        report["report_sha256"] = "b" * 64
        with self.assertRaisesRegex(EncryptedEvidenceError, "binding_mismatch"):
            decrypt_and_verify_source_evidence(
                self.envelope, report=report, manifest=self.manifest, key=self.key
            )

    def test_missing_evidence_rejected(self):
        with self.assertRaisesRegex(EncryptedEvidenceError, "count_mismatch"):
            encrypt_source_evidence([], report=self.report, key=self.key)

    def test_plaintext_report_guard(self):
        assert_sanitized_report_has_no_raw_payload(self.report)
        leaked = {"records": [{"raw_payload": {"token": "x"}}]}
        with self.assertRaisesRegex(EncryptedEvidenceError, "leaked"):
            assert_sanitized_report_has_no_raw_payload(leaked)

    def test_payload_mutation_rejected_after_authenticated_decryption(self):
        evidence = copy.deepcopy(self.evidence)
        evidence[0]["payload"]["score"] = [9, 0]
        with self.assertRaises(SourcePayloadProvenanceError):
            encrypt_source_evidence(evidence, report=self.report, key=self.key)


if __name__ == "__main__":
    unittest.main()
