import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from scripts.archive_encrypted_source_evidence import (
    EvidenceArchiveError, archive_evidence, _validate_endpoint_url as validate_archive_endpoint,
)
from scripts.restore_encrypted_source_evidence import (
    EvidenceRestoreError, restore_evidence, write_verified_digest_registry,
    _validate_endpoint_url as validate_restore_endpoint,
)


TEST_SIGNING_KEY_ARN = "arn:aws:kms:us-east-1:123456789012:key/test-signing-key"


class FakeKMS:
    def __init__(self, allowed_key_arn=TEST_SIGNING_KEY_ARN):
        self.allowed_key_arn = allowed_key_arn
        self.sign_calls = 0
        self.verify_calls = 0

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        self.sign_calls += 1
        assert KeyId == self.allowed_key_arn
        assert MessageType == "DIGEST" and SigningAlgorithm == "ECDSA_SHA_256"
        return {"Signature": hashlib.sha256(KeyId.encode() + Message).digest()}

    def verify(self, KeyId, Message, MessageType, Signature, SigningAlgorithm):
        self.verify_calls += 1
        expected = hashlib.sha256(KeyId.encode() + Message).digest()
        return {"SignatureValid": (
            KeyId == self.allowed_key_arn and MessageType == "DIGEST"
            and SigningAlgorithm == "ECDSA_SHA_256" and Signature == expected
        )}


class FakeS3:
    def __init__(self, corrupt_readback=False, fail_once_on_key=None):
        self.objects = {}
        self.corrupt_readback = corrupt_readback
        self.fail_once_on_key = fail_once_on_key
        self.failed_once = False

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            error = Exception("not found")
            error.response = {"ResponseMetadata": {"HTTPStatusCode": 404}, "Error": {"Code": "404"}}
            raise error
        return {"VersionId": "version-1"}

    def put_object(self, Bucket, Key, Body, **kwargs):
        if Key == self.fail_once_on_key and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("simulated transient upload failure")
        self.objects[(Bucket, Key)] = bytes(Body)

    def get_object(self, Bucket, Key):
        body = self.objects[(Bucket, Key)]
        if self.corrupt_readback and Key.endswith(".enc"):
            body = body + b"tamper"
        return {"Body": BytesIO(body)}


class PrivateEvidenceEndpointTests(unittest.TestCase):
    def test_archive_and_restore_require_https(self):
        self.assertEqual(validate_archive_endpoint("https://objects.example.test"), "https://objects.example.test")
        self.assertEqual(validate_restore_endpoint("https://objects.example.test"), "https://objects.example.test")
        for endpoint in ("http://objects.example.test", "file:///tmp/archive", "", None):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(EvidenceArchiveError, "must_be_https"):
                    validate_archive_endpoint(endpoint)
                with self.assertRaisesRegex(EvidenceRestoreError, "must_be_https"):
                    validate_restore_endpoint(endpoint)

    def test_archive_and_restore_reject_embedded_credentials(self):
        for endpoint in ("https://user:secret@objects.example.test", "https://user@objects.example.test"):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(EvidenceArchiveError, "must_be_https"):
                    validate_archive_endpoint(endpoint)
                with self.assertRaisesRegex(EvidenceRestoreError, "must_be_https"):
                    validate_restore_endpoint(endpoint)


class PrivateEvidenceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.report = {
            "report_sha256": "a" * 64,
            "records": [{"source_id": "1"}],
            "run_id": "batch-20261110T060000Z",
        }
        self.evidence = b"encrypted-bytes-only"
        self.manifest = {
            "run_id": self.report["run_id"],
            "report_sha256": self.report["report_sha256"],
            "ciphertext_sha256": hashlib.sha256(self.evidence).hexdigest(),
            "evidence_count": 1,
        }
        self.report_path = self.root / "report.json"
        self.evidence_path = self.root / "evidence.enc"
        self.manifest_path = self.root / "manifest.json"
        self.report_path.write_text(json.dumps(self.report))
        self.evidence_path.write_bytes(self.evidence)
        self.manifest_path.write_text(json.dumps(self.manifest))

    def tearDown(self):
        self.temp.cleanup()

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_uploads_and_reads_back_all_private_objects(self, validate):
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1, "input_count": 1}
        client = FakeS3()
        receipt_path = self.root / "receipt.json"
        result = archive_evidence(
            client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix/evidence",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=receipt_path,
        )
        self.assertTrue(result["readback_verified"])
        self.assertEqual(len(result["objects"]), 3)
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(len(client.objects), 4)

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_rejects_ciphertext_digest_mismatch_before_upload(self, validate):
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1}
        self.manifest["ciphertext_sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(self.manifest))
        client = FakeS3()
        with self.assertRaisesRegex(EvidenceArchiveError, "ciphertext_digest_mismatch"):
            archive_evidence(
                client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
            )
        self.assertEqual(client.objects, {})

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_fails_when_uploaded_ciphertext_readback_differs(self, validate):
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1, "input_count": 1}
        client = FakeS3(corrupt_readback=True)
        with self.assertRaisesRegex(EvidenceArchiveError, "readback_digest_mismatch"):
            archive_evidence(
                client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
            )

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_retry_completes_partial_upload_without_overwriting_verified_objects(self, validate):
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1, "input_count": 1}
        client = FakeS3(fail_once_on_key="veltrix/encrypted/batch-20261110T060000Z.enc")
        kwargs = dict(
            client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
        )
        with self.assertRaisesRegex(RuntimeError, "simulated transient upload failure"):
            archive_evidence(**kwargs)
        # The report is already present, but its identical digest makes retry safe.
        self.assertIn(("private-bucket", "veltrix/reports/batch-20261110T060000Z.json"), client.objects)
        result = archive_evidence(**kwargs)
        self.assertTrue(result["readback_verified"])
        self.assertEqual(len(client.objects), 4)

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_completed_archive_retry_reuses_validated_receipt(self, validate):
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1, "input_count": 1}
        client = FakeS3()
        kwargs = dict(
            client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
        )
        first = archive_evidence(**kwargs)
        second = archive_evidence(**kwargs)
        self.assertEqual(first["signature"], second["signature"])
        self.assertEqual(len(client.objects), 4)

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_archives_rejected_batch_using_total_input_count(self, validate):
        validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 1, "input_count": 2,
        }
        self.report["quarantine"] = [{"input_index": 1, "reason": "invalid_row", "source": None}]
        self.manifest["evidence_count"] = 2
        self.report_path.write_text(json.dumps(self.report))
        self.manifest_path.write_text(json.dumps(self.manifest))
        client = FakeS3()
        result = archive_evidence(
            client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
        )
        self.assertTrue(result["readback_verified"])
        validate.assert_called_once()
        self.assertEqual(validate.call_args.kwargs, {"require_acceptance": False})


    @patch("scripts.restore_encrypted_source_evidence.decrypt_and_verify_source_evidence")
    @patch("scripts.restore_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_restore_verifies_archive_and_writes_only_after_full_validation(
        self, archive_validate, restore_validate, decrypt
    ):
        archive_validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        restore_validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        decrypt.return_value = [{
            "kind": "accepted", "input_index": 0,
            "payload_sha256": "a" * 64,
            "normalized_record_sha256": "b" * 64,
        }]
        client = FakeS3()
        archive_evidence(
            client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
        )
        result = restore_evidence(
            client=client, kms_client=FakeKMS(), trusted_signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket",
            receipt_key="veltrix/receipts/batch-20261110T060000Z.json",
            encryption_key="test-key", output_dir=self.root / "restored",
        )
        self.assertTrue(result["valid"])
        self.assertTrue(result["archive_receipt_signature_verified"])
        self.assertEqual(result["receipt_signing_key_arn"], TEST_SIGNING_KEY_ARN)
        self.assertEqual(result["evidence_count"], 1)
        self.assertEqual(
            result["verified_source_evidence_sha256"], ["a" * 64, "b" * 64]
        )
        self.assertTrue(Path(result["paths"]["report"]).is_file())
        decrypt.assert_called_once()

    @patch("scripts.restore_encrypted_source_evidence.decrypt_and_verify_source_evidence")
    @patch("scripts.restore_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_restore_refuses_existing_destination_without_modifying_it(
        self, archive_validate, restore_validate, decrypt
    ):
        archive_validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        restore_validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        decrypt.return_value = [{"kind": "accepted", "input_index": 0}]
        client = FakeS3()
        archive_evidence(
            client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
        )
        destination = self.root / "existing-restore"
        destination.mkdir()
        marker = destination / "keep.txt"
        marker.write_text("preserve-existing-data")
        with self.assertRaisesRegex(EvidenceRestoreError, "restore_destination_already_exists"):
            restore_evidence(
                client=client, kms_client=FakeKMS(), trusted_signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket",
                receipt_key="veltrix/receipts/batch-20261110T060000Z.json",
                encryption_key="test-key", output_dir=destination,
            )
        self.assertEqual(marker.read_text(), "preserve-existing-data")
        self.assertEqual(list(destination.iterdir()), [marker])
        self.assertFalse(any(self.root.glob(".existing-restore.restore-*")))

    @patch("scripts.restore_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_restore_rejects_tampered_archived_object_before_writing(self, validate):
        validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        client = FakeS3()
        # Build a structurally valid archive receipt through the production writer.
        with patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report") as archive_validate:
            archive_validate.return_value = validate.return_value
            archive_evidence(
                client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
            )
        key = ("private-bucket", "veltrix/encrypted/batch-20261110T060000Z.enc")
        client.objects[key] = b"tampered"
        destination = self.root / "tampered-restore"
        with self.assertRaisesRegex(EvidenceRestoreError, "restore_object_digest_mismatch:evidence"):
            restore_evidence(
                client=client, kms_client=FakeKMS(), trusted_signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket",
                receipt_key="veltrix/receipts/batch-20261110T060000Z.json",
                encryption_key="test-key", output_dir=destination,
            )
        self.assertFalse(destination.exists())


    @patch("scripts.restore_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_restore_rejects_modified_receipt_before_fetching_archived_objects(self, validate):
        validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        client = FakeS3()
        with patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report") as archive_validate:
            archive_validate.return_value = validate.return_value
            archive_evidence(
                client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN,
                bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
            )
        receipt_key = "veltrix/receipts/batch-20261110T060000Z.json"
        receipt = json.loads(client.objects[("private-bucket", receipt_key)])
        receipt["evidence_count"] = 999
        client.objects[("private-bucket", receipt_key)] = json.dumps(receipt).encode()
        destination = self.root / "tampered-receipt-restore"
        with self.assertRaisesRegex(EvidenceRestoreError, "restore_receipt_signature_invalid"):
            restore_evidence(
                client=client, kms_client=FakeKMS(), trusted_signing_key_arn=TEST_SIGNING_KEY_ARN,
                bucket="private-bucket", receipt_key=receipt_key,
                encryption_key="test-key", output_dir=destination,
            )
        self.assertFalse(destination.exists())
        self.assertEqual(len(client.objects), 4)

    @patch("scripts.restore_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_restore_rejects_receipt_object_key_outside_run_prefix(self, validate):
        validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        client = FakeS3()
        with patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report") as archive_validate:
            archive_validate.return_value = validate.return_value
            archive_evidence(
                client=client, kms_client=FakeKMS(), signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
            )
        receipt_key = "veltrix/receipts/batch-20261110T060000Z.json"
        receipt = json.loads(client.objects[("private-bucket", receipt_key)])
        receipt["objects"][0]["key"] = "unrelated/private-object"
        client.objects[("private-bucket", receipt_key)] = json.dumps(receipt).encode()
        with self.assertRaisesRegex(EvidenceRestoreError, "restore_receipt_signature_invalid"):
            restore_evidence(
                client=client, kms_client=FakeKMS(), trusted_signing_key_arn=TEST_SIGNING_KEY_ARN, bucket="private-bucket", receipt_key=receipt_key,
                encryption_key="test-key", output_dir=self.root / "bad-key-restore",
            )



    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_archive_retry_verifies_receipt_signed_by_allowlisted_old_key(self, validate):
        validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "input_count": 1,
        }
        old_arn = "arn:aws:kms:us-east-1:123456789012:key/old-receipt-key"
        new_arn = "arn:aws:kms:eu-west-1:123456789012:key/new-receipt-key"
        old_kms, new_kms = FakeKMS(old_arn), FakeKMS(new_arn)
        trusted = {old_arn: old_kms, new_arn: new_kms}
        client = FakeS3()
        first = archive_evidence(
            client=client, kms_client=old_kms, signing_key_arn=old_arn,
            trusted_kms_clients=trusted, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "old-receipt.json",
        )
        second = archive_evidence(
            client=client, kms_client=new_kms, signing_key_arn=new_arn,
            trusted_kms_clients=trusted, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "new-retry.json",
        )
        self.assertEqual(first["signature"], second["signature"])
        self.assertEqual(old_kms.sign_calls, 1)
        self.assertEqual(old_kms.verify_calls, 1)
        self.assertEqual(new_kms.sign_calls, 0)

    @patch("scripts.restore_encrypted_source_evidence.decrypt_and_verify_source_evidence")
    @patch("scripts.restore_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_restore_accepts_old_receipt_only_through_explicit_trust_registry(
        self, archive_validate, restore_validate, decrypt
    ):
        archive_validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "quarantined_count": 0, "input_count": 1,
        }
        restore_validate.return_value = archive_validate.return_value
        decrypt.return_value = [{"kind": "accepted", "input_index": 0}]
        old_arn = "arn:aws:kms:us-east-1:123456789012:key/old-receipt-key"
        new_arn = "arn:aws:kms:eu-west-1:123456789012:key/new-receipt-key"
        old_kms, new_kms = FakeKMS(old_arn), FakeKMS(new_arn)
        trusted = {old_arn: old_kms, new_arn: new_kms}
        client = FakeS3()
        archive_evidence(
            client=client, kms_client=old_kms, signing_key_arn=old_arn,
            bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
        )
        result = restore_evidence(
            client=client, kms_client=None, trusted_signing_key_arn="",
            trusted_kms_clients=trusted, bucket="private-bucket",
            receipt_key="veltrix/receipts/batch-20261110T060000Z.json",
            encryption_key="test-key", output_dir=self.root / "rotated-restore",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(old_kms.verify_calls, 1)
        self.assertEqual(new_kms.verify_calls, 0)

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_archive_rejects_current_signing_key_not_in_trust_registry(self, validate):
        validate.return_value = {
            "valid": True, "report_sha256": "a" * 64,
            "accepted_count": 1, "input_count": 1,
        }
        new_arn = "arn:aws:kms:eu-west-1:123456789012:key/new-receipt-key"
        new_kms = FakeKMS(new_arn)
        with self.assertRaisesRegex(EvidenceArchiveError, "signing_key_not_in_trust_registry"):
            archive_evidence(
                client=FakeS3(), kms_client=new_kms, signing_key_arn=new_arn,
                trusted_kms_clients={TEST_SIGNING_KEY_ARN: FakeKMS()},
                bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "blocked.json",
            )


    def test_restore_exports_signature_verified_digest_registry_atomically(self):
        output = self.root / "verified-digests.json"
        registry = write_verified_digest_registry({
            "archive_receipt_signature_verified": True,
            "receipt_sha256": "a" * 64,
            "receipt_signing_key_arn": TEST_SIGNING_KEY_ARN,
            "run_id": "batch-20261110T060000Z",
            "verified_source_evidence_sha256": ["b" * 64, "a" * 64, "b" * 64],
        }, output)
        self.assertTrue(output.is_file())
        saved = json.loads(output.read_text())
        self.assertEqual(saved, registry)
        self.assertEqual(saved["verified_source_evidence_sha256"], ["a" * 64, "b" * 64])
        self.assertTrue(saved["verified_archive_receipts"][0]["archive_receipt_signature_verified"])

    def test_verified_digest_registry_refuses_symlink_destination(self):
        target = self.root / "target-digests.json"
        target.write_text("{}")
        link = self.root / "linked-digests.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(EvidenceRestoreError, "symlink_rejected"):
            write_verified_digest_registry({
                "archive_receipt_signature_verified": True,
                "receipt_sha256": "a" * 64,
                "receipt_signing_key_arn": TEST_SIGNING_KEY_ARN,
                "run_id": "batch-20261110T060000Z",
                "verified_source_evidence_sha256": ["b" * 64],
            }, link)
        self.assertEqual(target.read_text(), "{}")


if __name__ == "__main__":
    unittest.main()
