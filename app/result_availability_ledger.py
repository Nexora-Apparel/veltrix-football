"""Append-only observations of when a provider exposed a terminal result.

An observed_at timestamp records VELTRIX's observation of a response. It is
availability evidence only; it must never be relabelled as match settlement.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

SCHEMA_VERSION = 1
TERMINAL_STATES = {
    "strikerapi": {"final"},
    "fivedollar": {"finished"},
}


class ResultAvailabilityLedgerError(ValueError):
    pass


def _canonical_hash(value: Any) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise ResultAvailabilityLedgerError("payload_not_canonical_json") from None
    return hashlib.sha256(encoded).hexdigest()


def _aware_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ResultAvailabilityLedgerError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ResultAvailabilityLedgerError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResultAvailabilityLedgerError(f"{field}_timezone_missing")
    return parsed


def build_result_observation(*, provider: str, competition_id: str,
                             fixture_id: str, source_id: str, endpoint: str,
                             run_id: str, observed_at: str, payload: dict,
                             status_field: str = "status") -> dict:
    if provider not in TERMINAL_STATES:
        raise ResultAvailabilityLedgerError("provider_unsupported")
    for name, value in (("competition_id", competition_id), ("fixture_id", fixture_id),
                        ("source_id", source_id), ("endpoint", endpoint), ("run_id", run_id)):
        if not isinstance(value, str) or not value.strip():
            raise ResultAvailabilityLedgerError(f"{name}_invalid")
    observed = _aware_timestamp(observed_at, "observed_at")
    if not isinstance(payload, dict):
        raise ResultAvailabilityLedgerError("payload_invalid")
    if not isinstance(status_field, str) or not status_field:
        raise ResultAvailabilityLedgerError("status_field_invalid")
    status = payload.get(status_field)
    terminal = status in TERMINAL_STATES[provider]
    raw_digest = _canonical_hash(payload)
    observation = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "competition_id": competition_id,
        "fixture_id": fixture_id,
        "source_id": source_id,
        "endpoint": endpoint,
        "run_id": run_id,
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "status_field": status_field,
        "observed_status": status,
        "terminal_result_observed": terminal,
        "raw_payload": payload,
        "raw_payload_sha256": raw_digest,
    }
    observation["observation_id"] = _canonical_hash({
        key: value for key, value in observation.items() if key != "observation_id"
    })
    return observation


def validate_result_observation(observation: Any) -> dict:
    required = {
        "schema_version", "provider", "competition_id", "fixture_id", "source_id",
        "endpoint", "run_id", "observed_at", "status_field", "observed_status",
        "terminal_result_observed", "raw_payload", "raw_payload_sha256", "observation_id",
    }
    if not isinstance(observation, dict) or set(observation) != required:
        raise ResultAvailabilityLedgerError("observation_shape_invalid")
    if observation["schema_version"] != SCHEMA_VERSION:
        raise ResultAvailabilityLedgerError("schema_version_unsupported")
    expected = build_result_observation(
        provider=observation["provider"],
        competition_id=observation["competition_id"],
        fixture_id=observation["fixture_id"],
        source_id=observation["source_id"],
        endpoint=observation["endpoint"],
        run_id=observation["run_id"],
        observed_at=observation["observed_at"],
        payload=observation["raw_payload"],
        status_field=observation["status_field"],
    )
    if expected != observation:
        raise ResultAvailabilityLedgerError("observation_integrity_mismatch")
    return {"valid": True, "observation_id": expected["observation_id"],
            "raw_payload_sha256": expected["raw_payload_sha256"]}


def append_observations(ledger: Any, observations: list[dict]) -> dict:
    if not isinstance(ledger, dict) or set(ledger) != {"schema_version", "observations"}:
        raise ResultAvailabilityLedgerError("ledger_shape_invalid")
    if ledger["schema_version"] != SCHEMA_VERSION or not isinstance(ledger["observations"], list):
        raise ResultAvailabilityLedgerError("ledger_schema_invalid")
    if not isinstance(observations, list):
        raise ResultAvailabilityLedgerError("observations_must_be_list")
    existing = list(ledger["observations"])
    seen = set()
    last_by_fixture: dict[tuple[str, str], datetime] = {}
    for item in existing:
        validate_result_observation(item)
        oid = item["observation_id"]
        if oid in seen:
            raise ResultAvailabilityLedgerError("existing_duplicate_observation")
        seen.add(oid)
        key = (item["provider"], item["fixture_id"])
        stamp = _aware_timestamp(item["observed_at"], "observed_at")
        if key in last_by_fixture and stamp < last_by_fixture[key]:
            raise ResultAvailabilityLedgerError("existing_observation_order_invalid")
        last_by_fixture[key] = stamp

    added = 0
    for item in observations:
        validate_result_observation(item)
        oid = item["observation_id"]
        if oid in seen:
            continue
        key = (item["provider"], item["fixture_id"])
        stamp = _aware_timestamp(item["observed_at"], "observed_at")
        if key in last_by_fixture and stamp < last_by_fixture[key]:
            raise ResultAvailabilityLedgerError("observation_time_regression")
        existing.append(item)
        seen.add(oid)
        last_by_fixture[key] = stamp
        added += 1
    return {
        "ledger": {"schema_version": SCHEMA_VERSION, "observations": existing},
        "added_count": added,
        "total_observation_count": len(existing),
        "database_writes": 0,
        "imports": 0,
    }


def first_terminal_observation(ledger: dict, *, provider: str, fixture_id: str) -> dict | None:
    if not isinstance(ledger, dict) or ledger.get("schema_version") != SCHEMA_VERSION:
        raise ResultAvailabilityLedgerError("ledger_schema_invalid")
    matches = []
    for item in ledger.get("observations", []):
        validate_result_observation(item)
        if (item["provider"] == provider and item["fixture_id"] == fixture_id
                and item["terminal_result_observed"]):
            matches.append(item)
    if not matches:
        return None
    matches.sort(key=lambda item: _aware_timestamp(item["observed_at"], "observed_at"))
    first = matches[0]
    return {
        "provider": provider,
        "fixture_id": fixture_id,
        "first_observed_at": first["observed_at"],
        "observation_id": first["observation_id"],
        "raw_payload_sha256": first["raw_payload_sha256"],
        "timestamp_semantics": "veltrix_first_observed_terminal_result_availability",
        "is_settlement_timestamp": False,
        "historical_availability_reconstructed": False,
    }
