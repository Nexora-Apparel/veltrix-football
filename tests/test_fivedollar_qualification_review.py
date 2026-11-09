import unittest

from app.fivedollar_qualification_report import build_fivedollar_qualification_report
from app.fivedollar_qualification_review import build_fivedollar_registry
from app.provider_qualification_evidence import verify_attestation_signature


class FiveDollarRegistryReviewTests(unittest.TestCase):
    def report(self):
        return build_fivedollar_qualification_report(
            run_id="98765", retrieved_at="2026-11-09T12:00:00Z",
            window_start_utc="2026-08-11T00:00:00Z",
            window_end_utc="2026-11-09T00:00:00Z",
            max_requests=10, actual_requests=3,
            endpoint_requests=[{"endpoint": "leagues", "requests": 1},
                               {"endpoint": "leagues/39/fixtures", "requests": 1},
                               {"endpoint": "leagues/140/fixtures", "requests": 1}],
            competitions=[
                {"competition_id": "39", "competition_name": "Premier League",
                 "pages_fetched": 1, "source_rows": 2, "accepted_rows": 2,
                 "invalid_rows": 0, "duplicate_ids": 0, "missing_team_ids": 0,
                 "pagination_complete": True},
                {"competition_id": "140", "competition_name": "La Liga",
                 "pages_fetched": 1, "source_rows": 1, "accepted_rows": 1,
                 "invalid_rows": 0, "duplicate_ids": 0, "missing_team_ids": 0,
                 "pagination_complete": True},
            ],
        )

    def build(self, **overrides):
        args = {
            "run": {"repository": "Nexora-Apparel/veltrix-football",
                    "workflow_run_id": "98765",
                    "workflow_path": ".github/workflows/qualify-fivedollar-competitions.yml",
                    "event": "workflow_dispatch",
                    "head_branch": "phase-3/budget-aware-acquisition-contract",
                    "head_sha": "a" * 40},
            "artifact": {"artifact_id": 123, "artifact_name": "fivedollar-competition-qualification",
                         "github_artifact_digest": "b" * 64},
            "report": self.report(), "archive_sha256": "b" * 64,
            "report_sha256": self.report()["report_sha256"],
            "reviewer": "reviewer-1", "reviewed_at": "2026-11-09T12:30:00Z",
            "signing_key": "test-key-that-is-at-least-thirty-two-characters",
            "artifact_url": "https://github.com/Nexora-Apparel/veltrix-football/actions/runs/98765/artifacts/123",
        }
        args.update(overrides)
        return build_fivedollar_registry(**args)

    def test_builds_one_scoped_signed_entry_per_competition(self):
        registry = self.build()
        self.assertEqual(registry["registry_status"], "reviewed_github_artifact_evidence")
        self.assertEqual([x["competition_key"] for x in registry["sources"]], ["39", "140"])
        attestation = registry["sources"][0]["review_attestation"]
        self.assertTrue(verify_attestation_signature(attestation, "test-key-that-is-at-least-thirty-two-characters"))
        self.assertEqual(attestation["coverage"]["provider"], "fivedollar")
        self.assertEqual(attestation["coverage"]["competition_keys"], ["140", "39"])

    def test_report_run_id_must_match_verified_run(self):
        with self.assertRaisesRegex(ValueError, "run_id_mismatch"):
            self.build(run={"repository": "Nexora-Apparel/veltrix-football",
                            "workflow_run_id": "wrong", "workflow_path": "x",
                            "event": "workflow_dispatch", "head_branch": "x", "head_sha": "a"*40})

    def test_nonqualifying_report_cannot_emit_registry(self):
        report = self.report()
        report["acceptance_pass"] = False
        with self.assertRaises(ValueError):
            self.build(report=report)

    def test_artifact_report_hash_must_match(self):
        with self.assertRaisesRegex(ValueError, "report_hash_mismatch"):
            self.build(report_sha256="c" * 64)


if __name__ == "__main__":
    unittest.main()
