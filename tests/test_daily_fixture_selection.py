import unittest

from app.daily_fixture_selection import select_daily_fixtures


QUALIFIED = {"fivedollar": ["39"], "strikerapi": ["argentina"]}


def fixture(source_id, kickoff="2026-11-10T18:00:00Z",
            provider="fivedollar", competition="39", status="scheduled"):
    return {
        "schema_version": 1, "provider": provider, "source_id": str(source_id),
        "competition_key": competition, "home_team_source_id": "1",
        "away_team_source_id": "2", "home_team_name": "Home",
        "away_team_name": "Away", "kickoff_at": kickoff,
        "source_status": status, "normalized_status": status,
        "home_score": None, "away_score": None, "endpoint": "fixtures",
        "retrieved_at": "2026-11-09T12:00:00Z",
        "payload_sha256": "a" * 64, "run_id": "test",
    }


class DailyFixtureSelectionTests(unittest.TestCase):
    def select(self, rows, **kwargs):
        args = {
            "records": rows, "target_date": "2026-11-10",
            "as_of": "2026-11-09T20:00:00Z",
            "qualified_sources": QUALIFIED,
        }
        args.update(kwargs)
        return select_daily_fixtures(**args)

    def test_selects_only_future_scheduled_qualified_records(self):
        result = self.select([
            fixture("1"),
            fixture("2", provider="unverified", competition="unknown"),
            fixture("3", status="finished"),
            fixture("4", kickoff="2026-11-09T19:00:00Z"),
            fixture("5", kickoff="2026-11-11T10:00:00Z"),
        ])
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["selected"][0]["source_id"], "1")
        self.assertEqual(result["policy"]["synthetic_fixtures"], 0)

    def test_lagos_day_boundary_is_used_not_utc_date(self):
        result = self.select([fixture("edge", kickoff="2026-11-09T23:30:00Z")])
        self.assertEqual(result["selected_count"], 1)

    def test_records_after_lagos_day_are_excluded(self):
        result = self.select([fixture("next", kickoff="2026-11-10T23:30:00Z")])
        self.assertEqual(result["selected_count"], 0)
        self.assertEqual(result["excluded_reasons"]["outside_target_lagos_date"], 1)

    def test_maximum_is_hard_capped_at_25(self):
        with self.assertRaisesRegex(ValueError, "max_fixtures_must_be_between_1_and_25"):
            self.select([], max_fixtures=26)

    def test_daily_selection_never_exceeds_25(self):
        rows = [fixture(str(i)) for i in range(30)]
        result = self.select(rows)
        self.assertEqual(result["eligible_count"], 30)
        self.assertEqual(result["selected_count"], 25)
        self.assertEqual(result["excluded_reasons"]["daily_cap_exceeded"], 5)

    def test_duplicate_source_identity_is_selected_once(self):
        result = self.select([fixture("dup"), fixture("dup")])
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["excluded_reasons"]["duplicate_source_identity"], 1)

    def test_same_source_id_in_different_competitions_is_not_collapsed(self):
        rows = [
            fixture("same", competition="39"),
            fixture("same", provider="strikerapi", competition="argentina"),
        ]
        result = self.select(rows)
        self.assertEqual(result["selected_count"], 2)

    def test_naive_as_of_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "as_of_timezone_missing"):
            self.select([], as_of="2026-11-09T20:00:00")

    def test_favourites_only_filter_is_explicitly_disabled(self):
        result = self.select([fixture("underdog")])
        self.assertFalse(result["policy"]["favourites_only_filter"])


if __name__ == "__main__":
    unittest.main()
