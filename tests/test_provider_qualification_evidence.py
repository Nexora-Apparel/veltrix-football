import copy
import unittest

from app.provider_qualification_evidence import (
    QualificationEvidenceError,
    STRIKERAPI_COMPETITIONS,
    validate_run_metadata,
    validate_artifact_metadata,
    validate_coverage_report,
    build_review_attestation,
    verify_attestation_signature,
)


def good_run():
    return {
        "id": 12345, "repository": {"full_name": "Nexora-Apparel/veltrix-football"},
        "path": ".github/workflows/verify-strikerapi-17-competitions.yml",
        "event": "workflow_dispatch", "status": "completed", "conclusion": "success",
        "head_branch": "phase-3/strikerapi-readonly-qualification",
        "head_sha": "a" * 40, "created_at": "2026-11-10T00:00:00Z",
        "updated_at": "2026-11-10T00:10:00Z",
    }


def good_artifact():
    return {"id": 456, "name": "strikerapi-17-competition-coverage",
            "expired": False, "digest": "sha256:" + "b" * 64,
            "expires_at": "2026-11-17T00:00:00Z"}


def good_report():
    checks = []
    for league in sorted(STRIKERAPI_COMPETITIONS):
        for status in ("final", "scheduled"):
            rows = 3 if status == "final" else 0
            checks.append({
                "league_key": league, "status": status, "rows": rows, "valid": rows,
                "invalid": 0, "duplicate_ids": 0, "pages": 1,
                "pagination_truncated": False,
            })
    return {
        "schema_version": 1, "mode": "read_only_17_competition_rolling_coverage",
        "provider": "StrikerAPI", "competition_count": 17, "check_count": 34,
        "acceptance_pass": True, "retrieved_at": "2026-11-10T00:00:00+00:00",
        "totals": {"rows": 51, "valid": 51, "invalid": 0, "duplicate_ids": 0},
        "truncated_checks": [], "database_writes": 0, "imports": 0,
        "checkpoints": 0, "canonical_merges": 0,
        "request_budget": {"maximum_calls": 102, "actual_calls": 34,
                           "actual_documented_credits": 68},
        "checks": checks,
    }


class QualificationEvidenceTests(unittest.TestCase):
    def test_run_metadata_accepts_exact_manual_success(self):
        result = validate_run_metadata(
            good_run(), repository="Nexora-Apparel/veltrix-football",
            workflow_path=".github/workflows/verify-strikerapi-17-competitions.yml",
            expected_branch="phase-3/strikerapi-readonly-qualification",
            expected_sha="a" * 40,
        )
        self.assertEqual(result["workflow_run_id"], "12345")

    def test_rejects_wrong_repo_workflow_event_branch_or_sha(self):
        cases = [
            ("repository", {"repository": {"full_name": "other/repo"}}),
            ("path", {"path": "wrong.yml"}),
            ("event", {"event": "push"}),
            ("head_branch", {"head_branch": "main"}),
            ("head_sha", {"head_sha": "c" * 40}),
            ("conclusion", {"conclusion": "failure"}),
        ]
        for field, update in cases:
            with self.subTest(field=field):
                run = good_run()
                run.update(update)
                with self.assertRaises(QualificationEvidenceError):
                    validate_run_metadata(
                        run, repository="Nexora-Apparel/veltrix-football",
                        workflow_path=".github/workflows/verify-strikerapi-17-competitions.yml",
                        expected_branch="phase-3/strikerapi-readonly-qualification",
                        expected_sha="a" * 40,
                    )

    def test_artifact_requires_matching_name_digest_and_not_expired(self):
        self.assertEqual(validate_artifact_metadata(
            good_artifact(), expected_name="strikerapi-17-competition-coverage"
        )["artifact_id"], 456)
        for field, value in (("expired", True), ("digest", None), ("name", "other")):
            artifact = good_artifact()
            artifact[field] = value
            with self.assertRaises(QualificationEvidenceError):
                validate_artifact_metadata(
                    artifact, expected_name="strikerapi-17-competition-coverage"
                )

    def test_coverage_requires_all_17_competitions_and_both_statuses(self):
        result = validate_coverage_report(good_report())
        self.assertEqual(result["competition_count"], 17)
        self.assertEqual(result["check_count"], 34)

    def test_rejects_missing_competition_but_records_empty_final_window(self):
        report = good_report()
        report["checks"].pop()
        report["check_count"] = 33
        with self.assertRaises(QualificationEvidenceError):
            validate_coverage_report(report)
        report = good_report()
        report["checks"][0]["rows"] = 0
        report["checks"][0]["valid"] = 0
        report["totals"]["rows"] = 48
        report["totals"]["valid"] = 48
        result = validate_coverage_report(report)
        self.assertEqual(result["competition_count"], 16)
        self.assertEqual(result["observed_competition_count"], 17)

    def test_rejects_inconsistent_aggregate_accounting_and_no_final_history(self):
        report = good_report()
        report["totals"]["valid"] -= 1
        with self.assertRaisesRegex(QualificationEvidenceError, "coverage_total_valid_mismatch"):
            validate_coverage_report(report)
        report = good_report()
        for row in report["checks"]:
            if row["status"] == "final":
                row["rows"] = 0
                row["valid"] = 0
        report["totals"]["rows"] = 51
        report["totals"]["valid"] = 51
        with self.assertRaisesRegex(QualificationEvidenceError, "coverage_no_competition_with_final_history"):
            validate_coverage_report(report)

    def test_rejects_bad_counts_truncation_and_side_effects(self):
        for mutate in (
            lambda x: x["totals"].update(invalid=1),
            lambda x: x.update(truncated_checks=["soccer:final"]),
            lambda x: x.update(database_writes=1),
            lambda x: x["checks"][0].update(pagination_truncated=True),
            lambda x: x["request_budget"].update(actual_calls=103),
        ):
            report = good_report()
            mutate(report)
            with self.assertRaises(QualificationEvidenceError):
                validate_coverage_report(report)

    def test_attestation_binds_run_artifact_and_local_hashes(self):
        run = validate_run_metadata(
            good_run(), repository="Nexora-Apparel/veltrix-football",
            workflow_path=".github/workflows/verify-strikerapi-17-competitions.yml",
            expected_branch="phase-3/strikerapi-readonly-qualification",
            expected_sha="a" * 40,
        )
        artifact = validate_artifact_metadata(
            good_artifact(), expected_name="strikerapi-17-competition-coverage"
        )
        attestation = build_review_attestation(
            run=run, artifact=artifact, archive_sha256="d" * 64,
            report_sha256="e" * 64, coverage=validate_coverage_report(good_report()),
            reviewer="reviewer", reviewed_at="2026-11-10T00:15:00Z",
            signing_key="unit-test-qualification-key-32chars-minimum",
        )
        self.assertEqual(attestation["review_status"], "qualified")
        self.assertEqual(attestation["head_sha"], "a" * 40)
        self.assertTrue(verify_attestation_signature(
            attestation, "unit-test-qualification-key-32chars-minimum"
        ))
        tampered = dict(attestation)
        tampered["head_sha"] = "f" * 40
        self.assertFalse(verify_attestation_signature(
            tampered, "unit-test-qualification-key-32chars-minimum"
        ))


if __name__ == "__main__":
    unittest.main()
