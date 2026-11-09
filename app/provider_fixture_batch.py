"""Deterministic batch validation, deduplication, and quarantine.

This is an in-memory read-only boundary between provider retrieval and any
future import process. It never writes to storage or repairs conflicting rows.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.provider_fixture_normalizer import normalize_observation


def process_observations(observations: list[dict]) -> dict:
    if not isinstance(observations, list):
        raise ValueError("observations_must_be_a_list")

    accepted: list[dict] = []
    quarantined: list[dict] = []
    identity_indexes: dict[tuple[str, str, str], int] = {}
    duplicate_indexes: set[int] = set()

    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            quarantined.append({
                "input_index": index,
                "reason": "observation_not_object",
                "source": None,
            })
            continue
        provider = item.get("provider")
        row = item.get("row")
        options = item.get("options")
        if not isinstance(options, dict):
            quarantined.append({
                "input_index": index,
                "reason": "normalization_options_missing_or_invalid",
                "source": item,
            })
            continue
        try:
            record = normalize_observation(provider, row, **options)
        except (TypeError, ValueError) as exc:
            quarantined.append({
                "input_index": index,
                "reason": str(exc)[:120],
                "source": {"provider": provider, "row": row},
            })
            continue

        identity = (
            record["provider"],
            record["competition_key"],
            record["source_id"],
        )
        if identity in identity_indexes:
            previous_index = identity_indexes[identity]
            duplicate_indexes.add(previous_index)
            duplicate_indexes.add(index)
            quarantined.append({
                "input_index": previous_index,
                "reason": "duplicate_provider_competition_source_identity",
                "source": accepted[previous_index],
            })
            accepted[previous_index] = None
            quarantined.append({
                "input_index": index,
                "reason": "duplicate_provider_competition_source_identity",
                "source": record,
            })
            continue

        identity_indexes[identity] = len(accepted)
        accepted.append(record)

    accepted = [record for record in accepted if record is not None]
    reason_counts = Counter(item["reason"] for item in quarantined)
    return {
        "schema_version": 1,
        "mode": "read_only_batch_validation",
        "acceptance_pass": len(quarantined) == 0,
        "input_count": len(observations),
        "accepted_count": len(accepted),
        "quarantined_count": len(quarantined),
        "duplicate_identity_count": sum(
            1 for item in quarantined
            if item["reason"] == "duplicate_provider_competition_source_identity"
        ) // 2,
        "quarantine_reasons": dict(sorted(reason_counts.items())),
        "accepted": accepted,
        "quarantined": quarantined,
        "database_writes": 0,
        "imports": 0,
        "canonical_merges": 0,
    }
