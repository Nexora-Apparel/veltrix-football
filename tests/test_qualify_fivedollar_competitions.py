import unittest
from datetime import datetime, timedelta, timezone

from scripts.qualify_fivedollar_competitions import Budget, collect


class FakeBudget(Budget):
    def __init__(self):
        super().__init__(maximum=10)
        self.calls = []

    def get(self, endpoint, params, key):
        self.actual += 1
        self.by_endpoint[endpoint] = self.by_endpoint.get(endpoint, 0) + 1
        self.calls.append((endpoint, params))
        if endpoint == "leagues":
            return {"success": 1, "data": [
                {"id": 39, "name": "Premier League"},
                {"id": 140, "name": "La Liga"},
            ], "pagination": {"has_more": False}}
        if endpoint == "leagues/39/fixtures":
            return {"success": 1, "data": [{
                "id": 1001, "status": "finished", "kickoff_utc": (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(),
                "league": {"id": 39},
                "teams": {"home": {"id": 1, "name": "Home A"}, "away": {"id": 2, "name": "Away A"}},
                "goals": {"home": 2, "away": 0},
            }], "pagination": {"has_more": False}}
        if endpoint == "leagues/140/fixtures":
            return {"success": 1, "data": [{
                "id": 2001, "status": "finished", "kickoff_utc": (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(),
                "league": {"id": 140},
                "teams": {"home": {"id": 3, "name": "Home B"}, "away": {"id": 4, "name": "Away B"}},
                "goals": {"home": 1, "away": 1},
            }], "pagination": {"has_more": False}}
        raise AssertionError(endpoint)


class QualificationRunnerTests(unittest.TestCase):
    def test_collect_uses_only_catalogue_competitions_and_exact_request_budget(self):
        budget = FakeBudget()
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertEqual(report["competition_count"], 2)
        self.assertEqual(report["request_budget"]["actual_requests"], 3)
        self.assertTrue(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["accepted_rows"], 2)
        self.assertTrue(report["catalogue"]["pagination_complete"])

    def test_missing_team_ids_are_not_accepted(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues/39/fixtures":
                payload["data"][0]["teams"]["home"]["id"] = None
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["missing_team_ids"], 1)

    def test_out_of_window_result_is_invalid(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues/39/fixtures":
                payload["data"][0]["kickoff_utc"] = "2020-01-01T00:00:00Z"
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["invalid_rows"], 1)

    def test_catalogue_truncation_blocks_acceptance(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues":
                if params["page"] == 1:
                    payload["pagination"]["has_more"] = True
                else:
                    payload["data"] = []
                    payload["pagination"]["has_more"] = params["page"] < 5
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertFalse(report["catalogue"]["pagination_complete"])


if __name__ == "__main__":
    unittest.main()
