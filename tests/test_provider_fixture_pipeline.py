import unittest

from app.provider_fixture_pipeline import run_fixture_acquisition_pipeline


def observation(source_id):
    return {
        "provider": "strikerapi",
        "row": {
            "game_id": source_id, "starts_at": "2026-11-10T18:00:00Z",
            "status": "final",
            "home": {"team_id": 1, "name": "Home", "score": 1},
            "away": {"team_id": 2, "name": "Away", "score": 0},
        },
        "options": {
            "competition_key": "soccer", "endpoint": "list_games",
            "retrieved_at": "2026-11-09T12:00:00Z", "run_id": "pipeline-1",
        },
    }


class FixturePipelineTests(unittest.TestCase):
    def run_pipeline(self, observations):
        return run_fixture_acquisition_pipeline(
            observations=observations,
            run_id="pipeline-1",
            provider_scope=["strikerapi"],
            competition_scope=["soccer"],
            window={"from": "2026-11-01", "to": "2026-11-09"},
            retrieved_at="2026-11-09T12:00:00Z",
            request_budget={"calls_made": 0, "credits_consumed": 0},
        )

    def test_valid_batch_flows_into_report(self):
        result = self.run_pipeline([observation("1")])
        self.assertTrue(result["acceptance_pass"])
        self.assertEqual(result["report"]["quality"]["accepted_count"], 1)
        self.assertEqual(result["report"]["records"][0]["source_id"], "1")

    def test_duplicate_batch_fails_acceptance_and_reports_quarantine(self):
        result = self.run_pipeline([observation("1"), observation("1")])
        self.assertFalse(result["acceptance_pass"])
        self.assertEqual(result["report"]["quality"]["quarantined_count"], 2)
        self.assertEqual(result["report"]["quality"]["accepted_count"], 0)

    def test_pipeline_side_effects_are_all_zero(self):
        result = self.run_pipeline([observation("1")])
        self.assertTrue(all(value == 0 for value in result["side_effects"].values()))

    def test_report_hash_is_present(self):
        result = self.run_pipeline([observation("1")])
        self.assertEqual(len(result["report"]["report_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
