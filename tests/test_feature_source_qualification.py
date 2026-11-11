import copy
import unittest

from app.feature_source_qualification import (
    SCHEMA, FeatureSourceQualificationError,
    sign_feature_source_qualification_registry,
    verify_feature_source_qualification_registry, validate_feature_source,
)

KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/feature-source-test"


class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


class FeatureSourceQualificationTests(unittest.TestCase):
    def setUp(self):
        self.kms = FakeKms()
        self.trusted = {KEY_ARN: self.kms}
        self.registry = {
            "schema": SCHEMA,
            "issued_at": "2026-10-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "sources": [{
                "source": "provider-x",
                "qualified_features": ["home_rolling_xg_for", "away_rolling_xg_for"],
                "supported_competitions": ["league-a"],
                "observed_at_semantics": "source_measurement_timestamp",
                "available_at_semantics": "first_publication_timestamp",
                "qualification_evidence_sha256": ["a" * 64],
                "reviewer": "data-governance",
                "qualified_at": "2026-10-01T00:00:00Z",
                "valid_from": "2026-10-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
                "revoked_at": None,
            }],
        }

    def signed(self, registry=None):
        return sign_feature_source_qualification_registry(
            kms_client=self.kms, key_arn=KEY_ARN,
            trusted_key_regions={KEY_ARN: "eu-west-1"},
            registry=copy.deepcopy(registry or self.registry),
        )

    def verified(self, registry=None, as_of="2026-11-10T00:00:00Z"):
        return verify_feature_source_qualification_registry(
            registry=self.signed(registry), trusted_kms_clients=self.trusted, as_of=as_of,
        )

    def test_valid_source_is_scoped_to_feature_and_competition(self):
        verified = self.verified()
        evidence = validate_feature_source(
            verified_registry=verified, source="provider-x",
            feature_name="home_rolling_xg_for", competition_id="league-a",
        )
        self.assertEqual(evidence["signing_key_arn"], KEY_ARN)
        self.assertEqual(evidence["observed_at_semantics"], "source_measurement_timestamp")

    def test_unqualified_source_rejected(self):
        with self.assertRaisesRegex(FeatureSourceQualificationError, "feature_source_not_qualified"):
            validate_feature_source(
                verified_registry=self.verified(), source="unknown",
                feature_name="home_rolling_xg_for", competition_id="league-a",
            )

    def test_feature_outside_source_scope_rejected(self):
        with self.assertRaisesRegex(FeatureSourceQualificationError, "feature_not_qualified_for_source"):
            validate_feature_source(
                verified_registry=self.verified(), source="provider-x",
                feature_name="home_lineup_strength", competition_id="league-a",
            )

    def test_competition_outside_source_scope_rejected(self):
        with self.assertRaisesRegex(FeatureSourceQualificationError, "feature_source_competition_unsupported"):
            validate_feature_source(
                verified_registry=self.verified(), source="provider-x",
                feature_name="home_rolling_xg_for", competition_id="league-b",
            )

    def test_expired_source_is_not_resolved(self):
        verified = self.verified(as_of="2027-01-01T00:00:00Z")
        with self.assertRaisesRegex(FeatureSourceQualificationError, "feature_source_not_qualified"):
            validate_feature_source(
                verified_registry=verified, source="provider-x",
                feature_name="home_rolling_xg_for", competition_id="league-a",
            )

    def test_revoked_source_is_not_resolved(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"][0]["revoked_at"] = "2026-11-01T00:00:00Z"
        verified = self.verified(changed)
        with self.assertRaisesRegex(FeatureSourceQualificationError, "feature_source_not_qualified"):
            validate_feature_source(
                verified_registry=verified, source="provider-x",
                feature_name="home_rolling_xg_for", competition_id="league-a",
            )

    def test_registry_tampering_invalidates_signature(self):
        signed = self.signed()
        signed["sources"][0]["qualified_features"].append("home_lineup_strength")
        with self.assertRaisesRegex(FeatureSourceQualificationError, "registry_signature_invalid"):
            verify_feature_source_qualification_registry(
                registry=signed, trusted_kms_clients=self.trusted,
                as_of="2026-11-10T00:00:00Z",
            )

    def test_pre_signed_registry_cannot_be_resigned(self):
        with self.assertRaisesRegex(FeatureSourceQualificationError, "registry_already_signed"):
            sign_feature_source_qualification_registry(
                kms_client=self.kms, key_arn=KEY_ARN,
                trusted_key_regions={KEY_ARN: "eu-west-1"},
                registry=self.signed(),
            )

    def test_missing_evidence_digest_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"][0]["qualification_evidence_sha256"] = []
        with self.assertRaisesRegex(FeatureSourceQualificationError, "source_evidence_invalid"):
            self.signed(changed)

    def test_naive_validity_timestamp_rejected(self):
        changed = copy.deepcopy(self.registry)
        changed["sources"][0]["valid_from"] = "2026-10-01T00:00:00"
        with self.assertRaisesRegex(FeatureSourceQualificationError, "timezone_missing"):
            self.signed(changed)


if __name__ == "__main__":
    unittest.main()
