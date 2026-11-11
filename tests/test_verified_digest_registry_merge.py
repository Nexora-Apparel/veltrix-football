import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from app.evidence_receipt_signing import SCHEMA_V2, sign_receipt, verify_receipt_signature
from scripts.merge_verified_source_digest_registries import (
    RegistryMergeError, merge_registries,
)


KEY_A = "arn:aws:kms:us-east-1:123456789012:key/key-a"
KEY_B = "arn:aws:kms:us-east-1:123456789012:key/key-b"


class FakeKMS:
    def __init__(self, key_arn):
        self.key_arn = key_arn

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        if KeyId != self.key_arn:
            raise AssertionError("wrong signing key")
        return {"Signature": hashlib.sha256(KeyId.encode() + Message).digest()}

    def verify(self, KeyId, Message, MessageType, Signature, SigningAlgorithm):
        expected = hashlib.sha256(KeyId.encode() + Message).digest()
        return {"SignatureValid": (
            KeyId == self.key_arn and MessageType == "DIGEST"
            and SigningAlgorithm == "ECDSA_SHA_256" and Signature == expected
        )}


def source_registry(key, run_id, digest, receipt_sha):
    unsigned = {
        "schema": SCHEMA_V2,
        "schema_version": 1,
        "verified_source_evidence_sha256": [digest],
        "verified_archive_receipts": [{
            "archive_receipt_signature_verified": True,
            "receipt_sha256": receipt_sha,
            "receipt_signing_key_arn": key,
            "run_id": run_id,
        }],
    }
    return sign_receipt(kms_client=FakeKMS(key), key_arn=key, receipt=unsigned)


class VerifiedDigestRegistryMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.first = self.root / "first.json"
        self.second = self.root / "second.json"
        self.output = self.root / "merged.json"
        self.clients = {KEY_A: FakeKMS(KEY_A), KEY_B: FakeKMS(KEY_B)}
        self.first.write_text(json.dumps(source_registry(
            KEY_A, "run-a", "a" * 64, "1" * 64,
        )))
        self.second.write_text(json.dumps(source_registry(
            KEY_B, "run-b", "b" * 64, "2" * 64,
        )))

    def tearDown(self):
        self.temp.cleanup()

    def test_merges_verified_registries_and_signs_aggregate(self):
        result = merge_registries(
            input_paths=[str(self.first), str(self.second)],
            output_path=str(self.output), trusted_kms_clients=self.clients,
            signing_key_arn=KEY_A,
        )
        merged = json.loads(self.output.read_text())
        self.assertEqual(result["verified_source_digest_count"], 2)
        self.assertEqual(result["verified_archive_receipt_count"], 2)
        self.assertEqual(merged["verified_source_evidence_sha256"], ["a" * 64, "b" * 64])
        self.assertEqual(len(merged["verified_archive_receipts"]), 2)
        verify_receipt_signature(
            kms_client=self.clients[KEY_A], trusted_key_arn=KEY_A, receipt=merged,
        )

    def test_rejects_tampered_source_registry_before_output(self):
        source = json.loads(self.first.read_text())
        source["verified_source_evidence_sha256"].append("c" * 64)
        self.first.write_text(json.dumps(source))
        with self.assertRaisesRegex(RegistryMergeError, "signature_or_trust_invalid"):
            merge_registries(
                input_paths=[str(self.first), str(self.second)],
                output_path=str(self.output), trusted_kms_clients=self.clients,
                signing_key_arn=KEY_A,
            )
        self.assertFalse(self.output.exists())

    def test_rejects_signing_key_outside_allowlist(self):
        with self.assertRaisesRegex(RegistryMergeError, "signing_key_not_trusted"):
            merge_registries(
                input_paths=[str(self.first)], output_path=str(self.output),
                trusted_kms_clients=self.clients, signing_key_arn="arn:aws:kms:us-east-1:123456789012:key/unknown",
            )

    def test_duplicate_registry_inputs_are_idempotent(self):
        result = merge_registries(
            input_paths=[str(self.first), str(self.first)],
            output_path=str(self.output), trusted_kms_clients=self.clients,
            signing_key_arn=KEY_A,
        )
        self.assertEqual(result["verified_source_digest_count"], 1)
        self.assertEqual(result["verified_archive_receipt_count"], 1)


if __name__ == "__main__":
    unittest.main()
