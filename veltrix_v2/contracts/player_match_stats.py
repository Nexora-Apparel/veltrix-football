"""Canonical, point-in-time contract for provider-supplied player match statistics.

This is an ingestion contract only. It does not calculate player ratings, probabilities,
or predictions. Missing values remain None and xG values retain their model identity.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping as TypingMapping


_ALLOWED_METRICS = frozenset({
    "minutes_played", "goals", "assists", "shots", "shots_on_target",
    "shots_off_target", "xg", "npxg", "xa", "key_passes",
    "passes_attempted", "passes_completed", "crosses", "progressive_passes",
    "tackles", "interceptions", "clearances", "blocks", "duels_won",
    "aerials_won", "fouls_committed", "fouls_won", "yellow_cards",
    "red_cards", "saves", "goals_conceded", "own_goals",
    "penalties_saved", "penalties_missed", "recoveries", "offsides",
    "carries", "progressive_carries",
})
_COUNT_METRICS = _ALLOWED_METRICS - {"minutes_played", "xg", "npxg", "xa"}
_XG_METRICS = frozenset({"xg", "npxg"})


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PlayerMatchStats:
    provider: str
    provider_match_id: str
    provider_player_id: str
    provider_team_id: str
    competition_key: str
    season: str
    kickoff_utc: datetime
    retrieved_at_utc: datetime
    available_at_utc: datetime
    payload_sha256: str
    schema_version: str
    rights_approval_id: str
    stats: TypingMapping[str, int | float | None]
    started: bool | None = None
    position: str | None = None
    xg_model_id: str | None = None
    xa_model_id: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "provider", "provider_match_id", "provider_player_id",
            "provider_team_id", "competition_key", "season",
            "schema_version", "rights_approval_id",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} is required")

        kickoff = _utc(self.kickoff_utc, "kickoff_utc")
        retrieved = _utc(self.retrieved_at_utc, "retrieved_at_utc")
        available = _utc(self.available_at_utc, "available_at_utc")
        if available < kickoff:
            raise ValueError("player match statistics cannot be available before kickoff")
        if available > retrieved:
            raise ValueError("available_at_utc cannot be after retrieved_at_utc")
        object.__setattr__(self, "kickoff_utc", kickoff)
        object.__setattr__(self, "retrieved_at_utc", retrieved)
        object.__setattr__(self, "available_at_utc", available)

        digest = self.payload_sha256.lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("payload_sha256 must be a 64-character SHA-256 hex digest")
        object.__setattr__(self, "payload_sha256", digest)

        if self.started is not None and type(self.started) is not bool:
            raise ValueError("started must be bool or None")
        if not isinstance(self.stats, Mapping):
            raise ValueError("stats must be a mapping")
        unknown = set(self.stats) - _ALLOWED_METRICS
        if unknown:
            raise ValueError(f"unsupported player metrics: {', '.join(sorted(unknown))}")

        normalized: dict[str, int | float | None] = {}
        for metric, value in self.stats.items():
            if value is None:
                normalized[metric] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{metric} must be numeric or None")
            if not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"{metric} must be finite and non-negative")
            if metric in _COUNT_METRICS and type(value) is not int:
                raise ValueError(f"{metric} must be an integer count")
            if metric == "minutes_played" and value > 150:
                raise ValueError("minutes_played cannot exceed 150")
            normalized[metric] = value

        if any(normalized.get(metric) is not None for metric in _XG_METRICS) and not (self.xg_model_id or "").strip():
            raise ValueError("xg_model_id is required whenever xG or npxG is present")
        if normalized.get("xa") is not None and not (self.xa_model_id or "").strip():
            raise ValueError("xa_model_id is required whenever xA is present")
        object.__setattr__(self, "stats", MappingProxyType(normalized))

    def available_by(self, cutoff_utc: datetime) -> bool:
        cutoff = _utc(cutoff_utc, "cutoff_utc")
        return self.available_at_utc <= cutoff
