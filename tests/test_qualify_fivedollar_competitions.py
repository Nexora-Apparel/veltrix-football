import unittest
from datetime import datetime, timedelta, timezone

from app.fivedollar_qualification_report import validate_fivedollar_qualification_report
from scripts.qualify_fivedollar_competitions import Budget, collect


class FakeBudget(Budget):
    def __init__(self):
        super().__init__(maximum=10)
        self.calls = []

    def get(self, endpoint, params, key):
        if self.actual >= self.maximum:
            raise RuntimeError("request_budget_exhausted")
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

    def test_empty_team_identifier_is_not_accepted(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues/39/fixtures":
                payload["data"][0]["teams"]["home"]["id"] = ""
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["missing_team_ids"], 1)

    def test_same_home_and_away_team_is_invalid(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues/39/fixtures":
                payload["data"][0]["teams"]["away"]["id"] = 1
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["invalid_rows"], 1)

    def test_malformed_catalogue_row_fails_closed(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues":
                payload["data"].append({"id": 999})
            return payload

        budget.get = altered
        with self.assertRaisesRegex(RuntimeError, "provider_catalogue_row_invalid"):
            collect("test-key", budget, 90, 3, "test-run")

    def test_non_numeric_catalogue_id_is_rejected(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues":
                payload["data"][0]["id"] = "../39"
            return payload

        budget.get = altered
        with self.assertRaisesRegex(RuntimeError, "provider_catalogue_row_invalid"):
            collect("test-key", budget, 90, 3, "test-run")


    def test_non_numeric_fixture_id_is_invalid(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues/39/fixtures":
                payload["data"][0]["id"] = "../1001"
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["invalid_rows"], 1)

    def test_numeric_string_and_integer_fixture_ids_dedupe(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues/39/fixtures":
                payload["data"].append(dict(payload["data"][0], id="1001"))
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["duplicate_ids"], 1)

    def test_numeric_equivalent_home_and_away_ids_are_invalid(self):
        budget = FakeBudget()
        original = budget.get

        def altered(endpoint, params, key):
            payload = original(endpoint, params, key)
            if endpoint == "leagues/39/fixtures":
                payload["data"][0]["teams"]["away"]["id"] = "01"
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertEqual(report["aggregates"]["invalid_rows"], 1)

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

    def test_budget_exhaustion_emits_valid_incomplete_report(self):
        budget = FakeBudget()
        budget.maximum = 2
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        validation = validate_fivedollar_qualification_report(report)
        self.assertTrue(validation["valid"])
        self.assertFalse(validation["acceptance_pass"])
        self.assertEqual(report["request_budget"]["actual_requests"], 2)
        by_id = {row["competition_id"]: row for row in report["competitions"]}
        self.assertEqual(by_id["140"]["pages_fetched"], 0)

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
                    payload["pagination"]["has_more"] = True
            return payload

        budget.get = altered
        report = collect("test-key", budget, 90, 3, "test-run")
        self.assertFalse(report["acceptance_pass"])
        self.assertFalse(report["catalogue"]["pagination_complete"])


if __name__ == "__main__":
    unittest.main()
