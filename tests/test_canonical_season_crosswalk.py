import copy
import unittest

from app.canonical_season_crosswalk import (
    SCHEMA, SeasonCrosswalkError, resolve_canonical_season,
    sign_season_crosswalk_registry, verify_season_crosswalk_registry,
)

KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/veltrix-season-test-key"


class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


KMS = FakeKms()


def registry():
    return {
        "schema": SCHEMA,
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2027-01-01T00:00:00Z",
        "mappings": [{
            "provider": "provider-a",
            "competition_id": "league-1",
            "source_season": "2025/26",
            "canonical_season_id": "league-1:2025-2026",
            "evidence_sha256": ["a" * 64],
            "reviewer": "data-governance-review",
            "reviewed_at": "2026-01-02T00:00:00Z",
            "valid_from": "2026-01-03T00:00:00Z",
            "valid_until": "2026-12-31T00:00:00Z",
            "revoked_at": None,
        }],
    }


def signed(value=None):
    return sign_season_crosswalk_registry(
        kms_client=KMS, key_arn=KEY_ARN,
        trusted_key_regions={KEY_ARN: "eu-west-1"},
        registry=registry() if value is None else value,
    )


class CanonicalSeasonCrosswalkTests(unittest.TestCase):
    def test_resolves_exact_provider_competition_and_source_season(self):
        result = resolve_canonical_season(
            registry=signed(), trusted_kms_clients={KEY_ARN: KMS},
            provider="provider-a", competition_id="league-1",
            source_season="2025/26", as_of="2026-06-01T00:00:00Z",
        )
        self.assertEqual(result["canonical_season_id"], "league-1:2025-2026")
        self.assertEqual(result["reviewer"], "data-governance-review")
        self.assertEqual(len(result["registry_sha256"]), 64)

    def test_provider_and_competition_are_part_of_mapping_identity(self):
        value = signed()
        for provider, competition in (
            ("provider-b", "league-1"), ("provider-a", "league-2"),
        ):
            with self.assertRaisesRegex(SeasonCrosswalkError, "mapping_missing_or_inactive"):
                resolve_canonical_season(
                    registry=value, trusted_kms_clients={KEY_ARN: KMS},
                    provider=provider, competition_id=competition,
                    source_season="2025/26", as_of="2026-06-01T00:00:00Z",
                )

    def test_missing_source_season_is_not_inferred(self):
        with self.assertRaisesRegex(SeasonCrosswalkError, "mapping_missing_or_inactive"):
            resolve_canonical_season(
                registry=signed(), trusted_kms_clients={KEY_ARN: KMS},
                provider="provider-a", competition_id="league-1",
                source_season="", as_of="2026-06-01T00:00:00Z",
            )

    def test_untrusted_signing_key_is_rejected(self):
        with self.assertRaisesRegex(SeasonCrosswalkError, "signing_key_not_trusted"):
            verify_season_crosswalk_registry(
                registry=signed(), trusted_kms_clients={},
                as_of="2026-06-01T00:00:00Z",
            )

    def test_tampered_mapping_is_rejected_by_signature(self):
        value = signed()
        value["mappings"][0]["canonical_season_id"] = "league-1:2024-2025"
        with self.assertRaisesRegex(SeasonCrosswalkError, "signature_invalid"):
            verify_season_crosswalk_registry(
                registry=value, trusted_kms_clients={KEY_ARN: KMS},
                as_of="2026-06-01T00:00:00Z",
            )

    def test_duplicate_source_identity_is_rejected(self):
        value = registry()
        value["mappings"].append(copy.deepcopy(value["mappings"][0]))
        with self.assertRaisesRegex(SeasonCrosswalkError, "duplicate_source_mapping"):
            signed(value)

    def test_expired_and_revoked_mappings_are_inactive(self):
        value = registry()
        value["mappings"][0]["revoked_at"] = "2026-05-01T00:00:00Z"
        signed_value = signed(value)
        with self.assertRaisesRegex(SeasonCrosswalkError, "mapping_missing_or_inactive"):
            resolve_canonical_season(
                registry=signed_value, trusted_kms_clients={KEY_ARN: KMS},
                provider="provider-a", competition_id="league-1",
                source_season="2025/26", as_of="2026-06-01T00:00:00Z",
            )

    def test_naive_review_timestamp_is_rejected(self):
        value = registry()
        value["mappings"][0]["reviewed_at"] = "2026-01-02T00:00:00"
        with self.assertRaisesRegex(SeasonCrosswalkError, "timezone_missing"):
            signed(value)


if __name__ == "__main__":
    unittest.main()
