import hashlib
import json
import unittest

from app.evidence_receipt_signing import sign_receipt
from app.evidence_receipt_trust import (
    ReceiptTrustError, parse_trusted_key_regions,
    validate_current_signing_key, verify_receipt_with_trusted_clients,
)

OLD_KEY = "arn:aws:kms:us-east-1:123456789012:key/old-receipt-key"
NEW_KEY = "arn:aws:kms:eu-west-1:123456789012:key/new-receipt-key"


class FakeKMS:
    def __init__(self, allowed_key):
        self.allowed_key = allowed_key
        self.verify_calls = 0

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        if KeyId != self.allowed_key:
            raise AssertionError("wrong KMS key")
        return {"Signature": hashlib.sha256(KeyId.encode() + Message).digest()}

    def verify(self, KeyId, Message, MessageType, Signature, SigningAlgorithm):
        self.verify_calls += 1
        if KeyId != self.allowed_key:
            raise AssertionError("wrong KMS key")
        return {"SignatureValid": Signature == hashlib.sha256(KeyId.encode() + Message).digest()}


class EvidenceReceiptTrustTests(unittest.TestCase):
    def test_parses_explicit_multi_key_registry(self):
        registry = parse_trusted_key_regions(
            registry_json=json.dumps({OLD_KEY: "us-east-1", NEW_KEY: "eu-west-1"})
        )
        self.assertEqual(registry, {OLD_KEY: "us-east-1", NEW_KEY: "eu-west-1"})

    def test_supports_legacy_single_key_configuration(self):
        registry = parse_trusted_key_regions(
            registry_json=None, legacy_key_arn=OLD_KEY, legacy_region="us-east-1",
        )
        self.assertEqual(registry, {OLD_KEY: "us-east-1"})

    def test_rejects_unknown_or_malformed_key_arn(self):
        with self.assertRaisesRegex(ReceiptTrustError, "key_arn_invalid"):
            parse_trusted_key_regions(
                registry_json=json.dumps({"arn:aws:kms:us-east-1:bad:key/nope": "us-east-1"})
            )

    def test_rejects_region_mismatch(self):
        with self.assertRaisesRegex(ReceiptTrustError, "region_mismatch"):
            parse_trusted_key_regions(
                registry_json=json.dumps({OLD_KEY: "eu-west-1"})
            )

    def test_current_signer_must_be_explicitly_allowlisted(self):
        with self.assertRaisesRegex(ReceiptTrustError, "not_in_trust_registry"):
            validate_current_signing_key(
                signing_key_arn=NEW_KEY, signing_region="eu-west-1",
                trusted_key_regions={OLD_KEY: "us-east-1"},
            )

    def test_current_signer_region_must_match_arn_and_registry(self):
        with self.assertRaisesRegex(ReceiptTrustError, "region_mismatch"):
            validate_current_signing_key(
                signing_key_arn=OLD_KEY, signing_region="eu-west-1",
                trusted_key_regions={OLD_KEY: "us-east-1"},
            )

    def test_old_receipt_verifies_using_only_allowlisted_old_key(self):
        old_kms = FakeKMS(OLD_KEY)
        receipt = {
            "schema": "veltrix-evidence-archive-receipt-v2",
            "provider": "fivedollar",
            "run_id": "batch-20261110T060000Z",
            "receipt_key": "private/receipts/batch-20261110T060000Z.json",
            "report_sha256": "a" * 64,
            "objects": [],
        }
        signed = sign_receipt(kms_client=old_kms, key_arn=OLD_KEY, receipt=receipt)
        selected = verify_receipt_with_trusted_clients(
            receipt=signed,
            trusted_kms_clients={OLD_KEY: old_kms, NEW_KEY: FakeKMS(NEW_KEY)},
        )
        self.assertEqual(selected, OLD_KEY)
        self.assertEqual(old_kms.verify_calls, 1)

    def test_unknown_receipt_key_is_rejected_before_any_kms_call(self):
        old_kms = FakeKMS(OLD_KEY)
        receipt = {
            "schema": "veltrix-evidence-archive-receipt-v2",
            "signature": {
                "algorithm": "ECDSA_SHA_256",
                "message_type": "DIGEST",
                "key_arn": NEW_KEY,
                "value_base64": "ZmFrZQ==",
            },
        }
        with self.assertRaisesRegex(ReceiptTrustError, "not_trusted"):
            verify_receipt_with_trusted_clients(
                receipt=receipt, trusted_kms_clients={OLD_KEY: old_kms},
            )
        self.assertEqual(old_kms.verify_calls, 0)


if __name__ == "__main__":
    unittest.main()
