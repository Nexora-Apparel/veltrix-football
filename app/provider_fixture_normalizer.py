"""Provider-neutral fixture normalization with provenance and fail-closed validation.

This module performs no network access and has no database dependency. It
normalizes one source observation at a time and returns quarantine reasons
instead of guessing missing identity, timezones, statuses, or scores.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 1
SETTLED_STATUSES = {"final", "finished", "ft", "full_time"}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _utc_timestamp(value: Any) -> str:
    raw = _text(value)
    if not raw:
        raise ValueError("missing_kickoff")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid_kickoff") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff_timezone_missing")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _score(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid_score")
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError("invalid_score")


def _hash_payload(row: dict) -> str:
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _base_record(provider: str, source_id: Any, competition_key: Any,
                 season: Any, home_id: Any, away_id: Any,
                 home_name: Any, away_name: Any, kickoff: Any,
                 source_status: Any, home_score: Any, away_score: Any,
                 endpoint: str, retrieved_at: str, run_id: str,
                 raw_row: dict) -> dict:
    if not isinstance(raw_row, dict):
        raise ValueError("source_row_not_object")
    if not _text(source_id):
        raise ValueError("missing_source_id")
    if not _text(competition_key):
        raise ValueError("missing_competition_key")
    if not _text(home_id) or not _text(away_id):
        raise ValueError("missing_team_source_id")
    if not _text(home_name) or not _text(away_name):
        raise ValueError("missing_team_name")
    if _text(home_id) == _text(away_id):
        raise ValueError("home_away_team_id_collision")
    if not _text(endpoint) or not _text(run_id):
        raise ValueError("missing_endpoint_or_run_id")
    retrieved = _utc_timestamp(retrieved_at)
    kickoff_utc = _utc_timestamp(kickoff)
    status = _text(source_status).casefold()
    if not status:
        raise ValueError("missing_status")
    normalized_status = {
        "final": "finished", "ft": "finished", "full_time": "finished",
        "finished": "finished", "scheduled": "scheduled",
        "not_started": "scheduled", "postponed": "postponed",
        "cancelled": "cancelled", "canceled": "cancelled",
        "in_progress": "in_progress", "live": "in_progress",
    }.get(status, "unknown")
    hs, aws = _score(home_score), _score(away_score)
    if normalized_status == "finished" and (hs is None or aws is None):
        raise ValueError("finished_fixture_missing_score")
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "source_id": _text(source_id),
        "competition_key": _text(competition_key),
        "season": _text(season) or None,
        "home_team_source_id": _text(home_id),
        "away_team_source_id": _text(away_id),
        "home_team_name": _text(home_name),
        "away_team_name": _text(away_name),
        "kickoff_at": kickoff_utc,
        "source_status": status,
        "normalized_status": normalized_status,
        "home_score": hs,
        "away_score": aws,
        "endpoint": _text(endpoint),
        "retrieved_at": retrieved,
        "payload_sha256": _hash_payload(raw_row),
        "run_id": _text(run_id),
    }


def normalize_striker_game(row: dict, *, competition_key: str,
                            endpoint: str, retrieved_at: str,
                            run_id: str, season: str | int | None = None) -> dict:
    if not isinstance(row, dict):
        raise ValueError("source_row_not_object")
    home, away = row.get("home") or {}, row.get("away") or {}
    if not isinstance(home, dict) or not isinstance(away, dict):
        raise ValueError("team_object_invalid")
    return _base_record(
        "strikerapi", row.get("game_id"), competition_key, season,
        home.get("team_id"), away.get("team_id"), home.get("name"), away.get("name"),
        row.get("starts_at") or row.get("date"), row.get("status"),
        home.get("score"), away.get("score"), endpoint, retrieved_at, run_id, row,
    )


def normalize_fivedollar_fixture(row: dict, *, endpoint: str,
                                  retrieved_at: str, run_id: str) -> dict:
    if not isinstance(row, dict):
        raise ValueError("source_row_not_object")
    teams, goals, league = row.get("teams") or {}, row.get("goals") or {}, row.get("league") or {}
    if not all(isinstance(x, dict) for x in (teams, goals, league)):
        raise ValueError("provider_nested_object_invalid")
    home, away = teams.get("home") or {}, teams.get("away") or {}
    if not isinstance(home, dict) or not isinstance(away, dict):
        raise ValueError("team_object_invalid")
    return _base_record(
        "fivedollar", row.get("id"), league.get("id"), row.get("season"),
        home.get("id"), away.get("id"), home.get("name"), away.get("name"),
        row.get("kickoff_utc") or row.get("date"), row.get("status"),
        goals.get("home"), goals.get("away"), endpoint, retrieved_at, run_id, row,
    )


def normalize_observation(provider: str, row: dict, **kwargs) -> dict:
    """Dispatch by explicit provider name; unknown providers fail closed."""
    if provider == "strikerapi":
        return normalize_striker_game(row, **kwargs)
    if provider == "fivedollar":
        return normalize_fivedollar_fixture(row, **kwargs)
    raise ValueError("unsupported_provider")
