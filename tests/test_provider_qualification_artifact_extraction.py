import tempfile
import unittest
import zipfile
from pathlib import Path

from app.provider_qualification_evidence import QualificationEvidenceError
from scripts.review_provider_qualification import (
    MAX_ARCHIVE_ENTRIES,
    MAX_REPORT_BYTES,
    REPORT_NAME,
    extract_coverage_report,
)


class QualificationArtifactExtractionTests(unittest.TestCase):
    def make_archive(self, members):
        temp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        temp.close()
        path = Path(temp.name)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, data in members:
                bundle.writestr(name, data)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_extracts_exact_sanitized_report(self):
        payload = b'{"schema_version":1,"acceptance_pass":true}'
        archive = self.make_archive([("reports/" + REPORT_NAME, payload)])
        self.assertEqual(extract_coverage_report(archive), payload)

    def test_rejects_missing_or_ambiguous_report(self):
        missing = self.make_archive([("other.json", b"{}")])
        with self.assertRaisesRegex(QualificationEvidenceError, "missing_or_ambiguous"):
            extract_coverage_report(missing)
        ambiguous = self.make_archive([
            ("a/" + REPORT_NAME, b"{}"),
            ("b/" + REPORT_NAME, b"{}"),
        ])
        with self.assertRaisesRegex(QualificationEvidenceError, "missing_or_ambiguous"):
            extract_coverage_report(ambiguous)

    def test_rejects_report_size_over_limit(self):
        archive = self.make_archive([("reports/" + REPORT_NAME, b"x" * (MAX_REPORT_BYTES + 1))])
        with self.assertRaisesRegex(QualificationEvidenceError, "report_size_limit"):
            extract_coverage_report(archive)

    def test_rejects_excessive_archive_entry_count(self):
        archive = self.make_archive([
            (f"entry-{index}.txt", b"x")
            for index in range(MAX_ARCHIVE_ENTRIES + 1)
        ])
        with self.assertRaisesRegex(QualificationEvidenceError, "entry_limit"):
            extract_coverage_report(archive)


if __name__ == "__main__":
    unittest.main()
