import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from app.point_in_time_feature_contract import build_point_in_time_feature_snapshot
from app.provider_acquisition_dataset_pipeline import (
    ProviderDatasetPipelineError,
    assemble_audited_provider_dataset,
)
from app.canonical_team_crosswalk import (
    SCHEMA as TEAM_CROSSWALK_SCHEMA, canonical_sha256,
    sign_team_crosswalk_registry,
)
from app.feature_source_qualification import (
    SCHEMA as FEATURE_SOURCE_SCHEMA, sign_feature_source_qualification_registry,
    verify_feature_source_qualification_registry,
)

TEAM_KEY_ARN = "arn:aws:kms:eu-west-1:123456789012:key/team-pipeline-test"
class FakeTeamKms:
    def sign(self, **kwargs):
        return {"Signature": kwargs["Message"]}
    def verify(self, **kwargs):
        return {"SignatureValid": kwargs["Signature"] == kwargs["Message"]}

TEAM_KMS = FakeTeamKms()

def feature_source_registry():
    return sign_feature_source_qualification_registry(
        kms_client=TEAM_KMS, key_arn=TEAM_KEY_ARN,
        trusted_key_regions={TEAM_KEY_ARN: "eu-west-1"},
        registry={
            "schema": FEATURE_SOURCE_SCHEMA,
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "sources": [{
                "source": "test-source",
                "qualified_features": ["home_team_elo"],
                "supported_competitions": ["league-a"],
                "observed_at_semantics": "historical_match_kickoff",
                "available_at_semantics": "final_whistle_timestamp",
                "qualification_evidence_sha256": ["c" * 64],
                "reviewer": "feature-source-review",
                "qualified_at": "2026-01-01T00:00:00Z",
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
                "revoked_at": None,
            }],
        },
    )


def team_registry():
    mappings = []
    for source_id, canonical_id in (("home-src", "home-1"), ("away-src", "away-1")):
        mappings.append({
            "provider": "provider", "competition_id": "league-a",
            "source_team_id": source_id, "canonical_team_id": canonical_id,
            "team_scope": "men_first_team", "evidence_sha256": ["b" * 64],
            "reviewer": "identity-review", "reviewed_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-02T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z", "revoked_at": None,
        })
    unsigned = {
        "schema": TEAM_CROSSWALK_SCHEMA,
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2027-01-01T00:00:00Z", "mappings": mappings,
    }
    registry = sign_team_crosswalk_registry(
        kms_client=TEAM_KMS, key_arn=TEAM_KEY_ARN,
        trusted_key_regions={TEAM_KEY_ARN: "eu-west-1"}, registry=unsigned,
    )
    return registry, canonical_sha256(unsigned)



def make_snapshot(fixture_id, predictors):
    registry = feature_source_registry()
    verified = verify_feature_source_qualification_registry(
        registry=registry, trusted_kms_clients={TEAM_KEY_ARN: TEAM_KMS},
        as_of="2026-09-01T12:00:00Z",
    )
    return build_point_in_time_feature_snapshot(
        fixture_id=fixture_id,
        prediction_as_of="2026-09-01T12:00:00Z",
        verified_source_registry=verified,
        competition_id="league-a",
        features=[{
            "name": name, "value": value, "source": "test-source",
            "source_id": f"source-{fixture_id}-{name}",
            "observed_at": "2026-09-01T11:00:00Z",
            "available_at": "2026-09-01T11:15:00Z",
            "retrieved_at": "2026-09-01T11:30:00Z",
            "payload_sha256": "a" * 64,
        } for name, value in predictors.items()],
    )


def digest(value):
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class AuditedProviderDatasetPipelineTests(unittest.TestCase):
    def audit_report(self, accepted, input_count=None):
        report = {
            "schema_version": "veltrix-provider-acquisition-eligibility-audit-v1",
            "input_record_count": len(accepted) if input_count is None else input_count,
            "accepted_records": accepted,
            "rejected_records": [],
            "settlement_eligible_count": len(accepted),
            "rejected_count": (len(accepted) if input_count is None else input_count) - len(accepted),
            "model_training_started": False,
            "database_writes": 0,
            "prediction_publications": 0,
            "value_betting_enabled": False,
        }
        report["report_sha256"] = digest(report)
        return report

    def test_only_audit_admitted_original_records_reach_dataset_assembly(self):
        registry, registry_digest = team_registry()
        admitted = {"fixture_id": "provider:good", "provider": "provider", "source_id": "good",
                    "competition_id": "league-a", "home_team_id": "home-1",
                    "away_team_id": "away-1", "home_team_source_id": "home-src",
                    "away_team_source_id": "away-src",
                    "team_identity_evidence": {
                        "home_source_team_id": "home-src", "away_source_team_id": "away-src",
                        "home_canonical_team_id": "home-1", "away_canonical_team_id": "away-1",
                        "team_scope": "men_first_team", "registry_sha256": registry_digest,
                        "signing_key_arn": TEAM_KEY_ARN, "verified_at": "2026-09-01T12:00:00Z",
                    },
                    "kickoff_at": "2026-09-01T13:00:00Z",
                    "settled_at": "2026-09-01T14:00:00Z",
                    "settlement_source_id": "final-whistle"}
        records = [
            {"provider": "provider", "source_id": "good", "raw": "retained"},
            {"provider": "provider", "source_id": "bad", "raw": "must-not-pass"},
        ]
        packages = {"provider:good": {"evidence": "good"}}
        report = self.audit_report([admitted])
        predictors = {"home_team_elo": 1500}
        snapshot = make_snapshot("provider:good", predictors)
        assembled = {
            "dataset": {
                "dataset_sha256": "a" * 64,
                "rows": [{
                    "fixture_id": "provider:good", "competition_key": "league-a",
                    "split": "train", "predictors": predictors,
                    "feature_snapshot_sha256": snapshot["snapshot_sha256"],
                    "targets": {"1x2": "home", "btts": "yes", "over_2_5": "yes"},
                }],
                "quality": {"included_fixture_count": 1, "excluded_fixture_count": 0},
            },
            "feature_reconstruction": {
                "target_fixture_count": 1, "snapshot_count": 1, "snapshots": [snapshot],
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
                trusted_kms_clients={TEAM_KEY_ARN: TEAM_KMS},
                team_crosswalk_registry=team_registry()[0],

                team_crosswalk_as_of="2026-09-01T12:00:00Z",
                feature_source_qualification_registry=feature_source_registry(),

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
        self.assertIn("source_coverage", result)
        self.assertTrue(result["source_coverage"]["feature_source_qualification"]["verified"])
        self.assertEqual(
            result["source_coverage"]["feature_source_qualification"]["qualified_feature_cells"], 1
        )
        signed_features = feature_source_registry()
        expected_feature_registry_digest = digest({
            key: value for key, value in signed_features.items() if key != "signature"
        })
        self.assertEqual(
            result["source_coverage"]["feature_source_qualification"]["registry_sha256"],
            expected_feature_registry_digest,
        )
        self.assertFalse(result["source_coverage"]["qualification"]["source_coverage_qualified"])
        self.assertFalse(result["admission_profile"]["training_readiness"]["ready_for_model_training"])


    def test_rejects_dataset_quality_count_that_disagrees_with_actual_rows(self):
        admitted = {"fixture_id": "provider:good", "provider": "provider", "source_id": "good"}
        report = self.audit_report([admitted])
        predictors = {"home_team_elo": 1500}
        snapshot = make_snapshot("provider:good", predictors)
        assembled = {
            "dataset": {
                "rows": [{
                    "fixture_id": "provider:good", "competition_key": "league-a",
                    "split": "train", "predictors": predictors,
                    "feature_snapshot_sha256": snapshot["snapshot_sha256"],
                    "targets": {"1x2": "home", "btts": "yes", "over_2_5": "yes"},
                }],
                "quality": {"included_fixture_count": 0, "excluded_fixture_count": 0},
            },
            "feature_reconstruction": {
                "target_fixture_count": 1, "snapshot_count": 1, "snapshots": [snapshot],
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
        ):
            with self.assertRaisesRegex(
                ProviderDatasetPipelineError, "dataset_included_fixture_count_mismatch"
            ):
                assemble_audited_provider_dataset(
                    acquisition_records=[{"provider": "provider", "source_id": "good"}],
                    settlement_timestamp_packages={"provider:good": {}},
                    trusted_kms_clients={TEAM_KEY_ARN: TEAM_KMS},
                    team_crosswalk_registry=team_registry()[0],

                    team_crosswalk_as_of="2026-09-01T12:00:00Z",
                    feature_source_qualification_registry=feature_source_registry(),

                    split_policy={},
                )

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
                    trusted_kms_clients={TEAM_KEY_ARN: TEAM_KMS},
                    team_crosswalk_registry=team_registry()[0],

                    team_crosswalk_as_of="2026-09-01T12:00:00Z",
                    feature_source_qualification_registry=feature_source_registry(),

                    split_policy={},
                )

    def test_no_admitted_records_returns_audited_empty_result_without_assembly(self):
        report = self.audit_report([], input_count=1)
        with patch(
            "app.provider_acquisition_dataset_pipeline.audit_provider_acquisition_eligibility",
            return_value=report,
        ), patch(
            "app.provider_acquisition_dataset_pipeline.assemble_provider_acquisition_dataset",
        ) as assemble:
            result = assemble_audited_provider_dataset(
                acquisition_records=[{"provider": "p", "source_id": "x"}],
                settlement_timestamp_packages={},
                trusted_kms_clients={TEAM_KEY_ARN: TEAM_KMS},
                team_crosswalk_registry=team_registry()[0],

                team_crosswalk_as_of="2026-09-01T12:00:00Z",
                feature_source_qualification_registry=feature_source_registry(),

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
            "competition_id": "league-a", "home_team_id": "home-1",
            "away_team_id": "away-1", "kickoff_at": "2026-09-01T13:00:00Z",
            "settled_at": "2026-09-01T14:00:00Z", "settlement_source_id": "final-whistle",
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
                    trusted_kms_clients={TEAM_KEY_ARN: TEAM_KMS},
                    team_crosswalk_registry=team_registry()[0],

                    team_crosswalk_as_of="2026-09-01T12:00:00Z",
                    feature_source_qualification_registry=feature_source_registry(),

                    split_policy={},
                )


if __name__ == "__main__":
    unittest.main()
