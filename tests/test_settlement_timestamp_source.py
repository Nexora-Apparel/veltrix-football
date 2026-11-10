import unittest

from app.settlement_timestamp_source import (
    SettlementTimestampSourceError, build_settlement_timestamp_evidence,
    validate_settlement_timestamp_evidence, reconcile_settlement_timestamp_evidence,
    canonical_sha256,
)


CONTRACT = {
    "source_id": "qualified-source-a",
    "qualification_status": "qualified",
    "qualification_digest": "a" * 64,
    "timestamp_field": "match.full_time_whistle_at",
    "timestamp_semantics": "final_whistle",
    "supported_competitions": ["england-premier-league"],
}
IDENTITY = {
    "source_fixture_id": "source-match-1",
    "competition_id": "england-premier-league",
    "home_team_id": "team-home",
    "away_team_id": "team-away",
    "kickoff_at": "2026-10-01T15:00:00Z",
}
PAYLOAD = {"match": {"full_time_whistle_at": "2026-10-01T16:52:13Z"}}


class SettlementTimestampSourceTests(unittest.TestCase):
    def build(self, **overrides):
        args = {
            "source_contract": CONTRACT, "raw_payload": PAYLOAD,
            "fixture_identity": IDENTITY, "expected_fixture_identity": IDENTITY,
            "kickoff_at": IDENTITY["kickoff_at"],
            "observed_at": "2026-10-01T16:52:14Z",
            "retrieved_at": "2026-10-01T16:53:00Z",
        }
        args.update(overrides)
        return build_settlement_timestamp_evidence(**args)

    def test_qualified_source_produces_bound_timestamp(self):
        evidence = self.build()
        self.assertEqual(evidence["settlement_at"], "2026-10-01T16:52:13Z")
        result = validate_settlement_timestamp_evidence(
            evidence, source_contract=CONTRACT, raw_payload=PAYLOAD,
            fixture_identity=IDENTITY, expected_fixture_identity=IDENTITY,
            kickoff_at=IDENTITY["kickoff_at"],
        )
        self.assertTrue(result["valid"])

    def test_unqualified_source_is_rejected(self):
        contract = {**CONTRACT, "qualification_status": "candidate"}
        with self.assertRaisesRegex(SettlementTimestampSourceError, "timestamp_source_not_qualified"):
            self.build(source_contract=contract)

    def test_unverified_or_unsupported_semantics_rejected(self):
        contract = {**CONTRACT, "timestamp_semantics": "provider_updated_at"}
        with self.assertRaisesRegex(SettlementTimestampSourceError, "timestamp_semantics_unsupported"):
            self.build(source_contract=contract)

    def test_fixture_identity_mismatch_rejected(self):
        other = {**IDENTITY, "home_team_id": "wrong-team"}
        with self.assertRaisesRegex(SettlementTimestampSourceError, "fixture_identity_mismatch"):
            self.build(fixture_identity=other)

    def test_competition_scope_is_enforced(self):
        other = {**IDENTITY, "competition_id": "unqualified-league"}
        with self.assertRaisesRegex(SettlementTimestampSourceError, "fixture_identity_mismatch"):
            self.build(fixture_identity=other, expected_fixture_identity=other)

    def test_naive_timestamp_rejected(self):
        payload = {"match": {"full_time_whistle_at": "2026-10-01T16:52:13"}}
        with self.assertRaisesRegex(SettlementTimestampSourceError, "settlement_at_timezone_missing"):
            self.build(raw_payload=payload)

    def test_retrieval_and_observation_order_enforced(self):
        with self.assertRaisesRegex(SettlementTimestampSourceError, "retrieval_precedes_observation"):
            self.build(retrieved_at="2026-10-01T16:52:13Z")
        with self.assertRaisesRegex(SettlementTimestampSourceError, "observation_precedes_settlement"):
            self.build(observed_at="2026-10-01T16:52:12Z")

    def test_timestamp_before_kickoff_rejected(self):
        payload = {"match": {"full_time_whistle_at": "2026-10-01T14:59:00Z"}}
        with self.assertRaisesRegex(SettlementTimestampSourceError, "settlement_precedes_kickoff"):
            self.build(raw_payload=payload)

    def test_raw_payload_tampering_rejected(self):
        evidence = self.build()
        altered = {"match": {"full_time_whistle_at": "2026-10-01T16:50:00Z"}}
        with self.assertRaisesRegex(SettlementTimestampSourceError, "timestamp_raw_payload_binding_mismatch"):
            validate_settlement_timestamp_evidence(
                evidence, source_contract=CONTRACT, raw_payload=altered,
                fixture_identity=IDENTITY, expected_fixture_identity=IDENTITY,
                kickoff_at=IDENTITY["kickoff_at"],
            )

    def test_evidence_tampering_rejected(self):
        evidence = self.build()
        evidence["settlement_at"] = "2026-10-01T16:50:00Z"
        with self.assertRaisesRegex(SettlementTimestampSourceError, "timestamp_evidence_digest_or_binding_mismatch"):
            validate_settlement_timestamp_evidence(
                evidence, source_contract=CONTRACT, raw_payload=PAYLOAD,
                fixture_identity=IDENTITY, expected_fixture_identity=IDENTITY,
                kickoff_at=IDENTITY["kickoff_at"],
            )

    def test_conflicting_sources_rejected(self):
        one = self.build()
        two_contract = {**CONTRACT, "source_id": "qualified-source-b", "qualification_digest": "b" * 64}
        two = self.build(source_contract=two_contract,
                         raw_payload={"match": {"full_time_whistle_at": "2026-10-01T16:55:00Z"}},
                         observed_at="2026-10-01T16:55:01Z",
                         retrieved_at="2026-10-01T16:56:00Z")
        with self.assertRaisesRegex(SettlementTimestampSourceError, "settlement_timestamp_conflict"):
            reconcile_settlement_timestamp_evidence([one, two], maximum_difference_seconds=60)

    def test_duplicate_sources_rejected(self):
        evidence = self.build()
        with self.assertRaisesRegex(SettlementTimestampSourceError, "timestamp_sources_duplicate_or_invalid"):
            reconcile_settlement_timestamp_evidence([evidence, evidence])

    def test_digest_is_deterministic(self):
        self.assertEqual(canonical_sha256({"b": 2, "a": 1}), canonical_sha256({"a": 1, "b": 2}))


if __name__ == "__main__":
    unittest.main()
