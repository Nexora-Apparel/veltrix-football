import hashlib
import json
import unittest

from app.provider_fixture_normalizer import normalize_striker_game
from app.provider_source_evidence import build_source_evidence
from app.settlement_timestamp_source import build_settlement_timestamp_evidence
from app.source_qualification_registry import (
    SCHEMA, canonical_sha256, sign_source_qualification_registry,
)
from app.provider_acquisition_eligibility_audit import (
    SCHEMA_VERSION, audit_provider_acquisition_eligibility,
)


KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/veltrix-test-key"


class FakeKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}

    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}


KMS = FakeKms()
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


class ProviderAcquisitionEligibilityAuditTests(unittest.TestCase):
    def provider_record(self, game_id="g-1"):
        payload = {
            "game_id": game_id, "starts_at": "2026-11-01T15:00:00Z",
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

    def audit(self, records, packages=None, trusted=None):
        return audit_provider_acquisition_eligibility(
            acquisition_records=records,
            settlement_timestamp_packages=packages or {},
            trusted_kms_clients=trusted if trusted is not None else {KEY_ARN: KMS},
        )

    def test_valid_record_is_admitted_with_sanitized_provenance(self):
        report = self.audit(
            [self.provider_record()],
            {"strikerapi:g-1": self.settlement_package()},
        )
        self.assertEqual(report["schema_version"], SCHEMA_VERSION)
        self.assertEqual(report["settlement_eligible_count"], 1)
        self.assertEqual(report["rejected_count"], 0)
        accepted = report["accepted_records"][0]
        self.assertEqual(accepted["fixture_id"], "strikerapi:g-1")
        self.assertEqual(accepted["settlement_source_id"], "qualified-source-a")
        self.assertEqual(len(accepted["payload_sha256"]), 64)
        self.assertNotIn("raw_payload", json.dumps(report))

    def test_missing_settlement_package_is_reported_without_aborting_batch(self):
        report = self.audit(
            [self.provider_record(), self.provider_record("g-2")],
            {"strikerapi:g-1": self.settlement_package()},
        )
        self.assertEqual(report["settlement_eligible_count"], 1)
        self.assertEqual(report["rejected_count"], 1)
        self.assertEqual(
            report["rejected_records"][0]["reason"],
            "settlement_timestamp_unavailable",
        )

    def test_untrusted_registry_key_is_reported_as_rejection(self):
        report = self.audit(
            [self.provider_record()],
            {"strikerapi:g-1": self.settlement_package()},
            trusted={},
        )
        self.assertEqual(report["settlement_eligible_count"], 0)
        self.assertEqual(
            report["rejected_records"][0]["reason"],
            "trusted_settlement_registry_keys_required",
        )

    def test_all_duplicate_provider_source_identities_are_rejected(self):
        report = self.audit(
            [self.provider_record(), self.provider_record()],
            {"strikerapi:g-1": self.settlement_package()},
        )
        self.assertEqual(report["settlement_eligible_count"], 0)
        self.assertEqual(report["rejected_count"], 2)
        self.assertEqual(
            report["rejected_by_reason"]["duplicate_provider_source_identity"], 2,
        )

    def test_malformed_record_is_quarantined_without_stopping_batch(self):
        report = self.audit(
            [None, self.provider_record()],
            {"strikerapi:g-1": self.settlement_package()},
        )
        self.assertEqual(report["settlement_eligible_count"], 1)
        self.assertEqual(report["rejected_records"][0]["fixture_id"], "record-index-0")
        self.assertEqual(
            report["rejected_records"][0]["reason"],
            "acquisition_record_identity_invalid",
        )

    def test_unmatched_settlement_package_is_reported(self):
        report = self.audit(
            [self.provider_record()],
            {
                "strikerapi:g-1": self.settlement_package(),
                "strikerapi:orphan": self.settlement_package(),
            },
        )
        self.assertEqual(
            report["unmatched_settlement_package_ids"],
            ["strikerapi:orphan"],
        )

    def test_report_digest_is_deterministic_and_binds_decisions(self):
        records = [self.provider_record(), self.provider_record("g-2")]
        packages = {"strikerapi:g-1": self.settlement_package()}
        one = self.audit(records, packages)
        two = self.audit(records, packages)
        self.assertEqual(one, two)
        unsigned = dict(one)
        digest = unsigned.pop("report_sha256")
        raw = json.dumps(
            unsigned, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_audit_never_starts_training_or_writes_or_publishes(self):
        report = self.audit([self.provider_record()])
        self.assertFalse(report["model_training_started"])
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["prediction_publications"], 0)
        self.assertFalse(report["value_betting_enabled"])


if __name__ == "__main__":
    unittest.main()
