"""Versioned, fail-closed provider team alias registry.

Pending rows are documentation only. This module never guesses team identity.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class AliasRegistryError(ValueError):
    pass


def load_registry(path: str | Path) -> dict:
    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AliasRegistryError("alias registry could not be read") from exc
    validate_registry(registry)
    return registry


def validate_registry(registry: dict) -> None:
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise AliasRegistryError("unsupported registry schema")
    if registry.get("status") not in ("review_only", "approved"):
        raise AliasRegistryError("registry status must be review_only or approved")
    rows = registry.get("candidates")
    if not isinstance(rows, list):
        raise AliasRegistryError("candidates must be a list")
    seen_striker, seen_dollar, seen_pairs = set(), set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise AliasRegistryError("candidate row must be an object")
        required = ("competition_key", "season", "striker_team_id", "fivedollar_team_id",
                    "striker_name", "fivedollar_name", "status")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in required):
            raise AliasRegistryError("candidate identity and scope fields must be non-empty strings")
        if row["status"] not in ("pending_independent_verification", "approved", "rejected"):
            raise AliasRegistryError("unknown candidate status")
        scope = (row["competition_key"], row["season"])
        sid_key = (*scope, row["striker_team_id"])
        did_key = (*scope, row["fivedollar_team_id"])
        pair_key = (*scope, row["striker_team_id"], row["fivedollar_team_id"])
        if sid_key in seen_striker or did_key in seen_dollar or pair_key in seen_pairs:
            raise AliasRegistryError("team ID collision or duplicate pair within competition/season")
        seen_striker.add(sid_key)
        seen_dollar.add(did_key)
        seen_pairs.add(pair_key)
        if registry["status"] == "approved" and row["status"] == "pending_independent_verification":
            raise AliasRegistryError("approved registry cannot contain pending candidates")
        if row["status"] == "approved":
            evidence = row.get("evidence_url")
            retrieved = row.get("evidence_retrieved_at")
            reviewer = row.get("reviewer")
            if not all(isinstance(v, str) and v.strip() for v in (evidence, retrieved, reviewer)):
                raise AliasRegistryError("approved aliases require evidence URL, retrieval timestamp and reviewer")
            try:
                parsed = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
            except ValueError as exc:
                raise AliasRegistryError("approved alias evidence timestamp is invalid") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise AliasRegistryError("approved alias evidence timestamp must include timezone")


def alias_pair_is_approved(registry: dict, competition_key: str, season: str,
                           striker_team_id: str, fivedollar_team_id: str) -> bool:
    validate_registry(registry)
    if registry.get("status") != "approved":
        return False
    for row in registry["candidates"]:
        if (row["competition_key"] == competition_key and row["season"] == season
                and row["striker_team_id"] == str(striker_team_id)
                and row["fivedollar_team_id"] == str(fivedollar_team_id)
                and row["status"] == "approved"):
            return True
    return False
