import hashlib
import json
import unittest

from app.provider_acquisition_report import build_acquisition_report
from app.provider_acquisition_artifact import ArtifactIntegrityError, validate_acquisition_report


class AcquisitionArtifactTests(unittest.TestCase):
    def make_report(self):
        record = {
            "schema_version": 1, "provider": "strikerapi", "source_id": "42",
            "competition_key": "soccer", "season": "2026",
            "home_team_source_id": "1", "away_team_source_id": "2",
            "home_team_name": "Home", "away_team_name": "Away",
            "kickoff_at": "2026-11-10T18:00:00Z",
            "source_status": "final", "normalized_status": "finished",
            "home_score": 2, "away_score": 0, "endpoint": "list_games",
            "retrieved_at": "2026-11-09T12:00:00Z",
            "payload_sha256": "a" * 64, "run_id": "r-1",
        }
        return build_acquisition_report(
            run_id="r-1", provider_scope=["strikerapi"],
            competition_scope=["soccer"], window={"from": "2026-11-01", "to": "2026-11-09"},
            retrieved_at="2026-11-09T12:00:00Z",
            batch_result={"input_count": 1, "accepted": [record],
                          "quarantined": [], "acceptance_pass": True},
        )

    @staticmethod
    def rehash(report):
        report.pop("report_sha256", None)
        canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        report["report_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()

    def test_valid_report_passes_integrity(self):
        result = validate_acquisition_report(self.make_report())
        self.assertTrue(result["valid"])
        self.assertEqual(result["accepted_count"], 1)

    def test_report_tampering_is_detected(self):
        report = self.make_report()
        report["records"][0]["home_team_name"] = "Tampered"
        with self.assertRaisesRegex(ArtifactIntegrityError, "report_hash_mismatch"):
            validate_acquisition_report(report)

    def test_accepted_count_mismatch_is_detected_even_when_rehashed(self):
        report = self.make_report()
        report["quality"]["accepted_count"] = 99
        self.rehash(report)
        with self.assertRaisesRegex(ArtifactIntegrityError, "accepted_count_mismatch"):
            validate_acquisition_report(report)

    def test_raw_payload_quarantine_is_rejected(self):
        report = self.make_report()
        report["quarantine"] = [{
            "input_index": 1, "reason": "bad_row",
            "source": {"provider": "strikerapi", "raw_payload": {"secret": "x"}},
        }]
        report["quality"]["quarantined_count"] = 1
        report["quality"]["input_count"] = 2
        self.rehash(report)
        with self.assertRaisesRegex(ArtifactIntegrityError, "quarantine_source_not_sanitized"):
            validate_acquisition_report(report)

    def test_nonzero_database_write_claim_is_rejected(self):
        report = self.make_report()
        report["side_effects"]["database_writes"] = 1
        self.rehash(report)
        with self.assertRaisesRegex(ArtifactIntegrityError, "side_effect_boundary_invalid"):
            validate_acquisition_report(report)


if __name__ == "__main__":
    unittest.main()
