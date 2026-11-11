import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from app.provider_acquisition_dataset_pipeline import (
    ProviderDatasetPipelineError,
    assemble_audited_provider_dataset,
)


def digest(value):
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class AuditedProviderDatasetPipelineTests(unittest.TestCase):
    def audit_report(self, accepted):
        report = {
            "schema_version": "veltrix-provider-acquisition-eligibility-audit-v1",
            "accepted_records": accepted,
            "rejected_records": [],
            "settlement_eligible_count": len(accepted),
            "rejected_count": 0,
            "model_training_started": False,
            "database_writes": 0,
            "prediction_publications": 0,
            "value_betting_enabled": False,
        }
        report["report_sha256"] = digest(report)
        return report

    def test_only_audit_admitted_original_records_reach_dataset_assembly(self):
        admitted = {"fixture_id": "provider:good", "provider": "provider", "source_id": "good"}
        records = [
            {"provider": "provider", "source_id": "good", "raw": "retained"},
            {"provider": "provider", "source_id": "bad", "raw": "must-not-pass"},
        ]
        packages = {"provider:good": {"evidence": "good"}}
        report = self.audit_report([admitted])
        assembled = {
            "dataset": {"dataset_sha256": "a" * 64},
            "quality": {"included_fixture_count": 1},
            "feature_reconstruction": {
                "target_fixture_count": 1, "snapshot_count": 1,
                "withheld_count": 0, "withheld_by_reason": {}, "withheld": [],
                "labels_without_admitted_targets": [],
            },
        }
        with patch(
            "app.provider_acquisition_dataset_pipeline.audit_provider_acquisition_eligibility",
            return_value=report,
        ), patch(
            "app.provider_acquisition_dataset_pipeline.assemble_provider_acquisition_dataset",
            return_value=assembled,
        ) as assemble:
            result = assemble_audited_provider_dataset(
                acquisition_records=records,
                settlement_timestamp_packages=packages,
                trusted_kms_clients={"trusted": object()},
                split_policy={"train": "a", "validation": "b", "test": "c"},
            )
        kwargs = assemble.call_args.kwargs
        self.assertEqual(kwargs["acquisition_records"], [records[0]])
        self.assertEqual(kwargs["settlement_timestamp_packages"], packages)
        self.assertTrue(result["dataset_assembled"])
        self.assertEqual(result["dataset_fixture_count"], 1)
        self.assertFalse(result["training_authorized"])
        self.assertFalse(result["publication_allowed"])
        self.assertEqual(len(result["pipeline_report_sha256"]), 64)
        self.assertEqual(result["admission_profile"]["dataset"]["included_rows"], 1)
        self.assertFalse(result["admission_profile"]["training_readiness"]["ready_for_model_training"])

    def test_tampered_audit_report_is_rejected(self):
        report = self.audit_report([])
        report["rejected_count"] = 99
        with patch(
            "app.provider_acquisition_dataset_pipeline.audit_provider_acquisition_eligibility",
            return_value=report,
        ):
            with self.assertRaisesRegex(ProviderDatasetPipelineError, "eligibility_audit_digest_invalid"):
                assemble_audited_provider_dataset(
                    acquisition_records=[],
                    settlement_timestamp_packages={},
                    trusted_kms_clients={},
                    split_policy={},
                )

    def test_no_admitted_records_returns_audited_empty_result_without_assembly(self):
        report = self.audit_report([])
        with patch(
            "app.provider_acquisition_dataset_pipeline.audit_provider_acquisition_eligibility",
            return_value=report,
        ), patch(
            "app.provider_acquisition_dataset_pipeline.assemble_provider_acquisition_dataset",
        ) as assemble:
            result = assemble_audited_provider_dataset(
                acquisition_records=[{"provider": "p", "source_id": "x"}],
                settlement_timestamp_packages={},
                trusted_kms_clients={},
                split_policy={},
            )
        assemble.assert_not_called()
        self.assertIsNone(result["dataset"])
        self.assertFalse(result["dataset_assembled"])
        self.assertEqual(result["dataset_fixture_count"], 0)
        self.assertFalse(result["training_authorized"])

    def test_audit_identity_cannot_be_used_to_select_different_source_record(self):
        report = self.audit_report([{
            "fixture_id": "provider:good", "provider": "provider", "source_id": "good",
        }])
        with patch(
            "app.provider_acquisition_dataset_pipeline.audit_provider_acquisition_eligibility",
            return_value=report,
        ):
            with self.assertRaisesRegex(
                ProviderDatasetPipelineError,
                "eligibility_audit_original_record_join_mismatch",
            ):
                assemble_audited_provider_dataset(
                    acquisition_records=[{"provider": "provider", "source_id": "other"}],
                    settlement_timestamp_packages={"provider:good": {}},
                    trusted_kms_clients={},
                    split_policy={},
                )


if __name__ == "__main__":
    unittest.main()
