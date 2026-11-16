"""Evidence-backed entity identity and crosswalk utilities."""
from .teams import (
    CanonicalTeam,
    TeamCrosswalkEntry,
    TeamResolution,
    TeamSourceRecord,
    normalize_team_name,
    resolve_team_identity,
    validate_crosswalk_registry,
)

__all__ = [
    "CanonicalTeam", "TeamCrosswalkEntry", "TeamResolution",
    "TeamSourceRecord", "normalize_team_name",
    "resolve_team_identity", "validate_crosswalk_registry",
]
