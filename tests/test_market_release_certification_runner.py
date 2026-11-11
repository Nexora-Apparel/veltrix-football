import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app.bookmaker_odds_evidence import (
    append_odds_observations, build_odds_observation,
)
from app.evidence_receipt_signing import sign_receipt
from scripts.evaluate_market_release_certification import (
    CertificationRunnerError, evaluate,
)


MARKETS = {
    "1x2": (("home", "draw", "away"), {"home": 0.5, "draw": 0.3, "away": 0.2}, "home",
            {"home": 2.0, "draw": 3.0, "away": 4.0}),
    "btts": (("no", "yes"), {"no": 0.4, "yes": 0.6}, "yes",
            {"no": 2.0, "yes": 2.0}),
    "over_2_5": (("no", "yes"), {"no": 0.45, "yes": 0.55}, "yes",
                 {"no": 2.0, "yes": 2.0}),
}


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()


TEST_KEY_ARN = "arn:aws:kms:us-east-1:123456789012:key/test-key"


class FakeKMS:
    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        return {"Signature": hashlib.sha256(KeyId.encode() + Message).digest()}

    def verify(self, KeyId, Message, MessageType, Signature, SigningAlgorithm):
        expected = hashlib.sha256(KeyId.encode() + Message).digest()
        return {"SignatureValid": (
            KeyId == TEST_KEY_ARN and MessageType == "DIGEST"
            and SigningAlgorithm == "ECDSA_SHA_256" and Signature == expected
        )}


class MarketReleaseCertificationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.walk_path = self.root / "walk.json"
        self.odds_path = self.root / "odds.json"
        self.prospective_path = self.root / "prospective.json"
        self.verified_path = self.root / "verified.json"
        self.output_path = self.root / "certification.json"
        records = [{
            "origin_id": "origin-1",
            "fixture_id": "fixture-1",
            "kickoff_at": "2026-11-10T12:00:00Z",
            "label_available_at": "2026-11-10T15:00:00Z",
            "label_source_evidence_sha256": "a" * 64,
            "feature_snapshot_sha256": "f" * 64,
            "probabilities": {market: values[1] for market, values in MARKETS.items()},
            "targets": {market: values[2] for market, values in MARKETS.items()},
        }]
        binding = [{
            "origin_id": row["origin_id"],
            "fixture_id": row["fixture_id"],
            "probabilities": row["probabilities"],
            "targets": row["targets"],
        } for row in records]
        self.walk_path.write_text(json.dumps({
            "evaluation_type": "multi_origin_chronological_walk_forward",
            "test_records_sha256": digest(binding),
            "pooled_test_records": records,
        }))
        observations = []
        for market, (_, _, _, prices) in MARKETS.items():
            observations.append(build_odds_observation(
                provider="the_odds_api", provider_event_id="event-1",
                fixture_id="fixture-1", market=market, bookmaker="book-a",
                captured_at="2026-11-10T10:00:00Z",
                kickoff_at="2026-11-10T12:00:00Z",
                decimal_odds=prices, raw_payload={"event": "event-1", "market": market},
                source_payload_sha256="b" * 64,
                crosswalk_evidence_sha256="c" * 64,
            ))
        odds = append_odds_observations(
            {"schema_version": 1, "observations": []}, observations,
        )["ledger"]
        self.odds_path.write_text(json.dumps(odds))
        self.prospective_path.write_text(json.dumps({
            "schema_version": 1, "selections": [], "settlements": [],
        }))
        registry = {
            "schema": "veltrix-evidence-archive-receipt-v2",
            "schema_version": 1,
            "verified_source_evidence_sha256": ["a" * 64, "b" * 64, "c" * 64],
            "verified_archive_receipts": [
                {
                    "archive_receipt_signature_verified": True,
                    "receipt_sha256": "d" * 64,
                    "receipt_signing_key_arn": TEST_KEY_ARN,
                    "run_id": "restore-run-1",
                },
                {
                    "archive_receipt_signature_verified": True,
                    "receipt_sha256": "e" * 64,
                    "receipt_signing_key_arn": "arn:aws:kms:us-west-2:123456789012:key/retired-key",
                    "run_id": "restore-run-legacy",
                },
            ],
        }
        registry = sign_receipt(
            kms_client=FakeKMS(), key_arn=TEST_KEY_ARN, receipt=registry,
        )
        self.verified_path.write_text(json.dumps(registry))

    def tearDown(self):
        self.temp.cleanup()

    def run_evaluation(self):
        return evaluate(
            walk_forward_path=str(self.walk_path),
            odds_ledger_path=str(self.odds_path),
            prospective_ledger_path=str(self.prospective_path),
            verified_digests_path=str(self.verified_path),
            benchmark_bookmaker="book-a",
            evaluated_at="2026-11-11T00:00:00Z",
            output_path=str(self.output_path),
            trusted_kms_clients={TEST_KEY_ARN: FakeKMS()},
        )

    def test_runs_full_offline_evidence_chain_and_keeps_authorization_locked(self):
        report = self.run_evaluation()
        self.assertTrue(self.output_path.is_file())
        self.assertEqual(report["verified_source_evidence_digest_count"], 3)
        for market in MARKETS:
            self.assertTrue(
                report["markets"][market]["checks"]["source_evidence_receipts_verified"]
            )
        self.assertFalse(report["all_markets_certified"])
        self.assertFalse(report["value_betting_authorized"])
        self.assertFalse(report["publication_authorized"])
        self.assertEqual(report["side_effects"]["provider_requests"], 0)
        saved = json.loads(self.output_path.read_text())
        self.assertEqual(saved["input_bindings"]["benchmark_bookmaker"], "book-a")

    def test_unverified_crosswalk_digest_fails_provenance_gate(self):
        registry = json.loads(self.verified_path.read_text())
        registry.pop("signature", None)
        registry["verified_source_evidence_sha256"].remove("c" * 64)
        registry = sign_receipt(
            kms_client=FakeKMS(), key_arn=TEST_KEY_ARN, receipt=registry,
        )
        self.verified_path.write_text(json.dumps(registry))
        report = self.run_evaluation()
        self.assertTrue(all(
            not report["markets"][market]["checks"]["source_evidence_receipts_verified"]
            for market in MARKETS
        ))

    def test_rejects_tampered_digest_registry_signature(self):
        registry = json.loads(self.verified_path.read_text())
        registry["verified_source_evidence_sha256"].remove("c" * 64)
        self.verified_path.write_text(json.dumps(registry))
        with self.assertRaisesRegex(CertificationRunnerError, "signature_invalid"):
            self.run_evaluation()

    def test_rejects_registry_without_verified_archive_receipt(self):
        registry = json.loads(self.verified_path.read_text())
        registry["verified_archive_receipts"] = []
        registry = sign_receipt(
            kms_client=FakeKMS(), key_arn=TEST_KEY_ARN, receipt=registry,
        )
        self.verified_path.write_text(json.dumps(registry))
        with self.assertRaisesRegex(CertificationRunnerError, "registry_content_invalid"):
            self.run_evaluation()


if __name__ == "__main__":
    unittest.main()
