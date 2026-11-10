import copy
import hashlib
import unittest

from app.source_qualification_registry import (
    SCHEMA, SourceQualificationRegistryError,
    canonical_json_bytes, canonical_sha256,
    sign_source_qualification_registry,
    verify_source_qualification_registry,
    resolve_qualified_settlement_source,
)


KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/veltrix-test-key"


class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


class SourceQualificationRegistryTests(unittest.TestCase):
    def setUp(self):
        self.kms = FakeKms()
        self.record = {
            "source_id": "official-match-clock-v1",
            "qualification_status": "qualified",
            "timestamp_field": "match.full_time_whistle_at",
            "timestamp_semantics": "final_whistle",
            "supported_competitions": ["england-premier-league", "france-ligue-1"],
            "qualification_evidence_sha256": ["a" * 64, "b" * 64],
            "qualified_at": "2026-10-01T10:00:00Z",
        }
        self.entry = {
            "qualification_record": self.record,
            "qualification_record_sha256": canonical_sha256(self.record),
            "valid_from": "2026-10-01T10:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
            "revoked_at": None,
        }
        self.registry = {
            "schema": SCHEMA,
            "issued_at": "2026-10-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "sources": [self.entry],
        }
        self.trusted = {KEY_ARN: self.kms}

    def signed(self, registry=None):
        return sign_source_qualification_registry(
            kms_client=self.kms, key_arn=KEY_ARN,
            registry=copy.deepcopy(registry or self.registry),
        )

    def test_valid_signed_registry_resolves_only_scoped_contract(self):
        signed = self.signed()
        result = resolve_qualified_settlement_source(
            registry=signed, source_id="official-match-clock-v1",
            competition_id="england-premier-league",
            trusted_kms_clients=self.trusted, as_of="2026-11-10T10:00:00Z",
        )
        self.assertEqual(result["contract"]["qualification_status"], "qualified")
        self.assertEqual(result["contract"]["timestamp_semantics"], "final_whistle")
        self.assertEqual(result["contract"]["qualification_digest"], canonical_sha256(self.record))

    def test_unknown_signing_key_rejected(self):
        signed = self.signed()
        with self.assertRaisesRegex(SourceQualificationRegistryError, "registry_signing_key_not_trusted"):
            verify_source_qualification_registry(
                registry=signed, trusted_kms_clients={}, as_of="2026-11-10T10:00:00Z",
            )

    def test_registry_tampering_invalidates_signature(self):
        signed = self.signed()
        signed["sources"][0]["qualification_record"]["timestamp_field"] = "match.updated_at"
        with self.assertRaisesRegex(SourceQualificationRegistryError, "registry_signature_invalid"):
            verify_source_qualification_registry(
                registry=signed, trusted_kms_clients=self.trusted, as_of="2026-11-10T10:00:00Z",
            )

    def test_qualification_record_digest_mismatch_rejected_after_resigning(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"][0]["qualification_record"]["timestamp_field"] = "match.updated_at"
        signed = self.signed(changed)
        with self.assertRaisesRegex(SourceQualificationRegistryError, "qualification_record_digest_mismatch"):
            verify_source_qualification_registry(
                registry=signed, trusted_kms_clients=self.trusted, as_of="2026-11-10T10:00:00Z",
            )

    def test_non_final_whistle_semantics_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"][0]["qualification_record"]["timestamp_semantics"] = "provider_updated_at"
        changed["sources"][0]["qualification_record_sha256"] = canonical_sha256(changed["sources"][0]["qualification_record"])
        signed = self.signed(changed)
        with self.assertRaisesRegex(SourceQualificationRegistryError, "qualification_timestamp_semantics_unsupported"):
            verify_source_qualification_registry(
                registry=signed, trusted_kms_clients=self.trusted, as_of="2026-11-10T10:00:00Z",
            )

    def test_expired_registry_rejected(self):
        with self.assertRaisesRegex(SourceQualificationRegistryError, "registry_outside_validity_window"):
            verify_source_qualification_registry(
                registry=self.signed(), trusted_kms_clients=self.trusted,
                as_of="2027-01-01T00:00:00Z",
            )

    def test_revoked_source_not_resolved(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"][0]["revoked_at"] = "2026-11-01T00:00:00Z"
        signed = self.signed(changed)
        with self.assertRaisesRegex(SourceQualificationRegistryError, "settlement_source_not_qualified_or_inactive"):
            resolve_qualified_settlement_source(
                registry=signed, source_id="official-match-clock-v1",
                competition_id="england-premier-league",
                trusted_kms_clients=self.trusted, as_of="2026-11-10T10:00:00Z",
            )

    def test_unqualified_competition_rejected(self):
        with self.assertRaisesRegex(SourceQualificationRegistryError, "competition_not_qualified_for_timestamp_source"):
            resolve_qualified_settlement_source(
                registry=self.signed(), source_id="official-match-clock-v1",
                competition_id="unqualified-league",
                trusted_kms_clients=self.trusted, as_of="2026-11-10T10:00:00Z",
            )

    def test_duplicate_source_ids_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"].append(copy.deepcopy(changed["sources"][0]))
        signed = self.signed(changed)
        with self.assertRaisesRegex(SourceQualificationRegistryError, "registry_duplicate_source_id"):
            verify_source_qualification_registry(
                registry=signed, trusted_kms_clients=self.trusted, as_of="2026-11-10T10:00:00Z",
            )

    def test_unrecognized_top_level_registry_fields_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["operator_note"] = "unreviewed"
        with self.assertRaisesRegex(SourceQualificationRegistryError, "registry_shape_invalid"):
            sign_source_qualification_registry(
                kms_client=self.kms, key_arn=KEY_ARN, registry=changed,
            )

    def test_unrecognized_signature_fields_rejected(self):
        signed = self.signed()
        signed["signature"]["operator"] = "untrusted"
        with self.assertRaisesRegex(SourceQualificationRegistryError, "registry_signature_shape_invalid"):
            verify_source_qualification_registry(
                registry=signed, trusted_kms_clients=self.trusted,
                as_of="2026-11-10T10:00:00Z",
            )

    def test_source_cannot_be_active_before_qualification(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"][0]["valid_from"] = "2026-09-01T00:00:00Z"
        signed = self.signed(changed)
        with self.assertRaisesRegex(SourceQualificationRegistryError, "source_active_before_qualification"):
            verify_source_qualification_registry(
                registry=signed, trusted_kms_clients=self.trusted,
                as_of="2026-11-10T10:00:00Z",
            )

    def test_naive_verification_time_rejected(self):
        with self.assertRaisesRegex(SourceQualificationRegistryError, "as_of_timezone_missing"):
            verify_source_qualification_registry(
                registry=self.signed(), trusted_kms_clients=self.trusted,
                as_of="2026-11-10T10:00:00",
            )


if __name__ == "__main__":
    unittest.main()
