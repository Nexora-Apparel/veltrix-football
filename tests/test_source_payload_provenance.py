import unittest

from app.source_payload_provenance import (
    SourcePayloadProvenanceError,
    canonical_payload_sha256,
    validate_source_payload_evidence,
)


class SourcePayloadProvenanceTests(unittest.TestCase):
    def evidence(self):
        payload = {"fixture": {"id": 7, "score": [2, 1]}}
        normalized = {"fixture_id": "7", "home_score": 2, "away_score": 1}
        return {
            "provider": "fivedollar",
            "endpoint": "/fixtures/7",
            "source_id": "7",
            "run_id": "run-1",
            "retrieved_at": "2026-11-10T04:00:00Z",
            "payload": payload,
            "payload_sha256": canonical_payload_sha256(payload),
            "normalized_record": normalized,
            "normalized_record_sha256": canonical_payload_sha256(normalized),
        }

    def test_validates_canonical_payload_and_normalized_record(self):
        result = validate_source_payload_evidence(self.evidence())
        self.assertTrue(result["valid"])
        self.assertEqual(result["source_id"], "7")

    def test_rejects_payload_mutation(self):
        evidence = self.evidence()
        evidence["payload"]["fixture"]["score"] = [9, 0]
        with self.assertRaisesRegex(SourcePayloadProvenanceError, "source_payload_hash_mismatch"):
            validate_source_payload_evidence(evidence)

    def test_rejects_normalized_record_mutation(self):
        evidence = self.evidence()
        evidence["normalized_record"]["home_score"] = 9
        with self.assertRaisesRegex(SourcePayloadProvenanceError, "normalized_record_hash_mismatch"):
            validate_source_payload_evidence(evidence)

    def test_rejects_missing_timezone_and_metadata_mismatch_shape(self):
        evidence = self.evidence()
        evidence["retrieved_at"] = "2026-11-10T04:00:00"
        with self.assertRaisesRegex(SourcePayloadProvenanceError, "timezone_missing"):
            validate_source_payload_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
