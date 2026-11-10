"""Canonical source-payload integrity and provenance binding.

A supplied digest is never trusted by itself. The canonical payload is hashed
locally and bound to provider, endpoint, source ID, retrieval time and run ID.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


class SourcePayloadProvenanceError(ValueError):
    pass


def canonical_payload_sha256(payload: object) -> str:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SourcePayloadProvenanceError("source_payload_not_canonical_json") from None
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SourcePayloadProvenanceError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SourcePayloadProvenanceError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourcePayloadProvenanceError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def validate_source_payload_evidence(evidence: object) -> dict:
    required = {
        "provider", "endpoint", "source_id", "run_id", "retrieved_at",
        "payload", "payload_sha256",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise SourcePayloadProvenanceError("source_evidence_shape_invalid")
    for key in ("provider", "endpoint", "source_id", "run_id"):
        if not isinstance(evidence[key], str) or not evidence[key].strip():
            raise SourcePayloadProvenanceError(f"{key}_invalid")
    if not isinstance(evidence["payload"], (dict, list)):
        raise SourcePayloadProvenanceError("source_payload_type_invalid")
    retrieved = _timestamp(evidence["retrieved_at"], "retrieved_at")
    actual = canonical_payload_sha256(evidence["payload"])
    supplied = evidence["payload_sha256"]
    if not isinstance(supplied, str) or supplied != actual:
        raise SourcePayloadProvenanceError("source_payload_hash_mismatch")
    return {
        "valid": True,
        "payload_sha256": actual,
        "provider": evidence["provider"],
        "endpoint": evidence["endpoint"],
        "source_id": evidence["source_id"],
        "run_id": evidence["run_id"],
        "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
    }
