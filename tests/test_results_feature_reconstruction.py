import unittest
from datetime import date, timedelta

from app.results_feature_reconstruction import (
    FeatureReconstructionError,
    reconstruct_pre_match_features,
)


def make_history(days=6):
    teams = ["A", "B", "C", "D"]
    pairings = [
        [("A", "B"), ("C", "D")],
        [("B", "C"), ("D", "A")],
        [("A", "C"), ("B", "D")],
        [("A", "D"), ("B", "C")],
        [("A", "B"), ("C", "D")],
        [("A", "C"), ("B", "D")],
    ]
    rows = []
    start = date(2026, 8, 1)
    for day_index in range(days):
        day = start + timedelta(days=day_index * 3)
        for match_index, (home, away) in enumerate(pairings[day_index % len(pairings)]):
            kickoff_hour = 12 + match_index * 3
            home_score = (day_index + match_index) % 4
            away_score = (day_index * 2 + match_index + 1) % 3
            fixture_id = f"hist-{day_index}-{match_index}"
            rows.append({
                "fixture_id": fixture_id,
                "competition_id": "league-1",
                "kickoff_at": f"{day.isoformat()}T{kickoff_hour:02d}:00:00Z",
                "settled_at": f"{day.isoformat()}T{kickoff_hour + 2:02d}:00:00Z",
                "home_team_id": home,
                "away_team_id": away,
                "home_score": home_score,
                "away_score": away_score,
                "source_record_sha256": f"{len(rows) + 1:064x}",
            })
    return rows


TARGET = {
    "fixture_id": "target-001",
    "competition_id": "league-1",
    "kickoff_at": "2026-09-01T18:00:00Z",
    "home_team_id": "A",
    "away_team_id": "B",
}


class ResultsFeatureReconstructionTests(unittest.TestCase):
    def test_reconstructs_all_required_model_features(self):
        result = reconstruct_pre_match_features(
            historical_matches=make_history(),
            target_fixture=TARGET,
            cutoff_hours=6,
            form_window=10,
            minimum_team_matches=3,
        )
        self.assertEqual(set(result["features"]), {
            "home_attack_goals_rate", "home_defence_conceded_rate",
            "away_attack_goals_rate", "away_defence_conceded_rate",
            "elo_difference_home", "home_form_points_rate",
            "away_form_points_rate", "home_rest_days", "away_rest_days",
            "competition_home_goals_rate", "competition_away_goals_rate",
        })
        self.assertTrue(result["provenance"]["point_in_time_verified"])
        self.assertFalse(result["provenance"]["xg_used"])
        self.assertFalse(result["publication_allowed"])

    def test_future_fixture_cannot_change_historical_features(self):
        history = make_history()
        baseline = reconstruct_pre_match_features(
            historical_matches=history, target_fixture=TARGET,
            minimum_team_matches=3,
        )
        future = {
            "fixture_id": "future-001",
            "competition_id": "league-1",
            "kickoff_at": "2026-09-10T18:00:00Z",
            "settled_at": "2026-09-10T20:00:00Z",
            "home_team_id": "A", "away_team_id": "B",
            "home_score": 9, "away_score": 0,
            "source_record_sha256": f"{999:064x}",
        }
        changed = reconstruct_pre_match_features(
            historical_matches=history + [future], target_fixture=TARGET,
            minimum_team_matches=3,
        )
        self.assertEqual(baseline["features"], changed["features"])
        self.assertEqual(
            baseline["feature_snapshot_sha256"],
            changed["feature_snapshot_sha256"],
        )

    def test_rejects_history_settled_after_feature_cutoff(self):
        history = make_history()
        for row in history:
            if "A" in (row["home_team_id"], row["away_team_id"]):
                row["settled_at"] = "2026-09-01T13:00:00Z"
        with self.assertRaisesRegex(
            FeatureReconstructionError, "home_history_below_minimum"
        ):
            reconstruct_pre_match_features(
                historical_matches=history, target_fixture=TARGET,
                minimum_team_matches=3,
            )

    def test_rejects_duplicate_fixture_ids(self):
        history = make_history()
        history.append(dict(history[0]))
        with self.assertRaisesRegex(FeatureReconstructionError, "duplicate_historical_fixture_id"):
            reconstruct_pre_match_features(
                historical_matches=history, target_fixture=TARGET,
            )

    def test_rejects_target_fixture_in_history(self):
        history = make_history()
        target_copy = dict(history[0])
        target_copy["fixture_id"] = TARGET["fixture_id"]
        history.append(target_copy)
        with self.assertRaisesRegex(FeatureReconstructionError, "target_fixture_present_in_history"):
            reconstruct_pre_match_features(
                historical_matches=history, target_fixture=TARGET,
            )

    def test_rejects_missing_team_history_instead_of_using_zero_prior(self):
        history = make_history()
        only_home = [row for row in history if row["home_team_id"] == "A"]
        with self.assertRaisesRegex(FeatureReconstructionError, "history_below_minimum"):
            reconstruct_pre_match_features(
                historical_matches=only_home, target_fixture=TARGET,
                minimum_team_matches=3,
            )


if __name__ == "__main__":
    unittest.main()
