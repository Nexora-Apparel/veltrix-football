"""Point-in-time player-form features over canonical, timestamp-qualified evidence.

Raw OpenPlay dates/scrape strings cannot populate this contract unless a separate,
defensible timezone-aware availability timestamp is supplied. Missing evidence abstains.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping, Sequence


_METRICS = (
    "minutes_played", "goals", "assists", "shots", "shots_on_target",
    "xg", "npxg", "xa", "key_passes", "tackles", "interceptions",
)


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"PLAYER_FORM_{field}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PlayerMatchEvidence:
    match_id: str
    player_id: str
    team_id: str
    kickoff_utc: datetime
    available_at_utc: datetime
    metrics: Mapping[str, int | float | None]
    started: bool | None
    xg_model_id: str | None
    xa_model_id: str | None = None
    quality_state: str = "eligible_for_research"

    def __post_init__(self):
        if not self.match_id or not self.player_id or not self.team_id:
            raise ValueError("PLAYER_FORM_IDENTITY_REQUIRED")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc, "KICKOFF"))
        object.__setattr__(self, "available_at_utc", _utc(self.available_at_utc, "AVAILABILITY"))
        if self.available_at_utc < self.kickoff_utc:
            raise ValueError("PLAYER_FORM_RESULT_AVAILABLE_BEFORE_KICKOFF")
        if not isinstance(self.quality_state, str) or not self.quality_state.strip():
            raise ValueError("PLAYER_FORM_QUALITY_STATE_REQUIRED")
        copied = dict(self.metrics)
        unknown = set(copied) - set(_METRICS)
        if unknown:
            raise ValueError("PLAYER_FORM_UNKNOWN_METRIC")
        for key, value in copied.items():
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"PLAYER_FORM_INVALID_METRIC:{key}")
            if not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"PLAYER_FORM_INVALID_METRIC:{key}")
            if key not in {"minutes_played", "xg", "npxg", "xa"} and type(value) is not int:
                raise ValueError(f"PLAYER_FORM_NON_INTEGER_COUNT:{key}")
        if copied.get("minutes_played") is not None and copied["minutes_played"] > 150:
            raise ValueError("PLAYER_FORM_MINUTES_OUT_OF_RANGE")
        if any(copied.get(key) is not None for key in ("xg", "npxg")) and not (self.xg_model_id or "").strip():
            raise ValueError("PLAYER_FORM_XG_MODEL_ID_REQUIRED")
        if copied.get("xa") is not None and not (self.xa_model_id or "").strip():
            raise ValueError("PLAYER_FORM_XA_MODEL_ID_REQUIRED")
        if self.started is not None and type(self.started) is not bool:
            raise ValueError("PLAYER_FORM_STARTER_FLAG_INVALID")
        object.__setattr__(self, "metrics", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class PlayerFormFeatures:
    player_id: str
    cutoff_utc: datetime
    matches_used: int
    sample_state: str
    minutes_avg: float | None
    starts_rate: float | None
    goals_per90: float | None
    shots_per90: float | None
    xg_per90: float | None
    npxg_per90: float | None
    xa_per90: float | None
    xg_model_id: str | None
    xa_model_id: str | None
    source_match_ids: tuple[str, ...]


def build_player_form(
    evidence: Sequence[PlayerMatchEvidence],
    *,
    player_id: str,
    cutoff_utc: datetime,
    last_n: int = 5,
) -> PlayerFormFeatures:
    cutoff = _utc(cutoff_utc, "CUTOFF")
    if not player_id or type(last_n) is not int or not 1 <= last_n <= 20:
        raise ValueError("PLAYER_FORM_WINDOW_INVALID")
    eligible = []
    seen = set()
    for row in evidence:
        if row.player_id != player_id or row.quality_state != "eligible_for_research":
            continue
        if row.kickoff_utc >= cutoff or row.available_at_utc > cutoff:
            continue
        if row.match_id in seen:
            raise ValueError("PLAYER_FORM_DUPLICATE_MATCH_EVIDENCE")
        seen.add(row.match_id)
        eligible.append(row)
    eligible.sort(key=lambda row: (row.kickoff_utc, row.match_id))
    selected = eligible[-last_n:]
    model_ids = {
        row.xg_model_id for row in selected
        if row.metrics.get("xg") is not None or row.metrics.get("npxg") is not None
    }
    if len(model_ids) > 1:
        raise ValueError("PLAYER_FORM_MIXED_XG_MODEL_IDENTITIES")
    model_id = next(iter(model_ids), None)
    xa_model_ids = {row.xa_model_id for row in selected if row.metrics.get("xa") is not None}
    if len(xa_model_ids) > 1:
        raise ValueError("PLAYER_FORM_MIXED_XA_MODEL_IDENTITIES")
    xa_model_id = next(iter(xa_model_ids), None)

    def total(key: str) -> float | None:
        values = [row.metrics.get(key) for row in selected]
        present = [float(value) for value in values if value is not None]
        return sum(present) if present else None

    minutes = total("minutes_played")
    minutes_present = [row.metrics.get("minutes_played") for row in selected if row.metrics.get("minutes_played") is not None]
    starts = [row.started for row in selected if row.started is not None]
    goals, shots = total("goals"), total("shots")
    xg, npxg, xa = total("xg"), total("npxg"), total("xa")
    minutes_sum = sum(float(v) for v in minutes_present)
    rate_base = minutes_sum / 90 if minutes_sum > 0 else None

    def per90(value: float | None) -> float | None:
        return value / rate_base if value is not None and rate_base else None

    return PlayerFormFeatures(
        player_id=player_id,
        cutoff_utc=cutoff,
        matches_used=len(selected),
        sample_state="low_sample" if len(selected) < 3 else "usable_research_sample",
        minutes_avg=(minutes_sum / len(minutes_present)) if minutes_present else None,
        starts_rate=(sum(starts) / len(starts)) if starts else None,
        goals_per90=per90(goals),
        shots_per90=per90(shots),
        xg_per90=per90(xg),
        npxg_per90=per90(npxg),
        xa_per90=per90(xa),
        xg_model_id=model_id,
        xa_model_id=xa_model_id,
        source_match_ids=tuple(row.match_id for row in selected),
    )
