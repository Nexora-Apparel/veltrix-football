"""Explicit, scoped provider identity crosswalks; fuzzy matches never auto-merge."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TeamCrosswalk:
    provider: str
    competition_key: str
    season: str
    provider_team_id: str
    canonical_team_id: str
    evidence_ref: str
    status: str

    def __post_init__(self) -> None:
        required = (self.provider, self.competition_key, self.season,
                    self.provider_team_id, self.canonical_team_id, self.evidence_ref)
        if any(not value.strip() for value in required):
            raise ValueError("crosswalk scope, IDs and evidence reference are required")
        if self.status not in {"candidate", "approved", "rejected"}:
            raise ValueError("crosswalk status must be candidate, approved or rejected")
        if self.provider_team_id == self.canonical_team_id and self.provider == "canonical":
            raise ValueError("provider identity cannot masquerade as canonical namespace")


def resolve_team(
    rows: tuple[TeamCrosswalk, ...],
    *,
    provider: str,
    competition_key: str,
    season: str,
    provider_team_id: str,
) -> str | None:
    matches = [
        row for row in rows
        if row.provider == provider
        and row.competition_key == competition_key
        and row.season == season
        and row.provider_team_id == provider_team_id
        and row.status == "approved"
    ]
    if len(matches) > 1:
        raise ValueError("multiple approved canonical identities for one provider team")
    return matches[0].canonical_team_id if matches else None
