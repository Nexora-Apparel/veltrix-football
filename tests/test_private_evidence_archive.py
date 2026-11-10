import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from scripts.archive_encrypted_source_evidence import (
    EvidenceArchiveError, archive_evidence,
)


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
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1}
        client = FakeS3()
        receipt_path = self.root / "receipt.json"
        result = archive_evidence(
            client=client, bucket="private-bucket", prefix="veltrix/evidence",
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
                client=client, bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
            )
        self.assertEqual(client.objects, {})

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_fails_when_uploaded_ciphertext_readback_differs(self, validate):
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1}
        client = FakeS3(corrupt_readback=True)
        with self.assertRaisesRegex(EvidenceArchiveError, "readback_digest_mismatch"):
            archive_evidence(
                client=client, bucket="private-bucket", prefix="veltrix",
                report_path=self.report_path, evidence_path=self.evidence_path,
                manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
            )

    @patch("scripts.archive_encrypted_source_evidence.validate_fivedollar_history_batch_report")
    def test_retry_completes_partial_upload_without_overwriting_verified_objects(self, validate):
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1}
        client = FakeS3(fail_once_on_key="veltrix/encrypted/batch-20261110T060000Z.enc")
        kwargs = dict(
            client=client, bucket="private-bucket", prefix="veltrix",
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
        validate.return_value = {"valid": True, "report_sha256": "a" * 64, "accepted_count": 1}
        client = FakeS3()
        kwargs = dict(
            client=client, bucket="private-bucket", prefix="veltrix",
            report_path=self.report_path, evidence_path=self.evidence_path,
            manifest_path=self.manifest_path, receipt_output_path=self.root / "receipt.json",
        )
        first = archive_evidence(**kwargs)
        second = archive_evidence(**kwargs)
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertEqual(len(client.objects), 4)


if __name__ == "__main__":
    unittest.main()
