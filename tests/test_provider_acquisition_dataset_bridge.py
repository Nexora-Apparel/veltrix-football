import unittest

from app.provider_fixture_normalizer import normalize_striker_game
from app.provider_source_evidence import build_source_evidence
from app.settlement_timestamp_source import build_settlement_timestamp_evidence
from app.source_qualification_registry import (
    SCHEMA, canonical_sha256, sign_source_qualification_registry,
)
from app.provider_acquisition_dataset_bridge import (
    AcquisitionDatasetBridgeError, acquisition_record_to_history_row,
)
from app.canonical_team_crosswalk import (
    SCHEMA as TEAM_CROSSWALK_SCHEMA, sign_team_crosswalk_registry,
)
from app.results_feature_reconstruction import reconstruct_pre_match_features


KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/veltrix-test-key"


class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


KMS = FakeKms()


def signed_team_crosswalk_registry(*, home_scope="men_first_team",
                                   away_scope="men_first_team",
                                   same_canonical=False,
                                   valid_until="2027-01-01T00:00:00Z",
                                   revoked_at=None):
    mappings = []
    for source_id, canonical_id, scope in (
        ("h", "canonical-home", home_scope),
        ("a", "canonical-home" if same_canonical else "canonical-away", away_scope),
    ):
        mappings.append({
            "provider": "strikerapi", "competition_id": "soccer",
            "source_team_id": source_id, "canonical_team_id": canonical_id,
            "team_scope": scope, "evidence_sha256": ["b" * 64],
            "reviewer": "identity-review", "reviewed_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-02T00:00:00Z",
            "valid_until": valid_until, "revoked_at": revoked_at,
        })
    return sign_team_crosswalk_registry(
        kms_client=KMS, key_arn=KEY_ARN,
        trusted_key_regions={KEY_ARN: "eu-west-1"},
        registry={
            "schema": TEAM_CROSSWALK_SCHEMA,
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "mappings": mappings,
        },
    )


QUALIFICATION_RECORD = {
    "source_id": "qualified-source-a",
    "qualification_status": "qualified",
    "timestamp_field": "match.full_time_whistle_at",
    "timestamp_semantics": "final_whistle",
    "supported_competitions": ["soccer"],
    "qualification_evidence_sha256": ["a" * 64],
    "qualified_at": "2026-10-01T10:00:00Z",
}
CONTRACT = {
    "source_id": "qualified-source-a",
    "qualification_status": "qualified",
    "qualification_digest": canonical_sha256(QUALIFICATION_RECORD),
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
        registry = {
            "schema": SCHEMA,
            "issued_at": "2026-10-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "sources": [{
                "qualification_record": QUALIFICATION_RECORD,
                "qualification_record_sha256": canonical_sha256(QUALIFICATION_RECORD),
                "valid_from": "2026-10-01T10:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
                "revoked_at": None,
            }],
        }
        signed_registry = sign_source_qualification_registry(
            kms_client=KMS, key_arn=KEY_ARN,
            trusted_key_regions={KEY_ARN: "eu-west-1"}, registry=registry,
        )
        return {
            "source_contract": CONTRACT,
            "qualification_registry": signed_registry,
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

    def test_signed_qualified_external_final_whistle_evidence_is_joined(self):
        row = acquisition_record_to_history_row(
            self.provider_record(),
            settlement_timestamp_package=self.settlement_package(),
            trusted_kms_clients={KEY_ARN: KMS},
            team_crosswalk_registry=signed_team_crosswalk_registry(),
        )
        self.assertEqual(row["settled_at"], "2026-11-01T16:52:13Z")
        self.assertEqual(row["settlement_source_id"], "qualified-source-a")
        self.assertEqual(row["settlement_qualification_digest"], CONTRACT["qualification_digest"])
        self.assertEqual(len(row["settlement_evidence_sha256"]), 64)
        self.assertEqual(len(row["settlement_registry_sha256"]), 64)
        self.assertEqual(row["settlement_registry_signing_key_arn"], KEY_ARN)
        self.assertEqual(row["home_team_id"], "canonical-home")
        self.assertEqual(row["away_team_id"], "canonical-away")
        self.assertEqual(row["home_team_source_id"], "h")
        self.assertEqual(row["away_team_source_id"], "a")
        self.assertEqual(row["team_identity_evidence"]["signing_key_arn"], KEY_ARN)
        self.assertEqual(row["team_identity_evidence"]["team_scope"], "men_first_team")
        self.assertEqual(row["source_payload"]["payload"]["home"]["team_id"], "h")
        self.assertEqual(
            row["source_payload"]["normalized_record"]["home_team_id"], "h"
        )

    def test_expired_team_mapping_is_rejected(self):
        with self.assertRaisesRegex(
            AcquisitionDatasetBridgeError, "canonical_team_pair_rejected:team_pair_mapping_missing_or_inactive"
        ):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=self.settlement_package(),
                trusted_kms_clients={KEY_ARN: KMS},
                team_crosswalk_registry=signed_team_crosswalk_registry(
                    valid_until="2026-11-01T00:00:00Z"
                ),
            )

    def test_revoked_team_mapping_is_rejected(self):
        with self.assertRaisesRegex(
            AcquisitionDatasetBridgeError, "canonical_team_pair_rejected:team_pair_mapping_missing_or_inactive"
        ):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=self.settlement_package(),
                trusted_kms_clients={KEY_ARN: KMS},
                team_crosswalk_registry=signed_team_crosswalk_registry(
                    revoked_at="2026-11-01T00:00:00Z"
                ),
            )

    def test_two_source_ids_cannot_resolve_to_same_canonical_team(self):
        with self.assertRaisesRegex(
            AcquisitionDatasetBridgeError, "team_pair_resolves_to_same_canonical_team"
        ):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=self.settlement_package(),
                trusted_kms_clients={KEY_ARN: KMS},
                team_crosswalk_registry=signed_team_crosswalk_registry(same_canonical=True),
            )

    def test_men_women_reserve_and_youth_scopes_cannot_be_conflated(self):
        for incompatible_scope in (
            "women_first_team", "men_reserve", "women_reserve", "youth_men", "youth_women",
        ):
            with self.subTest(scope=incompatible_scope):
                with self.assertRaisesRegex(
                    AcquisitionDatasetBridgeError, "team_pair_scope_mismatch"
                ):
                    acquisition_record_to_history_row(
                        self.provider_record(), settlement_timestamp_package=self.settlement_package(),
                        trusted_kms_clients={KEY_ARN: KMS},
                        team_crosswalk_registry=signed_team_crosswalk_registry(
                            away_scope=incompatible_scope
                        ),
                    )

    def test_canonical_ids_drive_team_history_joins(self):
        row = acquisition_record_to_history_row(
            self.provider_record(), settlement_timestamp_package=self.settlement_package(),
            trusted_kms_clients={KEY_ARN: KMS},
            team_crosswalk_registry=signed_team_crosswalk_registry(),
        )
        feature_fields = {
            "fixture_id", "provider", "source_id", "competition_id", "kickoff_at",
            "settled_at", "home_team_id", "away_team_id", "home_score", "away_score",
            "endpoint", "retrieved_at", "payload_sha256", "run_id", "normalized_status",
            "source_payload", "home_team_source_id", "away_team_source_id",
            "team_identity_evidence",
        }
        history_row = {key: value for key, value in row.items() if key in feature_fields}
        features = reconstruct_pre_match_features(
            historical_matches=[history_row],
            target_fixture={
                "fixture_id": "target-after-canonicalization",
                "competition_id": "soccer",
                "kickoff_at": "2026-11-03T15:00:00Z",
                "home_team_id": "canonical-home",
                "away_team_id": "canonical-away",
            },
            cutoff_hours=6, minimum_team_matches=1,
        )["features"]
        self.assertEqual(features["home_attack_goals_rate"], 2.0)
        self.assertEqual(features["away_attack_goals_rate"], 1.0)

    def test_external_timestamp_evidence_tampering_is_rejected(self):
        package = self.settlement_package()
        package["evidence"]["settlement_at"] = "2026-11-01T16:50:00Z"
        with self.assertRaisesRegex(AcquisitionDatasetBridgeError, "qualified_settlement_rejected"):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=package,
                trusted_kms_clients={KEY_ARN: KMS},
            )

    def test_untrusted_registry_signer_is_rejected(self):
        package = self.settlement_package()
        with self.assertRaisesRegex(AcquisitionDatasetBridgeError, "trusted_settlement_registry_keys_required"):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=package,
                trusted_kms_clients={},
            )

    def test_contract_not_bound_to_signed_registry_is_rejected(self):
        package = self.settlement_package()
        package["source_contract"] = {**CONTRACT, "timestamp_field": "match.updated_at"}
        with self.assertRaisesRegex(AcquisitionDatasetBridgeError, "settlement_source_contract_not_registry_bound"):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=package,
                trusted_kms_clients={KEY_ARN: KMS},
            )

    def test_settlement_fixture_mapping_must_match_provider_record(self):
        package = self.settlement_package()
        package["expected_fixture_identity"] = {
            **IDENTITY, "home_team_id": "different-home-team",
        }
        package["fixture_identity"] = package["expected_fixture_identity"]
        package["evidence"] = build_settlement_timestamp_evidence(
            source_contract=CONTRACT, raw_payload=TIMESTAMP_PAYLOAD,
            fixture_identity=package["fixture_identity"],
            expected_fixture_identity=package["expected_fixture_identity"],
            kickoff_at=IDENTITY["kickoff_at"],
            observed_at="2026-11-01T16:52:14Z",
            retrieved_at="2026-11-01T16:53:00Z",
        )
        with self.assertRaisesRegex(
            AcquisitionDatasetBridgeError,
            "settlement_fixture_mapping_not_bound_to_provider_record",
        ):
            acquisition_record_to_history_row(
                self.provider_record(), settlement_timestamp_package=package,
                trusted_kms_clients={KEY_ARN: KMS},
            )

    def test_unbound_raw_payload_cannot_enter_training_history(self):
        record = self.provider_record()
        record["source_evidence"]["raw_payload"]["home"]["score"] = 9
        with self.assertRaises(AcquisitionDatasetBridgeError):
            acquisition_record_to_history_row(
                record, settlement_timestamp_package=self.settlement_package(),
                trusted_kms_clients={KEY_ARN: KMS},
            )

    def test_provider_retrieval_before_external_settlement_is_rejected(self):
        record = self.provider_record(retrieved_at="2026-11-01T16:00:00Z")
        with self.assertRaises(AcquisitionDatasetBridgeError):
            acquisition_record_to_history_row(
                record, settlement_timestamp_package=self.settlement_package(),
                trusted_kms_clients={KEY_ARN: KMS},
            )


if __name__ == "__main__":
    unittest.main()
