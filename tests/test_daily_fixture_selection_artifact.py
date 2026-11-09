import copy
import os
import unittest

from app.provider_acquisition_report import build_acquisition_report
from app.provider_qualification_evidence import sign_attestation
from app.daily_fixture_selection_artifact import (
    SelectionArtifactError,
    build_daily_selection_artifact,
    qualified_sources_from_registry,
    validate_daily_selection_artifact,
)


class DailySelectionArtifactTests(unittest.TestCase):
    def setUp(self):
        self.signing_key = "unit-test-qualification-key-32chars-minimum"
        os.environ["VELTRIX_QUALIFICATION_ATTESTATION_KEY"] = self.signing_key
        self.record = {
            "schema_version": 1, "provider": "fivedollar", "source_id": "101",
            "competition_key": "39", "season": "2026",
            "home_team_source_id": "1", "away_team_source_id": "2",
            "home_team_name": "Home", "away_team_name": "Away",
            "kickoff_at": "2026-11-10T18:00:00Z",
            "source_status": "scheduled", "normalized_status": "scheduled",
            "home_score": None, "away_score": None, "endpoint": "fixtures",
            "retrieved_at": "2026-11-09T12:00:00Z",
            "payload_sha256": "a" * 64, "run_id": "acq-1",
        }
        self.report = build_acquisition_report(
            run_id="acq-1", provider_scope=["fivedollar"],
            competition_scope=["39"], window={"local_date": "2026-11-10"},
            retrieved_at="2026-11-09T12:00:00Z",
            batch_result={"input_count": 1, "accepted": [self.record],
                          "quarantined": [], "acceptance_pass": True},
        )
        self.registry = {
            "schema_version": 1,
            "sources": [{
                "provider": "fivedollar", "competition_key": "39",
                "qualification_status": "qualified",
                "qualification_run_id": "98765",
                "artifact_sha256": "b" * 64,
                "evidence_ref": "https://github.com/Nexora-Apparel/veltrix-football/actions/runs/98765/artifacts/456",
                "pagination_complete": True,
                "invalid_rows": 0, "duplicate_rows": 0, "missing_team_ids": 0,
                "review_attestation": {
                    "attestation_version": 1, "review_status": "qualified",
                    "repository": "Nexora-Apparel/veltrix-football",
                    "workflow_run_id": "98765",
                    "workflow_path": ".github/workflows/qualify-fivedollar-competitions.yml",
                    "event": "workflow_dispatch", "dispatch_ref": "main",
                    "dispatch_sha": "c" * 40, "head_branch": "main",
                    "checkout_ref": "phase-3/budget-aware-acquisition-contract",
                    "checkout_sha": "d" * 40,
                    "reviewer": "unit-test-reviewer", "reviewed_at": "2026-11-09T20:00:00Z",
                    "head_sha": "c" * 40, "artifact_id": 456,
                    "artifact_name": "fivedollar-competition-qualification",
                    "github_artifact_digest": "b" * 64,
                    "local_archive_sha256": "b" * 64,
                    "local_report_sha256": "d" * 64,
                    "coverage": {
                        "provider": "fivedollar", "competition_keys": ["39"], "competition_count": 1,
                        "source_rows": 100, "accepted_rows": 100,
                        "pagination_complete": True, "invalid_rows": 0, "duplicate_rows": 0,
                    },
                },
            }],
        }
        self.registry["sources"][0]["review_attestation"] = sign_attestation(
            self.registry["sources"][0]["review_attestation"], self.signing_key
        )

    def test_strikerapi_registry_policy_remains_supported(self):
        attestation = {
            "attestation_version": 1, "review_status": "qualified",
            "repository": "Nexora-Apparel/veltrix-football",
            "workflow_run_id": "777",
            "workflow_path": ".github/workflows/verify-strikerapi-17-competitions.yml",
            "event": "workflow_dispatch",
            "head_branch": "phase-3/strikerapi-readonly-qualification",
            "reviewer": "unit-test-reviewer", "reviewed_at": "2026-11-09T20:00:00Z",
            "head_sha": "c" * 40, "artifact_id": 789,
            "artifact_name": "strikerapi-17-competition-coverage",
            "github_artifact_digest": "e" * 64,
            "local_archive_sha256": "e" * 64,
            "local_report_sha256": "d" * 64,
            "coverage": {
                "provider": "strikerapi", "competition_keys": ["soccer"],
                "competition_count": 1, "final_rows_by_competition": {"soccer": 4},
                "pagination_complete": True, "invalid_rows": 0, "duplicate_rows": 0,
            },
        }
        registry = {
            "schema_version": 1,
            "sources": [{
                "provider": "strikerapi", "competition_key": "soccer",
                "qualification_status": "qualified", "qualification_run_id": "777",
                "artifact_sha256": "e" * 64,
                "evidence_ref": "https://github.com/Nexora-Apparel/veltrix-football/actions/runs/777/artifacts/789",
                "pagination_complete": True, "invalid_rows": 0,
                "duplicate_rows": 0, "missing_team_ids": 0,
                "review_attestation": sign_attestation(attestation, self.signing_key),
            }],
        }
        self.assertEqual(qualified_sources_from_registry(registry), {"strikerapi": ["soccer"]})

    def test_registry_rejects_self_declared_qualified_source_without_attestation(self):
        registry = copy.deepcopy(self.registry)
        del registry["sources"][0]["review_attestation"]
        with self.assertRaisesRegex(SelectionArtifactError, "reviewer_attestation_missing"):
            qualified_sources_from_registry(registry)

    def test_registry_rejects_attestation_for_different_competition(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["review_attestation"]["coverage"]["competition_keys"] = ["other"]
        registry["sources"][0]["review_attestation"] = sign_attestation(
            registry["sources"][0]["review_attestation"], self.signing_key
        )
        with self.assertRaisesRegex(SelectionArtifactError, "attestation_scope_invalid"):
            qualified_sources_from_registry(registry)

    def test_registry_rejects_mismatched_artifact_digest(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["review_attestation"]["github_artifact_digest"] = "e" * 64
        registry["sources"][0]["review_attestation"] = sign_attestation(
            registry["sources"][0]["review_attestation"], self.signing_key
        )
        with self.assertRaisesRegex(SelectionArtifactError, "artifact_hash_mismatch"):
            qualified_sources_from_registry(registry)

    def test_registry_rejects_forged_or_tampered_attestation_signature(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["review_attestation"]["head_sha"] = "f" * 40
        with self.assertRaisesRegex(SelectionArtifactError, "attestation_signature_invalid"):
            qualified_sources_from_registry(registry)


    def test_fivedollar_attestation_requires_distinct_dispatch_and_checkout_refs(self):
        registry = copy.deepcopy(self.registry)
        attestation = registry["sources"][0]["review_attestation"]
        attestation["checkout_ref"] = "main"
        registry["sources"][0]["review_attestation"] = sign_attestation(attestation, self.signing_key)
        with self.assertRaisesRegex(SelectionArtifactError, "attestation_ref_invalid"):
            qualified_sources_from_registry(registry)

    def test_fivedollar_attestation_requires_both_commit_shas(self):
        registry = copy.deepcopy(self.registry)
        attestation = registry["sources"][0]["review_attestation"]
        attestation.pop("checkout_sha")
        registry["sources"][0]["review_attestation"] = sign_attestation(attestation, self.signing_key)
        with self.assertRaisesRegex(SelectionArtifactError, "attestation_commit_invalid"):
            qualified_sources_from_registry(registry)

    def test_qualified_registry_builds_allowlist(self):
        self.assertEqual(qualified_sources_from_registry(self.registry),
                         {"fivedollar": ["39"]})

    def test_selection_artifact_uses_only_qualified_sources(self):
        artifact = build_daily_selection_artifact(
            acquisition_report=self.report,
            qualification_registry=self.registry,
            target_date="2026-11-10", as_of="2026-11-09T20:00:00Z",
        )
        self.assertEqual(artifact["selection"]["selected_count"], 1)
        self.assertEqual(artifact["source_acquisition_report_sha256"],
                         self.report["report_sha256"])
        self.assertEqual(len(artifact["selection_sha256"]), 64)
        self.assertTrue(validate_daily_selection_artifact(artifact)["valid"])

    def test_selection_artifact_tampering_is_detected(self):
        artifact = build_daily_selection_artifact(
            acquisition_report=self.report,
            qualification_registry=self.registry,
            target_date="2026-11-10", as_of="2026-11-09T20:00:00Z",
        )
        artifact["selection"]["selected_count"] = 0
        with self.assertRaisesRegex(SelectionArtifactError, "selection_artifact_hash_mismatch"):
            validate_daily_selection_artifact(artifact)

    def test_empty_template_registry_selects_nothing(self):
        artifact = build_daily_selection_artifact(
            acquisition_report=self.report,
            qualification_registry={
                "schema_version": 1,
                "registry_status": "unpopulated_template_not_qualification_evidence",
                "sources": [],
            },
            target_date="2026-11-10", as_of="2026-11-09T20:00:00Z",
        )
        self.assertEqual(artifact["selection"]["selected_count"], 0)
        self.assertEqual(
            artifact["selection"]["excluded_reasons"]["source_or_competition_not_qualified"],
            1,
        )

    def test_unqualified_source_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["qualification_status"] = "catalogued"
        with self.assertRaisesRegex(SelectionArtifactError, "source_not_qualified"):
            qualified_sources_from_registry(registry)

    def test_incomplete_pagination_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["pagination_complete"] = False
        with self.assertRaisesRegex(SelectionArtifactError, "pagination_incomplete"):
            qualified_sources_from_registry(registry)

    def test_nonzero_invalid_rows_are_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["invalid_rows"] = 1
        with self.assertRaisesRegex(SelectionArtifactError, "invalid_rows_nonzero"):
            qualified_sources_from_registry(registry)

    def test_nonzero_missing_team_ids_are_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["review_attestation"]["coverage"]["missing_team_ids"] = 1
        registry["sources"][0]["review_attestation"] = sign_attestation(
            registry["sources"][0]["review_attestation"], self.signing_key
        )
        with self.assertRaisesRegex(SelectionArtifactError, "attestation_scope_invalid"):
            qualified_sources_from_registry(registry)

    def test_nonzero_missing_team_ids_in_registry_entry_are_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["missing_team_ids"] = 1
        with self.assertRaisesRegex(SelectionArtifactError, "missing_team_ids_nonzero"):
            qualified_sources_from_registry(registry)

    def test_evidence_reference_must_bind_exact_artifact(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["evidence_ref"] = "https://github.com/Nexora-Apparel/veltrix-football"
        with self.assertRaisesRegex(SelectionArtifactError, "evidence_ref_invalid"):
            qualified_sources_from_registry(registry)

    def test_nonzero_duplicate_rows_are_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"][0]["duplicate_rows"] = 1
        with self.assertRaisesRegex(SelectionArtifactError, "duplicate_rows_nonzero"):
            qualified_sources_from_registry(registry)

    def test_duplicate_provider_competition_qualification_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["sources"].append(copy.deepcopy(registry["sources"][0]))
        with self.assertRaisesRegex(SelectionArtifactError, "duplicate_qualification_entry"):
            qualified_sources_from_registry(registry)

    def test_invalid_acquisition_report_is_rejected_before_selection(self):
        report = copy.deepcopy(self.report)
        report["records"][0]["home_team_name"] = "changed"
        with self.assertRaisesRegex(ValueError, "report_hash_mismatch"):
            build_daily_selection_artifact(
                acquisition_report=report, qualification_registry=self.registry,
                target_date="2026-11-10", as_of="2026-11-09T20:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
