import unittest

from reconcile_openfootball_5dollar_snapshots import reconcile


def of_row(day="2026-09-01", score=(2, 1), home="Arsenal FC", away="Chelsea FC"):
    return {
        "date": day,
        "time": "20:00",
        "team1": home,
        "team2": away,
        "score": {"ft": list(score)} if score is not None else None,
    }


def fd_row(day="2026-09-01", score=(2, 1), fixture_id="100"):
    return {
        "id": fixture_id,
        "status": "finished",
        "kickoff_utc": day + "T19:00:00+00:00",
        "teams": {
            "home": {"id": 1, "name": "Arsenal"},
            "away": {"id": 2, "name": "Chelsea"},
        },
        "goals": {"home": score[0], "away": score[1]} if score is not None else {"home": None, "away": None},
    }


class LiveSnapshotReconciliationTests(unittest.TestCase):
    def test_exact_score_match_passes(self):
        report = reconcile(
            {"matches": [of_row()]},
            {"rows": [fd_row()]},
            "2026-08-01", "2026-10-01",
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["counts"]["score_agreements"], 1)

    def test_missing_source_score_is_not_replaced_with_zero(self):
        report = reconcile(
            {"matches": [of_row(score=None)]},
            {"rows": [fd_row()]},
            "2026-08-01", "2026-10-01",
        )
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["counts"]["missing_openfootball_scores"], 1)
        self.assertEqual(report["counts"]["score_agreements"], 0)

    def test_date_conflict_is_reported_not_timezone_normalized(self):
        report = reconcile(
            {"matches": [of_row(day="2026-09-02")]},
            {"rows": [fd_row(day="2026-09-01")]},
            "2026-08-01", "2026-10-01",
        )
        self.assertEqual(report["counts"]["date_conflicts"], 1)
        self.assertEqual(report["counts"]["unmatched_reference_fixtures"], 0)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")

    def test_unknown_team_identity_fails_closed(self):
        row = of_row(home="Unknown FC")
        report = reconcile(
            {"matches": [row]},
            {"rows": [fd_row()]},
            "2026-08-01", "2026-10-01",
        )
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(len(report["team_crosswalk"]["unmapped_source_teams"]), 1)

    def test_duplicate_reference_ids_are_reported(self):
        report = reconcile(
            {"matches": [of_row()]},
            {"rows": [fd_row(), fd_row(fixture_id="100")]},
            "2026-08-01", "2026-10-01",
        )
        self.assertEqual(report["counts"]["duplicate_fivedollar_fixture_ids"], 1)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
