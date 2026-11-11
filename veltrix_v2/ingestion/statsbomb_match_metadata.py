"""StatsBomb match metadata and conservative event-coverage manifest adapter.

Source date/kickoff strings retain original precision and timezone semantics. Only
explicitly offset-aware availability timestamps are normalized to UTC.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping, Sequence

from .statsbomb_events import StatsBombEvent


def _aware_utc(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _required_id(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if isinstance(value, bool) or value is None or not str(value).strip():
        raise ValueError(f"STATSBOMB_MATCH_METADATA_REQUIRED:{key}")
    return str(value).strip()


@dataclass(frozen=True, slots=True)
class StatsBombMatchMetadata:
    match_id: str
    competition_id: str
    competition_name: str
    season_id: str
    season_name: str
    home_team_id: str
    home_team_name: str
    away_team_id: str
    away_team_name: str
    match_date_raw: str | None
    kick_off_raw: str | None
    match_status: str | None
    match_week: int | None
    home_score: int | None
    away_score: int | None
    match_available_raw: str | None
    match_available_utc: datetime | None
    match_updated_raw: str | None
    match_updated_utc: datetime | None
    raw_metadata: Mapping[str, object]
    payload_sha256: str
    source: str = "statsbomb-open-data"


@dataclass(frozen=True, slots=True)
class StatsBombCoverageManifest:
    match_id: str
    competition_id: str
    season_id: str
    observed_event_count: int
    event_payload_sha256: str | None
    event_coverage_state: str
    match_available_utc: datetime | None
    match_updated_utc: datetime | None
    source: str = "statsbomb-open-data"
    completeness_semantics: str = "event_presence_does_not_prove_completeness"


def adapt_match_metadata(row: Mapping[str, object]) -> StatsBombMatchMetadata:
    if not isinstance(row, Mapping):
        raise ValueError("STATSBOMB_MATCH_METADATA_MUST_BE_MAPPING")
    competition_id = _required_id(row, "competition_id")
    season_id = _required_id(row, "season_id")
    match_id = _required_id(row, "match_id")
    competition_name = str(row.get("competition_name") or "").strip()
    season_name = str(row.get("season_name") or "").strip()
    home, away = row.get("home_team"), row.get("away_team")
    if not isinstance(home, Mapping) or not isinstance(away, Mapping):
        raise ValueError("STATSBOMB_MATCH_TEAMS_REQUIRED")
    home_id = _required_id(home, "home_team_id")
    away_id = _required_id(away, "away_team_id")
    home_name = str(home.get("home_team_name") or "").strip()
    away_name = str(away.get("away_team_name") or "").strip()
    if not home_name or not away_name or home_id == away_id:
        raise ValueError("STATSBOMB_MATCH_TEAM_IDENTITY_INVALID")

    def score(key: str) -> int | None:
        value = row.get(key)
        if value is None:
            return None
        if type(value) is not int or value < 0:
            raise ValueError(f"STATSBOMB_MATCH_SCORE_INVALID:{key}")
        return value

    week = row.get("match_week")
    if week is not None and (type(week) is not int or week < 0):
        raise ValueError("STATSBOMB_MATCH_WEEK_INVALID")
    available = row.get("match_available")
    updated = row.get("match_updated")
    available_raw = None if available in (None, "") else str(available)
    updated_raw = None if updated in (None, "") else str(updated)
    canonical = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str).encode()
    known = {
        "match_id", "competition_id", "competition_name", "season_id", "season_name",
        "home_team", "away_team", "match_date", "kick_off", "match_status",
        "match_week", "home_score", "away_score", "match_available", "match_updated",
    }
    extras = {key: value for key, value in row.items() if key not in known}
    return StatsBombMatchMetadata(
        match_id=match_id,
        competition_id=competition_id,
        competition_name=competition_name,
        season_id=season_id,
        season_name=season_name,
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        match_date_raw=None if row.get("match_date") in (None, "") else str(row["match_date"]),
        kick_off_raw=None if row.get("kick_off") in (None, "") else str(row["kick_off"]),
        match_status=None if row.get("match_status") in (None, "") else str(row["match_status"]),
        match_week=week,
        home_score=score("home_score"),
        away_score=score("away_score"),
        match_available_raw=available_raw,
        match_available_utc=_aware_utc(available_raw),
        match_updated_raw=updated_raw,
        match_updated_utc=_aware_utc(updated_raw),
        raw_metadata=MappingProxyType(extras),
        payload_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def build_coverage_manifest(
    metadata: StatsBombMatchMetadata,
    events: Sequence[StatsBombEvent] | None,
) -> StatsBombCoverageManifest:
    if events is None or len(events) == 0:
        return StatsBombCoverageManifest(
            match_id=metadata.match_id,
            competition_id=metadata.competition_id,
            season_id=metadata.season_id,
            observed_event_count=0,
            event_payload_sha256=None,
            event_coverage_state="events_missing",
            match_available_utc=metadata.match_available_utc,
            match_updated_utc=metadata.match_updated_utc,
        )
    if any(event.match_id != metadata.match_id for event in events):
        raise ValueError("STATSBOMB_COVERAGE_MATCH_ID_MISMATCH")
    if [event.event_index for event in events] != sorted(event.event_index for event in events):
        raise ValueError("STATSBOMB_COVERAGE_EVENTS_NOT_ORDERED")
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("STATSBOMB_COVERAGE_DUPLICATE_EVENT_ID")
    digest_payload = "|".join(event.payload_sha256 for event in events).encode()
    return StatsBombCoverageManifest(
        match_id=metadata.match_id,
        competition_id=metadata.competition_id,
        season_id=metadata.season_id,
        observed_event_count=len(events),
        event_payload_sha256=hashlib.sha256(digest_payload).hexdigest(),
        event_coverage_state="events_present_completeness_unverified",
        match_available_utc=metadata.match_available_utc,
        match_updated_utc=metadata.match_updated_utc,
    )


def availability_at_cutoff(
    metadata: StatsBombMatchMetadata, *, cutoff: datetime
) -> str:
    """Classify only source availability, never event-time or kickoff time."""
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("STATSBOMB_CUTOFF_MUST_BE_TIMEZONE_AWARE")
    available = metadata.match_available_utc
    if available is None:
        return "availability_time_unverified"
    if available > cutoff.astimezone(timezone.utc):
        return "available_after_cutoff"
    return "available_by_cutoff"
