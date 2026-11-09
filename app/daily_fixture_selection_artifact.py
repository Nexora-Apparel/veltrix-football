"""Evidence-checked offline daily fixture selection artifact builder."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.daily_fixture_selection import select_daily_fixtures
from app.provider_acquisition_artifact import validate_acquisition_report


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SelectionArtifactError(ValueError):
    pass


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def qualified_sources_from_registry(registry: Any) -> dict[str, list[str]]:
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise SelectionArtifactError("qualification_registry_schema_invalid")
    entries = registry.get("sources")
    if not isinstance(entries, list):
        raise SelectionArtifactError("qualification_registry_sources_invalid")

    qualified: dict[str, set[str]] = {}
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SelectionArtifactError(f"qualification_entry_invalid:{index}")
        provider = entry.get("provider")
        competition = entry.get("competition_key")
        run_id = entry.get("qualification_run_id")
        artifact_hash = entry.get("artifact_sha256")
        evidence_ref = entry.get("evidence_ref")
        if not isinstance(provider, str) or not provider.strip():
            raise SelectionArtifactError(f"qualification_provider_missing:{index}")
        if not isinstance(competition, (str, int)) or not str(competition).strip():
            raise SelectionArtifactError(f"qualification_competition_missing:{index}")
        if entry.get("qualification_status") != "qualified":
            raise SelectionArtifactError(f"source_not_qualified:{index}")
        if not isinstance(run_id, str) or not run_id.strip():
            raise SelectionArtifactError(f"qualification_run_id_missing:{index}")
        if not isinstance(artifact_hash, str) or not _SHA256.fullmatch(artifact_hash):
            raise SelectionArtifactError(f"qualification_artifact_hash_invalid:{index}")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise SelectionArtifactError(f"qualification_evidence_ref_missing:{index}")
        if entry.get("pagination_complete") is not True:
            raise SelectionArtifactError(f"qualification_pagination_incomplete:{index}")
        for field in ("invalid_rows", "duplicate_rows"):
            value = entry.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value != 0:
                raise SelectionArtifactError(f"qualification_{field}_nonzero:{index}")
        identity = (provider, str(competition))
        if identity in seen:
            raise SelectionArtifactError(f"duplicate_qualification_entry:{index}")
        seen.add(identity)
        qualified.setdefault(provider, set()).add(str(competition))

    return {provider: sorted(keys) for provider, keys in sorted(qualified.items())}


def build_daily_selection_artifact(*, acquisition_report: dict,
                                   qualification_registry: dict,
                                   target_date: str, as_of: str,
                                   max_fixtures: int = 25) -> dict:
    integrity = validate_acquisition_report(acquisition_report)
    qualified_sources = qualified_sources_from_registry(qualification_registry)
    selection = select_daily_fixtures(
        records=acquisition_report["records"],
        target_date=target_date,
        as_of=as_of,
        qualified_sources=qualified_sources,
        max_fixtures=max_fixtures,
    )
    registry_hash = _canonical_hash(qualification_registry)
    artifact = {
        "schema_version": 1,
        "artifact_type": "veltrix_daily_fixture_selection",
        "source_acquisition_report_sha256": integrity["report_sha256"],
        "qualification_registry_sha256": registry_hash,
        "selection": selection,
        "side_effects": {
            "provider_requests": 0,
            "database_writes": 0,
            "imports": 0,
            "prediction_publications": 0,
        },
    }
    artifact["selection_sha256"] = _canonical_hash(artifact)
    return artifact
