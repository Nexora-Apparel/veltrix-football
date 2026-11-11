"""Audited orchestration boundary for provider-to-training dataset assembly.

Only records admitted by the signed settlement/provenance audit are passed to
the chronological feature adapter. Feature-reconstruction withholding remains
separate from settlement eligibility. This module never trains or publishes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.provider_acquisition_eligibility_audit import (
    audit_provider_acquisition_eligibility,
)
from app.historical_dataset_admission_report import build_historical_dataset_admission_report
from app.historical_source_coverage import build_historical_source_coverage_report
from app.provider_acquisition_dataset_bridge import (
    AcquisitionDatasetBridgeError,
    assemble_provider_acquisition_dataset,
)


class ProviderDatasetPipelineError(ValueError):
    pass


def _canonical_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ProviderDatasetPipelineError("pipeline_report_not_canonical_json") from None
    return hashlib.sha256(payload).hexdigest()


def _finalize_report(
    result: dict,
    *,
    trusted_kms_clients: dict,
    season_crosswalk_registry: dict | None = None,
    season_crosswalk_as_of: str | None = None,
    team_crosswalk_registry: dict | None = None,
    team_crosswalk_as_of: str | None = None,
) -> dict:
    result["admission_profile"] = build_historical_dataset_admission_report(result)
    result["source_coverage"] = build_historical_source_coverage_report(
        result,
        season_crosswalk_registry=season_crosswalk_registry,
        trusted_kms_clients=(
            trusted_kms_clients
            if season_crosswalk_registry is not None or team_crosswalk_registry is not None
            else None
        ),
        season_crosswalk_as_of=season_crosswalk_as_of,
        team_crosswalk_registry=team_crosswalk_registry,
        team_crosswalk_as_of=team_crosswalk_as_of,
    )
    result["pipeline_report_sha256"] = _canonical_sha256(result)
    return result


def assemble_audited_provider_dataset(
    *,
    acquisition_records: list[dict],
    settlement_timestamp_packages: dict,
    trusted_kms_clients: dict,
    split_policy: dict,
    cutoff_hours: int = 6,
    form_window: int = 10,
    minimum_team_matches: int = 3,
    season_crosswalk_registry: dict | None = None,
    season_crosswalk_as_of: str | None = None,
    team_crosswalk_registry: dict | None = None,
    team_crosswalk_as_of: str | None = None,
) -> dict:
    """Audit all records, then assemble features from admitted originals only."""
    if not isinstance(team_crosswalk_registry, dict):
        raise ProviderDatasetPipelineError("team_crosswalk_registry_required")
    if not isinstance(team_crosswalk_as_of, str) or not team_crosswalk_as_of:
        raise ProviderDatasetPipelineError("team_crosswalk_as_of_required")
    audit = audit_provider_acquisition_eligibility(
        acquisition_records=acquisition_records,
        settlement_timestamp_packages=settlement_timestamp_packages,
        trusted_kms_clients=trusted_kms_clients,
        team_crosswalk_registry=team_crosswalk_registry,
    )
    unsigned_audit = dict(audit)
    supplied_digest = unsigned_audit.pop("report_sha256", None)
    if (not isinstance(supplied_digest, str)
            or supplied_digest != _canonical_sha256(unsigned_audit)):
        raise ProviderDatasetPipelineError("eligibility_audit_digest_invalid")

    accepted = audit.get("accepted_records")
    if not isinstance(accepted, list):
        raise ProviderDatasetPipelineError("eligibility_audit_accepted_records_invalid")

    admitted_ids = set()
    for item in accepted:
        if not isinstance(item, dict):
            raise ProviderDatasetPipelineError("eligibility_audit_entry_invalid")
        provider, source_id = item.get("provider"), item.get("source_id")
        fixture_id = item.get("fixture_id")
        if (not isinstance(provider, str) or not provider
                or not isinstance(source_id, str) or not source_id
                or fixture_id != f"{provider}:{source_id}"
                or fixture_id in admitted_ids):
            raise ProviderDatasetPipelineError("eligibility_audit_identity_invalid")
        admitted_ids.add(fixture_id)

    selected_records = []
    selected_packages = {}
    for record in acquisition_records:
        if not isinstance(record, dict):
            continue
        fixture_id = f'{record.get("provider")}:{record.get("source_id")}'
        if fixture_id in admitted_ids:
            selected_records.append(record)
            selected_packages[fixture_id] = settlement_timestamp_packages[fixture_id]

    if len(selected_records) != len(admitted_ids):
        raise ProviderDatasetPipelineError("eligibility_audit_original_record_join_mismatch")

    if not selected_records:
        result = {
            "dataset": None,
            "dataset_assembled": False,
            "dataset_fixture_count": 0,
            "feature_snapshot_count": 0,
            "acquisition_eligibility": audit,
            "feature_reconstruction": {
                "target_fixture_count": 0,
                "snapshot_count": 0,
                "snapshots": [],
                "withheld_count": 0,
                "withheld_by_reason": {},
                "withheld": [],
                "labels_without_admitted_targets": [],
                "model_training_started": False,
                "database_writes": 0,
                "prediction_publications": 0,
            },
            "historical_availability_proven": False,
            "training_authorized": False,
            "value_betting_enabled": False,
            "publication_allowed": False,
        }
        return _finalize_report(
            result, trusted_kms_clients=trusted_kms_clients,
            season_crosswalk_registry=season_crosswalk_registry,
            season_crosswalk_as_of=season_crosswalk_as_of,
            team_crosswalk_registry=team_crosswalk_registry,
            team_crosswalk_as_of=team_crosswalk_as_of,
        )

    try:
        assembled = assemble_provider_acquisition_dataset(
            acquisition_records=selected_records,
            settlement_timestamp_packages=selected_packages,
            trusted_kms_clients=trusted_kms_clients,
            team_crosswalk_registry=team_crosswalk_registry,
            split_policy=split_policy,
            cutoff_hours=cutoff_hours,
            form_window=form_window,
            minimum_team_matches=minimum_team_matches,
        )
    except AcquisitionDatasetBridgeError as exc:
        raise ProviderDatasetPipelineError(f"admitted_dataset_assembly_failed:{exc}") from None

    dataset = assembled.get("dataset")
    reconstruction = assembled.get("feature_reconstruction")
    if not isinstance(dataset, dict) or not isinstance(reconstruction, dict):
        raise ProviderDatasetPipelineError("dataset_assembly_contract_invalid")
    rows = dataset.get("rows")
    quality = dataset.get("quality")
    if not isinstance(rows, list) or not isinstance(quality, dict):
        raise ProviderDatasetPipelineError("dataset_rows_or_quality_invalid")
    included_count = quality.get("included_fixture_count")
    snapshot_count = reconstruction.get("snapshot_count")
    if (isinstance(included_count, bool) or not isinstance(included_count, int)
            or included_count < 0 or included_count != len(rows)):
        raise ProviderDatasetPipelineError("dataset_included_fixture_count_mismatch")
    if (isinstance(snapshot_count, bool) or not isinstance(snapshot_count, int)
            or snapshot_count < 0):
        raise ProviderDatasetPipelineError("feature_snapshot_count_invalid")

    result = {
        **assembled,
        "dataset_assembled": included_count > 0,
        "dataset_fixture_count": included_count,
        "feature_snapshot_count": snapshot_count,
        "acquisition_eligibility": audit,
        "feature_reconstruction": reconstruction,
        "historical_availability_proven": assembled.get("historical_availability_proven") is True,
        "training_authorized": False,
        "value_betting_enabled": False,
        "publication_allowed": False,
    }
    return _finalize_report(
        result, trusted_kms_clients=trusted_kms_clients,
        season_crosswalk_registry=season_crosswalk_registry,
        season_crosswalk_as_of=season_crosswalk_as_of,
        team_crosswalk_registry=team_crosswalk_registry,
        team_crosswalk_as_of=team_crosswalk_as_of,
    )
