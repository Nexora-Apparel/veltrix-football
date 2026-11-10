import hashlib
import unittest

from app.evidence_receipt_signing import (
    ReceiptSignatureError, canonical_receipt_payload, sign_receipt,
    verify_receipt_signature,
)


KEY_ARN = "arn:aws:kms:us-east-1:123456789012:key/receipt-signing-key"


class FakeKMS:
    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        self.assert_contract(KeyId, MessageType, SigningAlgorithm)
        return {"Signature": hashlib.sha256(KeyId.encode() + Message).digest()}

    def verify(self, KeyId, Message, MessageType, Signature, SigningAlgorithm):
        self.assert_contract(KeyId, MessageType, SigningAlgorithm)
        return {"SignatureValid": Signature == hashlib.sha256(KeyId.encode() + Message).digest()}

    @staticmethod
    def assert_contract(key_id, message_type, algorithm):
        if key_id != KEY_ARN or message_type != "DIGEST" or algorithm != "ECDSA_SHA_256":
            raise AssertionError("unexpected KMS signing contract")


class ReceiptSigningTests(unittest.TestCase):
    def setUp(self):
        self.kms = FakeKMS()
        self.receipt = {
            "schema": "veltrix-evidence-archive-receipt-v2",
            "provider": "fivedollar",
            "run_id": "batch-20261110T060000Z",
            "receipt_key": "private/receipts/batch-20261110T060000Z.json",
            "report_sha256": "a" * 64,
            "objects": [{"kind": "report", "key": "private/reports/batch.json", "sha256": "b" * 64}],
            "readback_verified": True,
        }

    def test_sign_and_verify_canonical_receipt(self):
        signed = sign_receipt(kms_client=self.kms, key_arn=KEY_ARN, receipt=self.receipt)
        verify_receipt_signature(kms_client=self.kms, trusted_key_arn=KEY_ARN, receipt=signed)
        self.assertEqual(signed["signature"]["key_arn"], KEY_ARN)

    def test_signature_covers_every_receipt_field_but_not_signature_envelope(self):
        signed = sign_receipt(kms_client=self.kms, key_arn=KEY_ARN, receipt=self.receipt)
        changed = dict(signed, report_sha256="c" * 64)
        with self.assertRaisesRegex(ReceiptSignatureError, "verification_failed"):
            verify_receipt_signature(kms_client=self.kms, trusted_key_arn=KEY_ARN, receipt=changed)
        self.assertEqual(
            canonical_receipt_payload(signed),
            canonical_receipt_payload(dict(signed, signature={"untrusted": "ignored"})),
        )

    def test_rejects_untrusted_key_identity(self):
        signed = sign_receipt(kms_client=self.kms, key_arn=KEY_ARN, receipt=self.receipt)
        with self.assertRaisesRegex(ReceiptSignatureError, "identity_invalid"):
            verify_receipt_signature(
                kms_client=self.kms,
                trusted_key_arn="arn:aws:kms:us-east-1:123456789012:key/other-key",
                receipt=signed,
            )

    def test_rejects_unsigned_legacy_receipt(self):
        with self.assertRaisesRegex(ReceiptSignatureError, "schema_unsupported"):
            verify_receipt_signature(
                kms_client=self.kms, trusted_key_arn=KEY_ARN,
                receipt={"schema": "veltrix-evidence-archive-receipt-v1"},
            )


if __name__ == "__main__":
    unittest.main()
