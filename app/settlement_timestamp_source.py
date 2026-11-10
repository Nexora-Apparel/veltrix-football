"""Qualified external wall-clock settlement timestamp evidence.

This adapter accepts only a source contract that has already been admitted by
an independently verified qualification registry. It verifies payload
integrity, fixture identity, timestamp semantics and chronology. A SHA-256
digest proves byte-level integrity, not source authenticity or truth.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

SCHEMA_VERSION = 1
ALLOWED_SEMANTICS = {"final_whistle"}
_HEX = re.compile(r"^[0-9a-f]{64}$")


class SettlementTimestampSourceError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise SettlementTimestampSourceError("payload_not_canonical_json") from None
    return hashlib.sha256(raw).hexdigest()


def _aware_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SettlementTimestampSourceError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SettlementTimestampSourceError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SettlementTimestampSourceError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _path_value(payload: dict, path: str) -> Any:
    if not isinstance(path, str) or not path or path.startswith(".") or path.endswith("."):
        raise SettlementTimestampSourceError("timestamp_field_path_invalid")
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SettlementTimestampSourceError("timestamp_field_missing")
        value = value[part]
    return value


def _validate_contract(contract: Any) -> dict:
    if not isinstance(contract, dict):
        raise SettlementTimestampSourceError("source_contract_invalid")
    required = {
        "source_id", "qualification_status", "qualification_digest",
        "timestamp_field", "timestamp_semantics", "supported_competitions",
    }
    if set(contract) != required:
        raise SettlementTimestampSourceError("source_contract_shape_invalid")
    if not isinstance(contract["source_id"], str) or not contract["source_id"].strip():
        raise SettlementTimestampSourceError("source_id_invalid")
    if contract["qualification_status"] != "qualified":
        raise SettlementTimestampSourceError("timestamp_source_not_qualified")
    if not isinstance(contract["qualification_digest"], str) or not _HEX.fullmatch(contract["qualification_digest"]):
        raise SettlementTimestampSourceError("qualification_digest_invalid")
    if contract["timestamp_semantics"] not in ALLOWED_SEMANTICS:
        raise SettlementTimestampSourceError("timestamp_semantics_unsupported")
    if not isinstance(contract["timestamp_field"], str) or not contract["timestamp_field"]:
        raise SettlementTimestampSourceError("timestamp_field_invalid")
    competitions = contract["supported_competitions"]
    if not isinstance(competitions, list) or not competitions or any(
        not isinstance(item, str) or not item.strip() for item in competitions
    ) or len(set(competitions)) != len(competitions):
        raise SettlementTimestampSourceError("supported_competitions_invalid")
    return contract


def build_settlement_timestamp_evidence(
    *, source_contract: dict, raw_payload: dict, fixture_identity: dict,
    expected_fixture_identity: dict, kickoff_at: str, observed_at: str,
    retrieved_at: str,
) -> dict:
    contract = _validate_contract(source_contract)
    if not isinstance(raw_payload, dict):
        raise SettlementTimestampSourceError("raw_payload_invalid")
    identity_fields = ("source_fixture_id", "competition_id", "home_team_id",
                       "away_team_id", "kickoff_at")
    if not isinstance(fixture_identity, dict) or set(fixture_identity) != set(identity_fields):
        raise SettlementTimestampSourceError("source_fixture_identity_invalid")
    if not isinstance(expected_fixture_identity, dict) or set(expected_fixture_identity) != set(identity_fields):
        raise SettlementTimestampSourceError("expected_fixture_identity_invalid")
    if fixture_identity != expected_fixture_identity:
        raise SettlementTimestampSourceError("fixture_identity_mismatch")
    if fixture_identity["competition_id"] not in contract["supported_competitions"]:
        raise SettlementTimestampSourceError("competition_not_qualified_for_timestamp_source")
    for field in identity_fields:
        if not isinstance(fixture_identity[field], str) or not fixture_identity[field].strip():
            raise SettlementTimestampSourceError(f"fixture_identity_{field}_invalid")
    kickoff = _aware_timestamp(kickoff_at, "kickoff_at")
    if _aware_timestamp(fixture_identity["kickoff_at"], "identity_kickoff_at") != kickoff:
        raise SettlementTimestampSourceError("fixture_identity_kickoff_mismatch")
    settled = _aware_timestamp(_path_value(raw_payload, contract["timestamp_field"]), "settlement_at")
    observed = _aware_timestamp(observed_at, "observed_at")
    retrieved = _aware_timestamp(retrieved_at, "retrieved_at")
    if settled < kickoff:
        raise SettlementTimestampSourceError("settlement_precedes_kickoff")
    if observed < settled:
        raise SettlementTimestampSourceError("observation_precedes_settlement")
    if retrieved < observed:
        raise SettlementTimestampSourceError("retrieval_precedes_observation")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "source_id": contract["source_id"],
        "qualification_digest": contract["qualification_digest"],
        "timestamp_field": contract["timestamp_field"],
        "timestamp_semantics": contract["timestamp_semantics"],
        "source_fixture_identity": fixture_identity,
        "source_fixture_identity_sha256": canonical_sha256(fixture_identity),
        "raw_payload": raw_payload,
        "raw_payload_sha256": canonical_sha256(raw_payload),
        "settlement_at": settled.isoformat().replace("+00:00", "Z"),
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
    }
    evidence["evidence_sha256"] = canonical_sha256(evidence)
    return evidence


def validate_settlement_timestamp_evidence(
    evidence: Any, *, source_contract: dict, raw_payload: dict,
    fixture_identity: dict, expected_fixture_identity: dict, kickoff_at: str,
) -> dict:
    if not isinstance(evidence, dict):
        raise SettlementTimestampSourceError("timestamp_evidence_invalid")
    if evidence.get("raw_payload") != raw_payload:
        raise SettlementTimestampSourceError("timestamp_raw_payload_binding_mismatch")
    expected = build_settlement_timestamp_evidence(
        source_contract=source_contract, raw_payload=raw_payload,
        fixture_identity=fixture_identity,
        expected_fixture_identity=expected_fixture_identity,
        kickoff_at=kickoff_at, observed_at=evidence.get("observed_at"),
        retrieved_at=evidence.get("retrieved_at"),
    )
    if evidence != expected:
        raise SettlementTimestampSourceError("timestamp_evidence_digest_or_binding_mismatch")
    return {
        "valid": True, "source_id": expected["source_id"],
        "settlement_at": expected["settlement_at"],
        "evidence_sha256": expected["evidence_sha256"],
    }


def reconcile_settlement_timestamp_evidence(
    evidence_items: list[dict], *, maximum_difference_seconds: int = 60,
) -> dict:
    if not isinstance(evidence_items, list) or not evidence_items:
        raise SettlementTimestampSourceError("timestamp_evidence_items_required")
    if isinstance(maximum_difference_seconds, bool) or not isinstance(maximum_difference_seconds, int) or maximum_difference_seconds < 0:
        raise SettlementTimestampSourceError("maximum_difference_invalid")
    sources = [item.get("source_id") for item in evidence_items if isinstance(item, dict)]
    if len(sources) != len(evidence_items) or len(set(sources)) != len(sources):
        raise SettlementTimestampSourceError("timestamp_sources_duplicate_or_invalid")
    stamps = [_aware_timestamp(item.get("settlement_at"), "settlement_at") for item in evidence_items]
    delta = (max(stamps) - min(stamps)).total_seconds()
    if delta > maximum_difference_seconds:
        raise SettlementTimestampSourceError("settlement_timestamp_conflict")
    return {
        "reconciled": True,
        "settlement_at": min(stamps).isoformat().replace("+00:00", "Z"),
        "source_count": len(evidence_items),
        "maximum_difference_seconds": maximum_difference_seconds,
        "observed_difference_seconds": int(delta),
        "evidence_digests": sorted(item["evidence_sha256"] for item in evidence_items),
    }
