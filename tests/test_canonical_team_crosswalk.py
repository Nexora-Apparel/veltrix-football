import copy
import unittest

from app.canonical_team_crosswalk import (
    SCHEMA, TeamCrosswalkError, resolve_canonical_team,
    sign_team_crosswalk_registry, verify_team_crosswalk_registry,
)

KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/veltrix-team-test-key"


class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


KMS = FakeKms()


def mapping(source_id, canonical_id, scope="men_first_team"):
    return {
        "provider": "provider-a",
        "competition_id": "league-1",
        "source_team_id": source_id,
        "canonical_team_id": canonical_id,
        "team_scope": scope,
        "evidence_sha256": ["a" * 64],
        "reviewer": "team-identity-review",
        "reviewed_at": "2026-01-02T00:00:00Z",
        "valid_from": "2026-01-03T00:00:00Z",
        "valid_until": "2026-12-31T00:00:00Z",
        "revoked_at": None,
    }


def registry(mappings=None):
    return {
        "schema": SCHEMA,
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2027-01-01T00:00:00Z",
        "mappings": [mapping("source-team-1", "canonical-team-1")] if mappings is None else mappings,
    }


def signed(value=None):
    return sign_team_crosswalk_registry(
        kms_client=KMS, key_arn=KEY_ARN,
        trusted_key_regions={KEY_ARN: "eu-west-1"},
        registry=registry() if value is None else value,
    )


class CanonicalTeamCrosswalkTests(unittest.TestCase):
    def test_resolves_exact_provider_competition_and_source_team(self):
        result = resolve_canonical_team(
            registry=signed(), trusted_kms_clients={KEY_ARN: KMS},
            provider="provider-a", competition_id="league-1",
            source_team_id="source-team-1", as_of="2026-06-01T00:00:00Z",
        )
        self.assertEqual(result["canonical_team_id"], "canonical-team-1")
        self.assertEqual(result["team_scope"], "men_first_team")
        self.assertEqual(result["reviewer"], "team-identity-review")

    def test_provider_and_competition_are_part_of_identity(self):
        value = signed()
        for provider, competition in (("provider-b", "league-1"), ("provider-a", "league-2")):
            with self.assertRaisesRegex(TeamCrosswalkError, "mapping_missing_or_inactive"):
                resolve_canonical_team(
                    registry=value, trusted_kms_clients={KEY_ARN: KMS},
                    provider=provider, competition_id=competition,
                    source_team_id="source-team-1", as_of="2026-06-01T00:00:00Z",
                )

    def test_duplicate_provider_competition_source_id_is_rejected(self):
        value = registry([mapping("source-team-1", "canonical-a"),
                          mapping("source-team-1", "canonical-b")])
        with self.assertRaisesRegex(TeamCrosswalkError, "duplicate_source_mapping"):
            signed(value)

    def test_canonical_id_cannot_cross_gender_or_team_scope(self):
        value = registry([
            mapping("men-source", "same-canonical", "men_first_team"),
            mapping("women-source", "same-canonical", "women_first_team"),
        ])
        with self.assertRaisesRegex(TeamCrosswalkError, "canonical_scope_collision"):
            signed(value)

    def test_unsupported_scope_is_rejected(self):
        value = registry([mapping("source-team-1", "canonical-team-1", "senior")])
        with self.assertRaisesRegex(TeamCrosswalkError, "scope_invalid"):
            signed(value)

    def test_tampered_mapping_is_rejected_by_signature(self):
        value = signed()
        value["mappings"][0]["canonical_team_id"] = "changed"
        with self.assertRaisesRegex(TeamCrosswalkError, "signature_invalid"):
            verify_team_crosswalk_registry(
                registry=value, trusted_kms_clients={KEY_ARN: KMS},
                as_of="2026-06-01T00:00:00Z",
            )

    def test_untrusted_signing_key_is_rejected(self):
        with self.assertRaisesRegex(TeamCrosswalkError, "signing_key_not_trusted"):
            verify_team_crosswalk_registry(
                registry=signed(), trusted_kms_clients={},
                as_of="2026-06-01T00:00:00Z",
            )

    def test_revoked_mapping_is_inactive(self):
        value = registry()
        value["mappings"][0]["revoked_at"] = "2026-05-01T00:00:00Z"
        with self.assertRaisesRegex(TeamCrosswalkError, "mapping_missing_or_inactive"):
            resolve_canonical_team(
                registry=signed(value), trusted_kms_clients={KEY_ARN: KMS},
                provider="provider-a", competition_id="league-1",
                source_team_id="source-team-1", as_of="2026-06-01T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
