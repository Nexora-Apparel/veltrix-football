import copy
import unittest

from app.provider_fixture_normalizer import normalize_fivedollar_fixture, normalize_striker_game
from app.provider_source_evidence import (
    SourceEvidenceError, build_source_evidence, validate_source_evidence,
)


class ProviderSourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "game_id": 9, "starts_at": "2026-11-10T18:00:00Z", "status": "final",
            "home": {"team_id": 1, "name": "Home", "score": 2},
            "away": {"team_id": 2, "name": "Away", "score": 1},
        }
        self.record = normalize_striker_game(
            self.raw, competition_key="soccer", endpoint="list_games",
            retrieved_at="2026-11-09T12:00:00Z", run_id="run-1", season="2026",
        )

    def test_raw_payload_and_mapping_are_recomputed(self):
        evidence = build_source_evidence(
            provider="strikerapi", payload=self.raw, normalized_record=self.record,
        )
        result = validate_source_evidence(evidence, expected_record=self.record)
        self.assertTrue(result["valid"])
        self.assertEqual(result["mapping_version"], "strikerapi.list_games.normalization.v1")

    def test_raw_payload_tampering_is_rejected(self):
        evidence = build_source_evidence(
            provider="strikerapi", payload=self.raw, normalized_record=self.record,
        )
        changed = copy.deepcopy(evidence)
        changed["raw_payload"]["home"]["score"] = 99
        with self.assertRaisesRegex(SourceEvidenceError, "raw_payload_sha256_mismatch"):
            validate_source_evidence(changed)

    def test_normalized_projection_tampering_is_rejected(self):
        evidence = build_source_evidence(
            provider="strikerapi", payload=self.raw, normalized_record=self.record,
        )
        changed = copy.deepcopy(evidence)
        changed["normalized_record"]["home_score"] = 99
        with self.assertRaises(SourceEvidenceError):
            validate_source_evidence(changed)

    def test_mapping_version_must_be_known(self):
        evidence = build_source_evidence(
            provider="strikerapi", payload=self.raw, normalized_record=self.record,
        )
        evidence["mapping_version"] = "unreviewed.mapping.v99"
        with self.assertRaisesRegex(SourceEvidenceError, "provider_mapping_version_unsupported"):
            validate_source_evidence(evidence)

    def test_fivedollar_mapping_is_recomputed(self):
        raw = {
            "id": 77, "kickoff_utc": "2026-11-10T17:00:00Z",
            "status": "finished", "season": "2026", "league": {"id": 39},
            "teams": {"home": {"id": 1, "name": "Home"},
                      "away": {"id": 2, "name": "Away"}},
            "goals": {"home": 1, "away": 0},
        }
        record = normalize_fivedollar_fixture(
            raw, endpoint="leagues/39/fixtures",
            retrieved_at="2026-11-09T12:00:00Z", run_id="run-2",
        )
        evidence = build_source_evidence(
            provider="fivedollar", payload=raw, normalized_record=record,
        )
        self.assertTrue(validate_source_evidence(evidence)["valid"])


if __name__ == "__main__":
    unittest.main()
