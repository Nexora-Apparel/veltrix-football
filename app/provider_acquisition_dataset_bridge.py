"""Bridge verified acquisition records into the chronological history dataset.

This is deliberately fail-closed: provider terminal status alone is not a
settlement timestamp. Records without an independently supplied settlement
timestamp cannot become historical labels or feature-history rows.
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
    SettlementEvidenceError, validate_settlement_evidence,
)
from app.results_training_dataset_adapter import (
    ResultsTrainingAdapterError, assemble_results_history_dataset,
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


def acquisition_record_to_history_row(record: Any) -> dict:
    if not isinstance(record, dict):
        raise AcquisitionDatasetBridgeError("acquisition_record_invalid")
    evidence = record.get("source_evidence")
    try:
        validate_source_evidence(evidence, expected_record={
            key: value for key, value in record.items() if key != "source_evidence"
        })
        settlement = validate_settlement_evidence(
            record.get("settlement_evidence"), provider=record.get("provider"),
            payload=evidence["raw_payload"],
        )
    except (SourceEvidenceError, SettlementEvidenceError, KeyError, TypeError) as exc:
        raise AcquisitionDatasetBridgeError(str(exc)) from None
    settled_at = record.get("settled_at")
    if not settlement.get("settlement_time_available") or not settled_at:
        raise AcquisitionDatasetBridgeError("settlement_timestamp_unavailable")
    settled_at = _timestamp(settled_at, "settled_at")
    retrieved_at = _timestamp(record.get("retrieved_at"), "retrieved_at")
    if datetime.fromisoformat(retrieved_at.replace("Z", "+00:00")) < datetime.fromisoformat(settled_at.replace("Z", "+00:00")):
        raise AcquisitionDatasetBridgeError("retrieval_precedes_settlement")
    fixture_id = f'{record["provider"]}:{record["source_id"]}'
    normalized = {
        "fixture_id": fixture_id,
        "competition_id": record["competition_key"],
        "kickoff_at": record["kickoff_at"],
        "settled_at": settled_at,
        "home_team_id": record["home_team_source_id"],
        "away_team_id": record["away_team_source_id"],
        "home_score": record["home_score"],
        "away_score": record["away_score"],
        "normalized_status": record["normalized_status"],
    }
    payload = evidence["raw_payload"]
    normalized_hash = _canonical_hash(normalized)
    source_payload = {
        "provider": record["provider"],
        "endpoint": record["endpoint"],
        "source_id": record["source_id"],
        "run_id": record["run_id"],
        "retrieved_at": retrieved_at,
        "payload": payload,
        "payload_sha256": evidence["raw_payload_sha256"],
        "normalized_record": normalized,
        "normalized_record_sha256": normalized_hash,
    }
    return {
        **normalized,
        "provider": record["provider"],
        "source_id": record["source_id"],
        "endpoint": record["endpoint"],
        "retrieved_at": retrieved_at,
        "payload_sha256": evidence["raw_payload_sha256"],
        "run_id": record["run_id"],
        "source_payload": source_payload,
    }


def assemble_provider_acquisition_dataset(*, acquisition_records: list[dict],
                                          split_policy: dict,
                                          cutoff_hours: int = 6,
                                          form_window: int = 10,
                                          minimum_team_matches: int = 3) -> dict:
    if not isinstance(acquisition_records, list) or not acquisition_records:
        raise AcquisitionDatasetBridgeError("acquisition_records_required")
    history = [acquisition_record_to_history_row(row) for row in acquisition_records]
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
        })
    try:
        assembled = assemble_results_history_dataset(
            historical_matches=history,
            target_fixtures=targets,
            settled_labels=labels,
            split_policy=split_policy,
            cutoff_hours=cutoff_hours,
            form_window=form_window,
            minimum_team_matches=minimum_team_matches,
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
    }
