import hashlib
import json
import unittest

from app.provider_acquisition_report import build_acquisition_report
from app.provider_acquisition_artifact import ArtifactIntegrityError, validate_acquisition_report
from app.provider_fixture_normalizer import normalize_striker_game
from app.provider_source_evidence import build_source_evidence


class AcquisitionArtifactTests(unittest.TestCase):
    def make_report(self):
        raw = {
            "game_id": 42, "starts_at": "2026-11-10T18:00:00Z", "status": "final",
            "home": {"team_id": 1, "name": "Home", "score": 2},
            "away": {"team_id": 2, "name": "Away", "score": 0},
        }
        record = normalize_striker_game(
            raw, competition_key="soccer", endpoint="list_games",
            retrieved_at="2026-11-09T12:00:00Z", run_id="r-1", season="2026",
        )
        record["source_evidence"] = build_source_evidence(
            provider="strikerapi", payload=raw, normalized_record=record,
        )
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

    def test_duplicate_quarantine_summary_passes_sanitization(self):
        report = self.make_report()
        record = report["records"][0]
        report["records"] = []
        report["quarantine"] = [
            {"input_index": 0, "reason": "duplicate_provider_competition_source_identity",
             "source": {key: record[key] for key in (
                 "provider", "source_id", "competition_key",
                 "home_team_source_id", "away_team_source_id", "payload_sha256",
             )}},
            {"input_index": 1, "reason": "duplicate_provider_competition_source_identity",
             "source": {key: record[key] for key in (
                 "provider", "source_id", "competition_key",
                 "home_team_source_id", "away_team_source_id", "payload_sha256",
             )}},
        ]
        report["quality"]["accepted_count"] = 0
        report["quality"]["quarantined_count"] = 2
        report["quality"]["input_count"] = 2
        report["quality"]["acceptance_pass"] = False
        self.rehash(report)
        result = validate_acquisition_report(report)
        self.assertEqual(result["quarantined_count"], 2)
        self.assertFalse(result["acceptance_pass"])

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
