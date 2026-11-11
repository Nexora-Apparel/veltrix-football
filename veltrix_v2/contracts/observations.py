"""Immutable, provider-neutral contracts for VELTRIX FOOTBALL 2.0."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


def require_aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    provider: str
    endpoint: str
    entity_type: str
    provider_entity_id: str
    competition_key: str
    season: str
    retrieved_at_utc: datetime
    source_event_time_utc: datetime
    available_at_utc: datetime
    payload_sha256: str
    schema_version: str
    rights_approval_id: str
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        for name in ("provider", "endpoint", "entity_type", "provider_entity_id",
                     "competition_key", "season", "schema_version", "rights_approval_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        for name in ("retrieved_at_utc", "source_event_time_utc", "available_at_utc"):
            object.__setattr__(self, name, require_aware_utc(getattr(self, name), name))
        digest = self.payload_sha256.lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("payload_sha256 must be a 64-character SHA-256 hex digest")
        object.__setattr__(self, "payload_sha256", digest)
        if self.available_at_utc > self.retrieved_at_utc:
            raise ValueError("available_at_utc cannot be after retrieved_at_utc")


@dataclass(frozen=True, slots=True)
class FixtureIdentity:
    provider: str
    provider_fixture_id: str
    competition_key: str
    season: str
    home_provider_team_id: str
    away_provider_team_id: str
    kickoff_utc: datetime

    def __post_init__(self) -> None:
        if not all((self.provider, self.provider_fixture_id, self.competition_key,
                    self.season, self.home_provider_team_id, self.away_provider_team_id)):
            raise ValueError("fixture identity fields are required")
        if self.home_provider_team_id == self.away_provider_team_id:
            raise ValueError("home and away team identities must differ")
        object.__setattr__(self, "kickoff_utc", require_aware_utc(self.kickoff_utc, "kickoff_utc"))


@dataclass(frozen=True, slots=True)
class ForecastCutoff:
    cutoff_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_utc", require_aware_utc(self.cutoff_utc, "cutoff_utc"))

    def permits(self, observation: ProviderObservation) -> bool:
        return observation.available_at_utc <= self.cutoff_utc
