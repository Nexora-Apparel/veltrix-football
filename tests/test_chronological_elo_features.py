import unittest

from app.chronological_elo_features import EloFeatureError, reconstruct_elo_features


def match(fid, day, home, away, hs, aws):
    return {
        "competition_key": "EPL", "fixture_id": fid,
        "kickoff_at": f"2026-01-{day:02d}T15:00:00Z",
        "settled_at": f"2026-01-{day:02d}T17:00:00Z",
        "home_team_id": home, "away_team_id": away,
        "home_score": hs, "away_score": aws,
        "source_record_sha256": "a" * 64,
    }


def target(fid="future", home="A", away="B", cutoff="2026-01-20T00:00:00Z"):
    return {
        "fixture_id": fid, "competition_key": "EPL",
        "kickoff_at": "2026-01-20T15:00:00Z", "feature_as_of": cutoff,
        "home_team_id": home, "away_team_id": away,
    }


class ChronologicalEloFeatureTests(unittest.TestCase):
    def test_uses_only_settled_history_before_cutoff(self):
        result = reconstruct_elo_features(
            history=[match("m1", 1, "A", "B", 3, 0),
                     match("m2", 10, "B", "A", 2, 0)],
            targets=[target()],
        )
        row = result["features"][0]
        self.assertEqual(row["history_match_count"], 2)
        self.assertGreater(row["elo_difference_home"], 0)
        self.assertFalse(row["publication_allowed"])

    def test_excludes_future_settlement_even_if_kickoff_was_earlier(self):
        late = match("m1", 1, "A", "B", 2, 0)
        late["settled_at"] = "2026-01-20T00:00:00Z"
        result = reconstruct_elo_features(history=[late], targets=[target()])
        self.assertEqual(result["features"][0]["history_match_count"], 0)

    def test_competitions_are_isolated(self):
        other = match("m1", 1, "A", "B", 3, 0)
        other["competition_key"] = "Ligue1"
        result = reconstruct_elo_features(history=[other], targets=[target()])
        self.assertEqual(result["features"][0]["history_match_count"], 0)

    def test_rejects_naive_cutoff(self):
        with self.assertRaisesRegex(EloFeatureError, "timezone_missing"):
            reconstruct_elo_features(
                history=[], targets=[target(cutoff="2026-01-20T00:00:00")]
            )

    def test_rejects_duplicate_history_fixture(self):
        item = match("m1", 1, "A", "B", 1, 0)
        with self.assertRaisesRegex(EloFeatureError, "duplicate_fixture"):
            reconstruct_elo_features(history=[item, item], targets=[target()])

    def test_rejects_same_team_fixture(self):
        with self.assertRaisesRegex(EloFeatureError, "same_team"):
            reconstruct_elo_features(history=[], targets=[target(home="A", away="A")])


if __name__ == "__main__":
    unittest.main()
