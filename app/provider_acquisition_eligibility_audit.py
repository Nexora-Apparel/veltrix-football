"""Fail-closed per-record eligibility audit for acquired provider history.

The audit verifies each record through the existing acquisition-to-dataset bridge,
then emits a sanitized report of settlement-eligible and rejected fixtures. It
never trains models, writes a database, or publishes predictions.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from app.provider_acquisition_dataset_bridge import (
    AcquisitionDatasetBridgeError,
    acquisition_record_to_history_row,
)


SCHEMA_VERSION = "veltrix-provider-acquisition-eligibility-audit-v1"


class AcquisitionEligibilityAuditError(ValueError):
    pass


def _digest(value: Any) -> str:
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise AcquisitionEligibilityAuditError("audit_report_not_canonical_json") from None
    return hashlib.sha256(raw).hexdigest()


def _record_identity(record: Any, index: int) -> tuple[str, str, str] | None:
    if not isinstance(record, dict):
        return None
    provider = record.get("provider")
    source_id = record.get("source_id")
    if (not isinstance(provider, str) or not provider.strip()
            or not isinstance(source_id, str) or not source_id.strip()):
        return None
    return provider, source_id, f"{provider}:{source_id}"


def audit_provider_acquisition_eligibility(
    *,
    acquisition_records: list[dict],
    settlement_timestamp_packages: dict,
    trusted_kms_clients: dict,
    team_crosswalk_registry: dict,
) -> dict:
    """Audit all records independently and report every admission decision.

    Duplicate provider/source identities are rejected for every occurrence;
    the audit never chooses an arbitrary winner. The returned report contains
    identifiers and digests only, never raw provider payloads.
    """
    if not isinstance(acquisition_records, list):
        raise AcquisitionEligibilityAuditError("acquisition_records_must_be_list")
    if not isinstance(settlement_timestamp_packages, dict):
        raise AcquisitionEligibilityAuditError("settlement_timestamp_packages_must_be_dict")
    if not isinstance(trusted_kms_clients, dict):
        raise AcquisitionEligibilityAuditError("trusted_kms_clients_must_be_dict")

    identities = [
        _record_identity(record, index)
        for index, record in enumerate(acquisition_records)
    ]
    identity_counts = Counter(
        identity[2] for identity in identities if identity is not None
    )

    accepted = []
    rejected = []
    matched_package_ids = set()

    for index, record in enumerate(acquisition_records):
        identity = identities[index]
        if identity is None:
            rejected_item = {
                "fixture_id": f"record-index-{index}",
                "reason": "acquisition_record_identity_invalid",
            }
            if isinstance(record, dict):
                provider = record.get("provider")
                source_id = record.get("source_id")
                if isinstance(provider, str) and provider.strip():
                    rejected_item["provider"] = provider
                if isinstance(source_id, str) and source_id.strip():
                    rejected_item["source_id"] = source_id
            rejected.append(rejected_item)
            continue

        provider, source_id, fixture_id = identity
        if identity_counts[fixture_id] > 1:
            rejected.append({
                "fixture_id": fixture_id,
                "provider": provider,
                "source_id": source_id,
                "reason": "duplicate_provider_source_identity",
            })
            continue

        package = settlement_timestamp_packages.get(fixture_id)
        if package is None:
            rejected.append({
                "fixture_id": fixture_id,
                "provider": provider,
                "source_id": source_id,
                "reason": "settlement_timestamp_unavailable",
            })
            continue

        matched_package_ids.add(fixture_id)
        try:
            row = acquisition_record_to_history_row(
                record,
                settlement_timestamp_package=package,
                trusted_kms_clients=trusted_kms_clients,
                team_crosswalk_registry=team_crosswalk_registry,
            )
        except AcquisitionDatasetBridgeError as exc:
            rejected.append({
                "fixture_id": fixture_id,
                "provider": provider,
                "source_id": source_id,
                "reason": str(exc)[:200],
            })
            continue

        accepted.append({
            "fixture_id": row["fixture_id"],
            "provider": provider,
            "source_id": source_id,
            "competition_id": row["competition_id"],
            "source_season": record.get("season"),
            "home_team_id": row["home_team_id"],
            "away_team_id": row["away_team_id"],
            "home_team_source_id": row["home_team_source_id"],
            "away_team_source_id": row["away_team_source_id"],
            "team_identity_evidence": row["team_identity_evidence"],
            "kickoff_at": row["kickoff_at"],
            "settled_at": row["settled_at"],
            "retrieved_at": row["retrieved_at"],
            "payload_sha256": row["payload_sha256"],
            "settlement_source_id": row["settlement_source_id"],
            "settlement_qualification_digest": row["settlement_qualification_digest"],
            "settlement_evidence_sha256": row["settlement_evidence_sha256"],
            "settlement_registry_sha256": row["settlement_registry_sha256"],
        })

    accepted.sort(key=lambda item: item["fixture_id"])
    rejected.sort(key=lambda item: (item["fixture_id"], item["reason"]))
    rejected_by_reason = Counter(item["reason"].split(":", 1)[0] for item in rejected)
    input_fixture_ids = {
        identity[2] for identity in identities if identity is not None
    }
    unmatched_packages = sorted(set(settlement_timestamp_packages) - input_fixture_ids)

    report = {
        "schema_version": SCHEMA_VERSION,
        "input_record_count": len(acquisition_records),
        "settlement_eligible_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_records": accepted,
        "rejected_records": rejected,
        "rejected_by_reason": dict(sorted(rejected_by_reason.items())),
        "unmatched_settlement_package_ids": unmatched_packages,
        "model_training_started": False,
        "database_writes": 0,
        "prediction_publications": 0,
        "value_betting_enabled": False,
    }
    report["report_sha256"] = _digest(report)
    return report
