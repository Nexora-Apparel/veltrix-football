"""Bridge verified acquisition records into the chronological history dataset.

Provider terminal status and independently qualified final-whistle evidence
are separate facts. This bridge joins them only through an explicit reviewed
fixture identity mapping. It never infers settlement time from provider status.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from app.provider_source_evidence import (
    SourceEvidenceError, validate_source_evidence,
)
from app.provider_settlement_evidence import (
    extract_settlement_evidence, SettlementEvidenceError,
)
from app.settlement_timestamp_source import (
    SettlementTimestampSourceError,
    validate_settlement_timestamp_evidence,
)
from app.results_training_dataset_adapter import (
    ResultsTrainingAdapterError, assemble_results_history_dataset,
)
from app.source_qualification_registry import (
    SourceQualificationRegistryError, resolve_qualified_settlement_source,
)
from app.canonical_team_crosswalk import (
    TeamCrosswalkError, resolve_canonical_team_pair,
)


class AcquisitionDatasetBridgeError(ValueError):
    pass


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AcquisitionDatasetBridgeError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AcquisitionDatasetBridgeError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AcquisitionDatasetBridgeError(f"{field}_timezone_missing")
    return parsed.isoformat().replace("+00:00", "Z")


def _qualified_settlement(record: dict, package: Any, *,
                          trusted_kms_clients: dict) -> dict:
    if not isinstance(package, dict) or set(package) != {
        "source_contract", "qualification_registry",
        "raw_payload", "fixture_identity", "expected_fixture_identity", "evidence",
    }:
        raise AcquisitionDatasetBridgeError("qualified_settlement_package_invalid")
    provider_payload = record.get("source_evidence", {}).get("raw_payload")
    try:
        provider_status = extract_settlement_evidence(record.get("provider"), provider_payload)
        if record.get("settlement_evidence") != provider_status:
            raise AcquisitionDatasetBridgeError("provider_terminal_status_evidence_mismatch")
        if provider_status.get("terminal_status_confirmed") is not True:
            raise AcquisitionDatasetBridgeError("provider_terminal_status_not_confirmed")
        qualification = resolve_qualified_settlement_source(
            registry=package["qualification_registry"],
            source_id=package["source_contract"].get("source_id"),
            competition_id=record.get("competition_key"),
            trusted_kms_clients=trusted_kms_clients,
            as_of=record.get("retrieved_at"),
        )
        if qualification["contract"] != package["source_contract"]:
            raise AcquisitionDatasetBridgeError("settlement_source_contract_not_registry_bound")
        expected_identity = package["expected_fixture_identity"]
        if not isinstance(expected_identity, dict) or {
            "competition_id": record.get("competition_key"),
            "home_team_id": record.get("home_team_source_id"),
            "away_team_id": record.get("away_team_source_id"),
            "kickoff_at": record.get("kickoff_at"),
        } != {key: expected_identity.get(key) for key in (
            "competition_id", "home_team_id", "away_team_id", "kickoff_at",
        )}:
            raise AcquisitionDatasetBridgeError("settlement_fixture_mapping_not_bound_to_provider_record")
        verified = validate_settlement_timestamp_evidence(
            package["evidence"],
            source_contract=qualification["contract"],
            raw_payload=package["raw_payload"],
            fixture_identity=package["fixture_identity"],
            expected_fixture_identity=package["expected_fixture_identity"],
            kickoff_at=record.get("kickoff_at"),
        )
    except SourceQualificationRegistryError as exc:
        raise AcquisitionDatasetBridgeError(f"settlement_source_registry_rejected:{exc}") from None
    except SettlementTimestampSourceError as exc:
        raise AcquisitionDatasetBridgeError(f"qualified_settlement_rejected:{exc}") from None
    except (KeyError, TypeError, SettlementEvidenceError) as exc:
        raise AcquisitionDatasetBridgeError(f"provider_settlement_evidence_invalid:{exc}") from None

    settled_at = _timestamp(verified["settlement_at"], "settled_at")
    retrieved_at = _timestamp(record.get("retrieved_at"), "retrieved_at")
    if datetime.fromisoformat(retrieved_at.replace("Z", "+00:00")) < datetime.fromisoformat(settled_at.replace("Z", "+00:00")):
        raise AcquisitionDatasetBridgeError("provider_retrieval_precedes_settlement")
    return {
        "settled_at": settled_at,
        "settlement_source_id": verified["source_id"],
        "settlement_qualification_digest": qualification["contract"]["qualification_digest"],
        "settlement_evidence_sha256": verified["evidence_sha256"],
        "settlement_registry_sha256": qualification["registry_sha256"],
        "settlement_registry_signing_key_arn": qualification["signing_key_arn"],
    }


def acquisition_record_to_history_row(record: Any, *,
                                       settlement_timestamp_package: dict | None = None,
                                       trusted_kms_clients: dict | None = None,
                                       team_crosswalk_registry: dict | None = None) -> dict:
    if not isinstance(record, dict):
        raise AcquisitionDatasetBridgeError("acquisition_record_invalid")
    evidence = record.get("source_evidence")
    try:
        validate_source_evidence(evidence, expected_record={
            key: value for key, value in record.items() if key != "source_evidence"
        })
    except (SourceEvidenceError, KeyError, TypeError) as exc:
        raise AcquisitionDatasetBridgeError(str(exc)) from None

    if settlement_timestamp_package is None:
        raise AcquisitionDatasetBridgeError("settlement_timestamp_unavailable")
    if not isinstance(trusted_kms_clients, dict) or not trusted_kms_clients:
        raise AcquisitionDatasetBridgeError("trusted_settlement_registry_keys_required")
    if not isinstance(team_crosswalk_registry, dict):
        raise AcquisitionDatasetBridgeError("team_crosswalk_registry_required")
    try:
        team_identity = resolve_canonical_team_pair(
            registry=team_crosswalk_registry,
            trusted_kms_clients=trusted_kms_clients,
            provider=record["provider"],
            competition_id=record["competition_key"],
            home_source_team_id=record["home_team_source_id"],
            away_source_team_id=record["away_team_source_id"],
            as_of=record["retrieved_at"],
        )
    except TeamCrosswalkError as exc:
        raise AcquisitionDatasetBridgeError(
            f"canonical_team_pair_rejected:{exc}"
        ) from None

    settlement = _qualified_settlement(
        record, settlement_timestamp_package,
        trusted_kms_clients=trusted_kms_clients,
    )
    fixture_id = f'{record["provider"]}:{record["source_id"]}'
    # The source-normalized record deliberately retains provider IDs. Canonical
    # identity is a separate signed evidence layer and never rewrites raw evidence.
    source_normalized = {
        "fixture_id": fixture_id,
        "competition_id": record["competition_key"],
        "kickoff_at": record["kickoff_at"],
        "settled_at": settlement["settled_at"],
        "home_team_id": record["home_team_source_id"],
        "away_team_id": record["away_team_source_id"],
        "home_score": record["home_score"],
        "away_score": record["away_score"],
        "normalized_status": record["normalized_status"],
    }
    identity_evidence = {
        "home_source_team_id": record["home_team_source_id"],
        "away_source_team_id": record["away_team_source_id"],
        "home_canonical_team_id": team_identity["home"]["canonical_team_id"],
        "away_canonical_team_id": team_identity["away"]["canonical_team_id"],
        "team_scope": team_identity["home"]["team_scope"],
        "registry_sha256": team_identity["registry_sha256"],
        "signing_key_arn": team_identity["signing_key_arn"],
        "verified_at": team_identity["verified_at"],
    }
    normalized = {
        **source_normalized,
        "home_team_id": identity_evidence["home_canonical_team_id"],
        "away_team_id": identity_evidence["away_canonical_team_id"],
    }
    source_payload = {
        "provider": record["provider"],
        "endpoint": record["endpoint"],
        "source_id": record["source_id"],
        "run_id": record["run_id"],
        "retrieved_at": _timestamp(record["retrieved_at"], "retrieved_at"),
        "payload": evidence["raw_payload"],
        "payload_sha256": evidence["raw_payload_sha256"],
        "normalized_record": source_normalized,
        "normalized_record_sha256": _canonical_hash(source_normalized),
    }
    return {
        **normalized,
        "provider": record["provider"],
        "source_id": record["source_id"],
        "endpoint": record["endpoint"],
        "retrieved_at": source_payload["retrieved_at"],
        "payload_sha256": evidence["raw_payload_sha256"],
        "run_id": record["run_id"],
        "source_payload": source_payload,
        "home_team_source_id": identity_evidence["home_source_team_id"],
        "away_team_source_id": identity_evidence["away_source_team_id"],
        "team_identity_evidence": identity_evidence,
        **settlement,
    }


def assemble_provider_acquisition_dataset(*, acquisition_records: list[dict],
                                          settlement_timestamp_packages: dict,
                                          trusted_kms_clients: dict,
                                          team_crosswalk_registry: dict,
                                          split_policy: dict,
                                          cutoff_hours: int = 6,
                                          form_window: int = 10,
                                          minimum_team_matches: int = 3,
                                          feature_source_qualification_registry: dict | None = None) -> dict:
    if not isinstance(acquisition_records, list) or not acquisition_records:
        raise AcquisitionDatasetBridgeError("acquisition_records_required")
    if not isinstance(settlement_timestamp_packages, dict):
        raise AcquisitionDatasetBridgeError("settlement_timestamp_packages_required")
    history = []
    for record in acquisition_records:
        fixture_id = f'{record.get("provider")}:{record.get("source_id")}' if isinstance(record, dict) else None
        package = settlement_timestamp_packages.get(fixture_id)
        history.append(acquisition_record_to_history_row(
            record, settlement_timestamp_package=package,
            trusted_kms_clients=trusted_kms_clients,
            team_crosswalk_registry=team_crosswalk_registry,
        ))

    targets, labels, manifest = [], [], []
    for row in history:
        targets.append({
            "fixture_id": row["fixture_id"],
            "competition_id": row["competition_id"],
            "kickoff_at": row["kickoff_at"],
            "home_team_id": row["home_team_id"],
            "away_team_id": row["away_team_id"],
        })
        labels.append({
            "fixture_id": row["fixture_id"],
            "competition_key": row["competition_id"],
            "kickoff_at": row["kickoff_at"],
            "settled_at": row["settled_at"],
            "home_score": row["home_score"],
            "away_score": row["away_score"],
            "label_source": row["provider"],
            "label_source_id": row["source_id"],
            "label_retrieved_at": row["retrieved_at"],
            "payload_sha256": row["payload_sha256"],
        })
        manifest.append({
            "fixture_id": row["fixture_id"],
            "provider": row["provider"],
            "source_id": row["source_id"],
            "run_id": row["run_id"],
            "payload_sha256": row["payload_sha256"],
            "settled_at": row["settled_at"],
            "settlement_source_id": row["settlement_source_id"],
            "settlement_qualification_digest": row["settlement_qualification_digest"],
            "settlement_evidence_sha256": row["settlement_evidence_sha256"],
            "settlement_registry_sha256": row["settlement_registry_sha256"],
            "settlement_registry_signing_key_arn": row["settlement_registry_signing_key_arn"],
            "team_identity_evidence": row["team_identity_evidence"],
        })
    feature_history = [
        {key: value for key, value in row.items() if key not in {
            "settlement_source_id", "settlement_qualification_digest",
            "settlement_evidence_sha256", "settlement_registry_sha256",
            "settlement_registry_signing_key_arn",
        }}
        for row in history
    ]
    try:
        assembled = assemble_results_history_dataset(
            historical_matches=feature_history,
            target_fixtures=targets,
            settled_labels=labels,
            split_policy=split_policy,
            cutoff_hours=cutoff_hours,
            form_window=form_window,
            minimum_team_matches=minimum_team_matches,
            feature_source_qualification_registry=feature_source_qualification_registry,
            trusted_kms_clients=trusted_kms_clients,
            team_crosswalk_registry=team_crosswalk_registry,
        )
    except (ResultsTrainingAdapterError, ValueError, KeyError) as exc:
        raise AcquisitionDatasetBridgeError(str(exc)) from None
    dataset = assembled["dataset"]
    dataset["source_evidence_manifest"] = manifest
    dataset["source_evidence_manifest_sha256"] = _canonical_hash(manifest)
    unhashed = dict(dataset)
    unhashed.pop("dataset_sha256", None)
    dataset["dataset_sha256"] = _canonical_hash(unhashed)
    return {
        **assembled,
        "dataset": dataset,
        "source_evidence_manifest_sha256": dataset["source_evidence_manifest_sha256"],
        "acquisition_record_count": len(acquisition_records),
        "settlement_timestamp_eligible_count": len(history),
        "historical_availability_proven": False,
        "model_training_started": False,
    }
