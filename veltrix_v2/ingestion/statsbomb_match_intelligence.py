"""StatsBomb-specific match intelligence aggregation.

Metrics retain StatsBomb event semantics and xG provenance. This module does not
claim provider-equivalent PPDA, tactical labels, UTC availability, or lineup state.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from .statsbomb_events import StatsBombEvent


_DEFENSIVE_ACTIONS = frozenset({
    "Ball Recovery", "Block", "Clearance", "Interception", "Tackle",
})


def _freeze_nested(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze_nested(v) for k, v in value.items()})
    return value


@dataclass(frozen=True, slots=True)
class TeamMatchIntelligence:
    team_id: int
    team_name: str
    shots: int
    shots_on_target: int
    goals_from_shots: int
    statsbomb_xg: float | None
    statsbomb_xg_model_id: str
    shot_outcomes: Mapping[str, int]
    possessions_won_or_started: int
    play_patterns: Mapping[str, int]
    under_pressure_events: int
    counterpress_events: int
    defensive_actions: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class StatsBombMatchIntelligence:
    match_id: str
    event_count: int
    team_metrics: Mapping[int, TeamMatchIntelligence]
    possession_count: int
    possession_team_counts: Mapping[int, int]
    source: str = "statsbomb-open-data"
    xg_model_id: str = "statsbomb-open-data:shot.statsbomb_xg"
    metric_semantics: str = "statsbomb_event_aggregates_not_provider_normalized"


def aggregate_match(events: Sequence[StatsBombEvent]) -> StatsBombMatchIntelligence:
    """Aggregate one complete, ordered match event sequence.

    Input completeness cannot be inferred here; callers must gate on match metadata
    and declared event coverage before using these aggregates in research.
    """
    if not isinstance(events, (list, tuple)) or not events:
        raise ValueError("STATSBOMB_MATCH_EVENTS_REQUIRED")
    match_ids = {event.match_id for event in events}
    if len(match_ids) != 1:
        raise ValueError("STATSBOMB_MIXED_MATCH_IDS")
    if [e.event_index for e in events] != sorted(e.event_index for e in events):
        raise ValueError("STATSBOMB_EVENTS_NOT_ORDERED")
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("STATSBOMB_DUPLICATE_EVENT_ID")
    if len({e.event_index for e in events}) != len(events):
        raise ValueError("STATSBOMB_DUPLICATE_EVENT_INDEX")

    teams: dict[int, dict] = {}
    possession_owners: dict[int, int] = {}
    possession_counts: Counter[int] = Counter()

    def team_bucket(team_id: int, team_name: str) -> dict:
        current = teams.get(team_id)
        if current is None:
            current = {
                "name": team_name, "shots": 0, "on_target": 0, "goals": 0,
                "xg": 0.0, "xg_count": 0, "outcomes": Counter(),
                "possessions": 0, "patterns": Counter(), "pressure": 0,
                "counterpress": 0, "defensive": Counter(),
            }
            teams[team_id] = current
        elif current["name"] != team_name:
            raise ValueError("STATSBOMB_TEAM_ID_NAME_CONFLICT")
        return current

    for event in events:
        if event.possession is not None and event.possession_team_id is not None:
            owner = possession_owners.setdefault(event.possession, event.possession_team_id)
            if owner != event.possession_team_id:
                raise ValueError("STATSBOMB_POSSESSION_OWNER_CONFLICT")
            possession_counts[event.possession] += 1
            if event.possession_team_name:
                bucket = team_bucket(event.possession_team_id, event.possession_team_name)
                # Count a possession once, not once per event.
                if possession_counts[event.possession] == 1:
                    bucket["possessions"] += 1
                if event.play_pattern_name:
                    bucket["patterns"][event.play_pattern_name] += 1

        if event.team_id is None or not event.team_name:
            continue
        bucket = team_bucket(event.team_id, event.team_name)
        if event.under_pressure is True:
            bucket["pressure"] += 1
        if event.counterpress is True:
            bucket["counterpress"] += 1
        if event.event_type_name in _DEFENSIVE_ACTIONS:
            bucket["defensive"][event.event_type_name] += 1

        if event.event_type_name == "Shot":
            bucket["shots"] += 1
            shot = event.raw_attributes.get("shot", {})
            if not isinstance(shot, Mapping):
                raise ValueError("STATSBOMB_SHOT_ATTRIBUTES_INVALID")
            outcome = shot.get("outcome", {})
            outcome_name = outcome.get("name") if isinstance(outcome, Mapping) else None
            if outcome_name:
                bucket["outcomes"][str(outcome_name)] += 1
                if outcome_name == "Goal":
                    bucket["goals"] += 1
                if outcome_name in {"Goal", "Saved", "Saved to Post"}:
                    bucket["on_target"] += 1
            raw_xg = shot.get("statsbomb_xg")
            if raw_xg is not None:
                if isinstance(raw_xg, bool) or not isinstance(raw_xg, (int, float)):
                    raise ValueError("STATSBOMB_XG_INVALID")
                if not math.isfinite(float(raw_xg)) or not 0 <= float(raw_xg) <= 1:
                    raise ValueError("STATSBOMB_XG_OUT_OF_RANGE")
                bucket["xg"] += float(raw_xg)
                bucket["xg_count"] += 1

    result = {}
    for team_id, data in teams.items():
        result[team_id] = TeamMatchIntelligence(
            team_id=team_id,
            team_name=data["name"],
            shots=data["shots"],
            shots_on_target=data["on_target"],
            goals_from_shots=data["goals"],
            statsbomb_xg=data["xg"] if data["xg_count"] else None,
            statsbomb_xg_model_id="statsbomb-open-data:shot.statsbomb_xg",
            shot_outcomes=MappingProxyType(dict(data["outcomes"])),
            possessions_won_or_started=data["possessions"],
            play_patterns=MappingProxyType(dict(data["patterns"])),
            under_pressure_events=data["pressure"],
            counterpress_events=data["counterpress"],
            defensive_actions=MappingProxyType(dict(data["defensive"])),
        )
    return StatsBombMatchIntelligence(
        match_id=next(iter(match_ids)),
        event_count=len(events),
        team_metrics=MappingProxyType(result),
        possession_count=len(possession_owners),
        possession_team_counts=MappingProxyType(dict(Counter(possession_owners.values()))),
    )
