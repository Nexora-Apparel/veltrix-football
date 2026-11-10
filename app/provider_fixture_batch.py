"""Deterministic batch validation, deduplication, and sanitized quarantine.

This is an in-memory read-only boundary between provider retrieval and any
future import process. It never writes to storage or repairs conflicting rows.
Quarantine entries retain only identity hints and a payload hash, never raw rows.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from app.provider_fixture_normalizer import normalize_observation
from app.provider_source_evidence import SourceEvidenceError, build_source_evidence


def _safe_source_summary(provider, row, options) -> dict:
    summary = {"provider": provider if isinstance(provider, str) else "unknown"}
    if isinstance(row, dict):
        source_id = row.get("game_id", row.get("id"))
        if source_id is not None and isinstance(source_id, (str, int)):
            summary["source_id"] = str(source_id)
        league = row.get("league")
        if isinstance(league, dict) and league.get("id") is not None:
            summary["competition_key"] = str(league["id"])
        home, away = row.get("home"), row.get("away")
        teams = row.get("teams")
        if isinstance(home, dict) and isinstance(away, dict):
            summary["home_team_source_id"] = str(home.get("team_id")) if home.get("team_id") is not None else None
            summary["away_team_source_id"] = str(away.get("team_id")) if away.get("team_id") is not None else None
        elif isinstance(teams, dict):
            h, a = teams.get("home"), teams.get("away")
            if isinstance(h, dict) and h.get("id") is not None:
                summary["home_team_source_id"] = str(h["id"])
            if isinstance(a, dict) and a.get("id") is not None:
                summary["away_team_source_id"] = str(a["id"])
        try:
            canonical = json.dumps(row, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False, allow_nan=False)
            summary["payload_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            summary["payload_sha256"] = None
    if isinstance(options, dict):
        key = options.get("competition_key")
        if key is not None and "competition_key" not in summary:
            summary["competition_key"] = str(key)
    return summary


def _safe_normalized_summary(record: dict) -> dict:
    keys = (
        "provider", "source_id", "competition_key",
        "home_team_source_id", "away_team_source_id", "payload_sha256",
    )
    return {key: record[key] for key in keys if key in record}


def process_observations(observations: list[dict]) -> dict:
    if not isinstance(observations, list):
        raise ValueError("observations_must_be_a_list")

    accepted: list[dict | None] = []
    quarantined: list[dict] = []
    identity_indexes: dict[tuple[str, str, str], int] = {}
    duplicate_identities: set[tuple[str, str, str]] = set()

    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            quarantined.append({
                "input_index": index, "reason": "observation_not_object",
                "source": None,
            })
            continue
        provider, row, options = item.get("provider"), item.get("row"), item.get("options")
        if not isinstance(options, dict):
            quarantined.append({
                "input_index": index,
                "reason": "normalization_options_missing_or_invalid",
                "source": _safe_source_summary(provider, row, None),
            })
            continue
        try:
            record = normalize_observation(provider, row, **options)
            record["source_evidence"] = build_source_evidence(
                provider=provider, payload=row, normalized_record=record,
            )
        except (TypeError, ValueError, AttributeError, SourceEvidenceError) as exc:
            quarantined.append({
                "input_index": index, "reason": str(exc)[:120] or "normalization_failed",
                "source": _safe_source_summary(provider, row, options),
            })
            continue

        identity = (record["provider"], record["competition_key"], record["source_id"])
        if identity in identity_indexes:
            if identity not in duplicate_identities:
                previous_index = identity_indexes[identity]
                previous_record = accepted[previous_index]
                accepted[previous_index] = None
                quarantined.append({
                    "input_index": previous_index,
                    "reason": "duplicate_provider_competition_source_identity",
                    "source": _safe_normalized_summary(previous_record),
                })
                duplicate_identities.add(identity)
            quarantined.append({
                "input_index": index,
                "reason": "duplicate_provider_competition_source_identity",
                "source": _safe_normalized_summary(record),
            })
            continue

        identity_indexes[identity] = len(accepted)
        accepted.append(record)

    accepted_records = [record for record in accepted if record is not None]
    reason_counts = Counter(item["reason"] for item in quarantined)
    return {
        "schema_version": 1,
        "mode": "read_only_batch_validation",
        "acceptance_pass": len(quarantined) == 0,
        "input_count": len(observations),
        "accepted_count": len(accepted_records),
        "quarantined_count": len(quarantined),
        "duplicate_identity_count": len(duplicate_identities),
        "quarantine_reasons": dict(sorted(reason_counts.items())),
        "accepted": accepted_records,
        "quarantined": quarantined,
        "database_writes": 0,
        "imports": 0,
        "canonical_merges": 0,
    }
