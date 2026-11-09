import unittest

from app.provider_fixture_normalizer import (
    normalize_fivedollar_fixture,
    normalize_striker_game,
    normalize_observation,
)


RETRIEVED = "2026-11-09T12:00:00Z"
RUN = "run-test-001"


def striker_row():
    return {
        "game_id": 9001, "starts_at": "2026-11-10T18:00:00+01:00",
        "status": "final",
        "home": {"team_id": 11, "name": "Home FC", "score": 2},
        "away": {"team_id": 12, "name": "Away FC", "score": 1},
    }


def dollar_row():
    return {
        "id": 7001, "kickoff_utc": "2026-11-10T17:00:00Z",
        "status": "finished", "season": "2026",
        "league": {"id": 39},
        "teams": {
            "home": {"id": 101, "name": "Home FC"},
            "away": {"id": 102, "name": "Away FC"},
        },
        "goals": {"home": 2, "away": 1},
    }


class FixtureNormalizerTests(unittest.TestCase):
    def test_striker_normalizes_and_preserves_provenance(self):
        result = normalize_striker_game(
            striker_row(), competition_key="soccer", endpoint="list_games",
            retrieved_at=RETRIEVED, run_id=RUN, season="2026",
        )
        self.assertEqual(result["provider"], "strikerapi")
        self.assertEqual(result["source_id"], "9001")
        self.assertEqual(result["kickoff_at"], "2026-11-10T17:00:00Z")
        self.assertEqual(result["normalized_status"], "finished")
        self.assertEqual(result["home_score"], 2)
        self.assertEqual(len(result["payload_sha256"]), 64)
        self.assertEqual(result["run_id"], RUN)

    def test_fivedollar_normalizes_provider_specific_ids(self):
        result = normalize_fivedollar_fixture(
            dollar_row(), endpoint="fixtures", retrieved_at=RETRIEVED, run_id=RUN,
        )
        self.assertEqual(result["provider"], "fivedollar")
        self.assertEqual(result["competition_key"], "39")
        self.assertEqual(result["home_team_source_id"], "101")
        self.assertEqual(result["kickoff_at"], "2026-11-10T17:00:00Z")

    def test_equivalent_kickoffs_normalize_identically(self):
        s = normalize_striker_game(
            striker_row(), competition_key="soccer", endpoint="list_games",
            retrieved_at=RETRIEVED, run_id=RUN,
        )
        d = normalize_fivedollar_fixture(
            dollar_row(), endpoint="fixtures", retrieved_at=RETRIEVED, run_id=RUN,
        )
        self.assertEqual(s["kickoff_at"], d["kickoff_at"])

    def test_naive_kickoff_is_rejected(self):
        row = striker_row()
        row["starts_at"] = "2026-11-10T18:00:00"
        with self.assertRaisesRegex(ValueError, "kickoff_timezone_missing"):
            normalize_striker_game(row, competition_key="soccer", endpoint="list_games",
                                   retrieved_at=RETRIEVED, run_id=RUN)

    def test_finished_match_without_both_scores_is_rejected(self):
        row = striker_row()
        row["away"]["score"] = None
        with self.assertRaisesRegex(ValueError, "finished_fixture_missing_score"):
            normalize_striker_game(row, competition_key="soccer", endpoint="list_games",
                                   retrieved_at=RETRIEVED, run_id=RUN)

    def test_duplicate_team_ids_are_rejected(self):
        row = striker_row()
        row["away"]["team_id"] = row["home"]["team_id"]
        with self.assertRaisesRegex(ValueError, "home_away_team_id_collision"):
            normalize_striker_game(row, competition_key="soccer", endpoint="list_games",
                                   retrieved_at=RETRIEVED, run_id=RUN)

    def test_unknown_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported_provider"):
            normalize_observation("unknown", {}, endpoint="x")

    def test_payload_hash_is_stable(self):
        first = normalize_striker_game(
            striker_row(), competition_key="soccer", endpoint="list_games",
            retrieved_at=RETRIEVED, run_id=RUN,
        )
        second = normalize_striker_game(
            striker_row(), competition_key="soccer", endpoint="list_games",
            retrieved_at=RETRIEVED, run_id=RUN,
        )
        self.assertEqual(first["payload_sha256"], second["payload_sha256"])


if __name__ == "__main__":
    unittest.main()
