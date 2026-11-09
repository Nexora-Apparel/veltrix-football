"""Offline integrity checks for sanitized fixture acquisition reports."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECORD_KEYS = {
    "schema_version", "provider", "source_id", "competition_key", "season",
    "home_team_source_id", "away_team_source_id", "home_team_name",
    "away_team_name", "kickoff_at", "source_status", "normalized_status",
    "home_score", "away_score", "endpoint", "retrieved_at", "payload_sha256",
    "run_id",
}
_QUARANTINE_KEYS = {"input_index", "reason", "source"}


class ArtifactIntegrityError(ValueError):
    pass


def _canonical_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_acquisition_report(report: Any) -> dict:
    if not isinstance(report, dict):
        raise ArtifactIntegrityError("report_not_object")
    if report.get("schema_version") != 1 or report.get("report_type") != "veltrix_provider_fixture_acquisition":
        raise ArtifactIntegrityError("unsupported_report_schema")
    supplied_hash = report.get("report_sha256")
    if not isinstance(supplied_hash, str) or not _HEX_SHA256.fullmatch(supplied_hash):
        raise ArtifactIntegrityError("report_hash_missing_or_invalid")
    unhashed = dict(report)
    unhashed.pop("report_sha256", None)
    if _canonical_hash(unhashed) != supplied_hash:
        raise ArtifactIntegrityError("report_hash_mismatch")

    quality, records, quarantine = report.get("quality"), report.get("records"), report.get("quarantine")
    if not isinstance(quality, dict):
        raise ArtifactIntegrityError("quality_block_invalid")
    if not isinstance(records, list) or not isinstance(quarantine, list):
        raise ArtifactIntegrityError("record_arrays_invalid")
    if quality.get("accepted_count") != len(records):
        raise ArtifactIntegrityError("accepted_count_mismatch")
    if quality.get("quarantined_count") != len(quarantine):
        raise ArtifactIntegrityError("quarantined_count_mismatch")
    if quality.get("input_count") != len(records) + len(quarantine):
        raise ArtifactIntegrityError("input_count_mismatch")

    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
            raise ArtifactIntegrityError(f"normalized_record_shape_invalid:{index}")
        if record.get("schema_version") != 1:
            raise ArtifactIntegrityError(f"normalized_record_schema_invalid:{index}")
        if not isinstance(record.get("payload_sha256"), str) or not _HEX_SHA256.fullmatch(record["payload_sha256"]):
            raise ArtifactIntegrityError(f"payload_hash_invalid:{index}")

    safe_source_keys = {
        "provider", "source_id", "competition_key", "home_team_source_id",
        "away_team_source_id", "payload_sha256",
    }
    for index, item in enumerate(quarantine):
        if not isinstance(item, dict) or set(item) != _QUARANTINE_KEYS:
            raise ArtifactIntegrityError(f"quarantine_shape_invalid:{index}")
        source = item.get("source")
        if source is not None and (
            not isinstance(source, dict) or not set(source).issubset(safe_source_keys)
        ):
            raise ArtifactIntegrityError(f"quarantine_source_not_sanitized:{index}")

    side_effects = report.get("side_effects")
    required_zero = {"database_writes", "imports", "checkpoints", "canonical_merges", "prediction_publications"}
    if not isinstance(side_effects, dict) or any(side_effects.get(key) != 0 for key in required_zero):
        raise ArtifactIntegrityError("side_effect_boundary_invalid")

    return {
        "valid": True, "report_sha256": supplied_hash,
        "accepted_count": len(records), "quarantined_count": len(quarantine),
        "input_count": len(records) + len(quarantine),
        "acceptance_pass": quality.get("acceptance_pass") is True,
    }


def validate_acquisition_report_file(path: str | Path) -> dict:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError(f"report_file_unreadable:{type(exc).__name__}") from None
    return validate_acquisition_report(report)
