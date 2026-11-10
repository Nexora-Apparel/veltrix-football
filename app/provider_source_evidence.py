"""Restricted raw-source evidence sidecars and versioned provider mapping audits.

Raw payloads belong only in private acquisition artifacts. This module verifies
both the raw digest and the exact provider-specific normalization projection.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any

from app.provider_fixture_normalizer import normalize_fivedollar_fixture, normalize_striker_game

EVIDENCE_SCHEMA_VERSION = 1
MAPPING_VERSIONS = {
    "strikerapi": "strikerapi.list_games.normalization.v1",
    "fivedollar": "fivedollar.fixtures.normalization.v1",
}
_REQUIRED = {
    "schema_version", "mapping_version", "provider", "endpoint", "source_id",
    "run_id", "retrieved_at", "raw_payload", "raw_payload_sha256",
    "normalized_record", "normalized_record_sha256",
}


class SourceEvidenceError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise SourceEvidenceError("evidence_payload_not_canonical_json") from None
    return hashlib.sha256(raw).hexdigest()


def _normalization_projection(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "source_evidence"}


def _recompute(provider: str, payload: dict, record: dict) -> dict:
    common = {
        "endpoint": record["endpoint"],
        "retrieved_at": record["retrieved_at"],
        "run_id": record["run_id"],
    }
    if provider == "strikerapi":
        return normalize_striker_game(
            payload, competition_key=record["competition_key"],
            season=record.get("season"), **common,
        )
    if provider == "fivedollar":
        return normalize_fivedollar_fixture(payload, **common)
    raise SourceEvidenceError("evidence_provider_unsupported")


def build_source_evidence(*, provider: str, payload: dict, normalized_record: dict) -> dict:
    if provider not in MAPPING_VERSIONS or not isinstance(payload, dict):
        raise SourceEvidenceError("evidence_input_invalid")
    projection = _normalization_projection(normalized_record)
    try:
        recomputed = _recompute(provider, payload, projection)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SourceEvidenceError("provider_mapping_recomputation_failed") from None
    if recomputed != projection:
        raise SourceEvidenceError("provider_mapping_projection_mismatch")
    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "mapping_version": MAPPING_VERSIONS[provider],
        "provider": provider,
        "endpoint": projection["endpoint"],
        "source_id": projection["source_id"],
        "run_id": projection["run_id"],
        "retrieved_at": projection["retrieved_at"],
        "raw_payload": payload,
        "raw_payload_sha256": canonical_sha256(payload),
        "normalized_record": projection,
        "normalized_record_sha256": canonical_sha256(projection),
    }
    validate_source_evidence(evidence, expected_record=projection)
    return evidence


def validate_source_evidence(evidence: Any, *, expected_record: dict | None = None) -> dict:
    if not isinstance(evidence, dict) or set(evidence) != _REQUIRED:
        raise SourceEvidenceError("source_evidence_shape_invalid")
    provider = evidence.get("provider")
    if provider not in MAPPING_VERSIONS:
        raise SourceEvidenceError("evidence_provider_unsupported")
    if evidence.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise SourceEvidenceError("source_evidence_schema_unsupported")
    if evidence.get("mapping_version") != MAPPING_VERSIONS[provider]:
        raise SourceEvidenceError("provider_mapping_version_unsupported")
    for field in ("endpoint", "source_id", "run_id"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            raise SourceEvidenceError(f"evidence_{field}_invalid")
    retrieved = evidence.get("retrieved_at")
    if not isinstance(retrieved, str):
        raise SourceEvidenceError("evidence_retrieved_at_invalid")
    try:
        stamp = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
    except ValueError:
        raise SourceEvidenceError("evidence_retrieved_at_invalid") from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise SourceEvidenceError("evidence_retrieved_at_timezone_missing")
    payload = evidence.get("raw_payload")
    normalized = evidence.get("normalized_record")
    if not isinstance(payload, dict) or not isinstance(normalized, dict):
        raise SourceEvidenceError("evidence_payload_or_projection_invalid")
    raw_hash = canonical_sha256(payload)
    normalized_hash = canonical_sha256(normalized)
    if evidence.get("raw_payload_sha256") != raw_hash:
        raise SourceEvidenceError("raw_payload_sha256_mismatch")
    if evidence.get("normalized_record_sha256") != normalized_hash:
        raise SourceEvidenceError("normalized_record_sha256_mismatch")
    for field in ("provider", "endpoint", "source_id", "run_id", "retrieved_at"):
        if normalized.get(field) != evidence.get(field):
            raise SourceEvidenceError(f"evidence_{field}_projection_mismatch")
    if normalized.get("payload_sha256") != raw_hash:
        raise SourceEvidenceError("normalized_payload_digest_mismatch")
    if expected_record is not None and normalized != expected_record:
        raise SourceEvidenceError("source_evidence_record_binding_mismatch")
    try:
        recomputed = _recompute(provider, payload, normalized)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SourceEvidenceError("provider_mapping_recomputation_failed") from None
    if recomputed != normalized:
        raise SourceEvidenceError("provider_mapping_projection_mismatch")
    return {
        "valid": True, "provider": provider,
        "mapping_version": evidence["mapping_version"],
        "raw_payload_sha256": raw_hash,
        "normalized_record_sha256": normalized_hash,
    }
