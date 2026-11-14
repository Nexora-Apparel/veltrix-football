"""Fail-closed, evidence-backed football team identity resolution.

Name similarity is candidate discovery only. Cross-provider identity is
resolved exclusively by a verified provider-ID crosswalk with scoped,
hash-addressed evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
import unicodedata
from urllib.parse import urlparse


_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_ISO_COUNTRY = re.compile(r"[A-Z]{2}")


@dataclass(frozen=True)
class TeamSourceRecord:
    source: str
    source_team_id: str
    display_name: str
    competition_id: str
    country_code: str


@dataclass(frozen=True)
class CanonicalTeam:
    canonical_team_id: str
    display_name: str
    competition_id: str
    country_code: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class TeamCrosswalkEntry:
    source: str
    source_team_id: str
    canonical_team_id: str
    competition_id: str
    country_code: str
    evidence_uri: str
    evidence_sha256: str
    verified_at: datetime


@dataclass(frozen=True)
class TeamResolution:
    status: str
    canonical_team_id: str | None
    candidate_canonical_team_ids: tuple[str, ...]
    reason_code: str


def normalize_team_name(value: str) -> str:
    """Normalize spelling and punctuation without dropping club-name tokens."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("TEAM_NAME_REQUIRED")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _valid_record(record: TeamSourceRecord) -> bool:
    return (
        isinstance(record, TeamSourceRecord)
        and all(isinstance(value, str) and value.strip() for value in (
            record.source, record.source_team_id, record.display_name,
            record.competition_id, record.country_code,
        ))
        and bool(_ISO_COUNTRY.fullmatch(record.country_code))
    )


def validate_crosswalk_registry(
    canonical_teams: tuple[CanonicalTeam, ...] | list[CanonicalTeam],
    entries: tuple[TeamCrosswalkEntry, ...] | list[TeamCrosswalkEntry],
) -> None:
    """Validate canonical identities, evidence, scope and source-ID uniqueness."""
    canonical_by_id: dict[str, CanonicalTeam] = {}
    for team in canonical_teams:
        if not isinstance(team, CanonicalTeam):
            raise ValueError("CANONICAL_TEAM_RECORD_INVALID")
        if not all(isinstance(value, str) and value.strip() for value in (
            team.canonical_team_id, team.display_name, team.competition_id, team.country_code
        )):
            raise ValueError("CANONICAL_TEAM_FIELDS_REQUIRED")
        if not _ISO_COUNTRY.fullmatch(team.country_code):
            raise ValueError("CANONICAL_TEAM_COUNTRY_INVALID")
        if team.canonical_team_id in canonical_by_id:
            raise ValueError("CANONICAL_TEAM_ID_DUPLICATE")
        if any(not isinstance(alias, str) or not alias.strip() for alias in team.aliases):
            raise ValueError("CANONICAL_TEAM_ALIAS_INVALID")
        canonical_by_id[team.canonical_team_id] = team

    source_keys: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, TeamCrosswalkEntry):
            raise ValueError("CROSSWALK_ENTRY_INVALID")
        if not all(isinstance(value, str) and value.strip() for value in (
            entry.source, entry.source_team_id, entry.canonical_team_id,
            entry.competition_id, entry.country_code, entry.evidence_uri,
            entry.evidence_sha256,
        )):
            raise ValueError("CROSSWALK_REQUIRED_FIELD_MISSING")
        if not _ISO_COUNTRY.fullmatch(entry.country_code):
            raise ValueError("CROSSWALK_COUNTRY_INVALID")
        parsed = urlparse(entry.evidence_uri)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("CROSSWALK_EVIDENCE_URI_INVALID")
        if not _SHA256.fullmatch(entry.evidence_sha256):
            raise ValueError("CROSSWALK_EVIDENCE_HASH_INVALID")
        if (not isinstance(entry.verified_at, datetime) or entry.verified_at.tzinfo is None
                or entry.verified_at.utcoffset() is None):
            raise ValueError("CROSSWALK_VERIFIED_AT_MUST_BE_AWARE")
        key = (entry.source, entry.source_team_id)
        if key in source_keys:
            raise ValueError("CROSSWALK_SOURCE_ID_DUPLICATE")
        source_keys.add(key)
        canonical = canonical_by_id.get(entry.canonical_team_id)
        if canonical is None:
            raise ValueError("CROSSWALK_CANONICAL_TEAM_UNKNOWN")
        if (entry.competition_id != canonical.competition_id
                or entry.country_code != canonical.country_code):
            raise ValueError("CROSSWALK_CANONICAL_SCOPE_MISMATCH")


def resolve_team_identity(
    record: TeamSourceRecord,
    *,
    canonical_teams: tuple[CanonicalTeam, ...] | list[CanonicalTeam],
    crosswalk_entries: tuple[TeamCrosswalkEntry, ...] | list[TeamCrosswalkEntry] = (),
) -> TeamResolution:
    """Resolve only explicit verified IDs; exact names produce review candidates."""
    if not _valid_record(record):
        raise ValueError("TEAM_SOURCE_RECORD_INVALID")
    validate_crosswalk_registry(canonical_teams, crosswalk_entries)

    exact_entries = [
        entry for entry in crosswalk_entries
        if entry.source == record.source and entry.source_team_id == record.source_team_id
    ]
    if exact_entries:
        entry = exact_entries[0]
        if (entry.competition_id != record.competition_id
                or entry.country_code != record.country_code):
            return TeamResolution(
                "SCOPE_MISMATCH", None, (), "SOURCE_ID_CROSSWALK_SCOPE_MISMATCH"
            )
        return TeamResolution(
            "RESOLVED", entry.canonical_team_id, (entry.canonical_team_id,),
            "VERIFIED_PROVIDER_ID_CROSSWALK",
        )

    source_name = normalize_team_name(record.display_name)
    candidates = []
    for team in canonical_teams:
        if team.competition_id != record.competition_id or team.country_code != record.country_code:
            continue
        names = (team.display_name, *team.aliases)
        if any(normalize_team_name(name) == source_name for name in names):
            candidates.append(team.canonical_team_id)

    candidates = sorted(set(candidates))
    if len(candidates) == 1:
        return TeamResolution(
            "REVIEW_REQUIRED", None, tuple(candidates), "EXACT_NAME_CANDIDATE_REQUIRES_EVIDENCE"
        )
    if len(candidates) > 1:
        return TeamResolution(
            "AMBIGUOUS", None, tuple(candidates), "EXACT_NAME_COLLISION"
        )
    return TeamResolution("UNRESOLVED", None, (), "NO_SCOPED_ID_OR_NAME_MATCH")
