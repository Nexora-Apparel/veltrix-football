"""Lossless StatsBomb Open Data event adapter.

Preserves StatsBomb's event identity and nested event-specific attributes. Match-clock
timestamps are not UTC wall-clock timestamps. This module performs no metric inference,
xG conversion, rights approval, database write or prediction calculation.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
from uuid import UUID


_CLOCK = re.compile(r"^(?P<h>\d{2}):(?P<m>[0-5]\d):(?P<s>[0-5]\d)(?:\.(?P<ms>\d{1,3}))?$")
_PERIODS = frozenset({1, 2, 3, 4, 5})


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    return value


def _object_id_name(value, field: str) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise ValueError(f"STATSBOMB_INVALID_OBJECT:{field}")
    raw_id, raw_name = value.get("id"), value.get("name")
    if raw_id is not None and (isinstance(raw_id, bool) or not isinstance(raw_id, int)):
        raise ValueError(f"STATSBOMB_INVALID_OBJECT_ID:{field}")
    if raw_name is not None and (not isinstance(raw_name, str) or not raw_name.strip()):
        raise ValueError(f"STATSBOMB_INVALID_OBJECT_NAME:{field}")
    return raw_id, raw_name


def _clock_ms(value: object) -> int:
    if not isinstance(value, str):
        raise ValueError("STATSBOMB_EVENT_TIMESTAMP_REQUIRED")
    match = _CLOCK.fullmatch(value)
    if not match:
        raise ValueError("STATSBOMB_INVALID_EVENT_TIMESTAMP")
    parts = match.groupdict()
    fraction = (parts["ms"] or "").ljust(3, "0")[:3]
    return (
        int(parts["h"]) * 3_600_000
        + int(parts["m"]) * 60_000
        + int(parts["s"]) * 1_000
        + int(fraction or 0)
    )


@dataclass(frozen=True, slots=True)
class StatsBombEvent:
    event_id: str
    match_id: str
    event_index: int
    period: int
    timestamp_match_ms: int
    timestamp_match_raw: str
    minute: int | None
    second: int | None
    event_type_id: int | None
    event_type_name: str
    possession: int | None
    possession_team_id: int | None
    possession_team_name: str | None
    team_id: int | None
    team_name: str | None
    player_id: int | None
    player_name: str | None
    play_pattern_id: int | None
    play_pattern_name: str | None
    location: tuple[float, float] | None
    under_pressure: bool | None
    counterpress: bool | None
    raw_attributes: Mapping[str, object]
    payload_sha256: str
    source: str = "statsbomb-open-data"
    schema_spec: str = "StatsBomb Open Data Specification v1.1"
    timestamp_semantics: str = "match_clock_not_utc"

    def __post_init__(self):
        object.__setattr__(self, "raw_attributes", _freeze(dict(self.raw_attributes)))


def adapt_event(row: Mapping[str, object], *, match_id: str) -> StatsBombEvent:
    if not isinstance(row, Mapping):
        raise ValueError("STATSBOMB_EVENT_MUST_BE_MAPPING")
    if not isinstance(match_id, str) or not match_id.strip():
        raise ValueError("STATSBOMB_MATCH_ID_REQUIRED")

    raw_id = row.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ValueError("STATSBOMB_EVENT_ID_REQUIRED")
    try:
        event_id = str(UUID(raw_id))
    except (ValueError, AttributeError):
        raise ValueError("STATSBOMB_EVENT_ID_MUST_BE_UUID") from None

    index, period = row.get("index"), row.get("period")
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise ValueError("STATSBOMB_EVENT_INDEX_INVALID")
    if isinstance(period, bool) or not isinstance(period, int) or period not in _PERIODS:
        raise ValueError("STATSBOMB_EVENT_PERIOD_INVALID")

    timestamp = row.get("timestamp")
    elapsed = _clock_ms(timestamp)
    minute, second = row.get("minute"), row.get("second")
    if minute is not None and (type(minute) is not int or minute < 0):
        raise ValueError("STATSBOMB_EVENT_MINUTE_INVALID")
    if second is not None and (type(second) is not int or not 0 <= second <= 59):
        raise ValueError("STATSBOMB_EVENT_SECOND_INVALID")

    type_id, type_name = _object_id_name(row.get("type"), "type")
    if not type_name:
        raise ValueError("STATSBOMB_EVENT_TYPE_NAME_REQUIRED")
    possession = row.get("possession")
    if possession is not None and (type(possession) is not int or possession < 1):
        raise ValueError("STATSBOMB_POSSESSION_INVALID")

    possession_team_id, possession_team_name = _object_id_name(row.get("possession_team"), "possession_team")
    team_id, team_name = _object_id_name(row.get("team"), "team")
    player_id, player_name = _object_id_name(row.get("player"), "player")
    pattern_id, pattern_name = _object_id_name(row.get("play_pattern"), "play_pattern")

    location_raw = row.get("location")
    location = None
    if location_raw is not None:
        if (not isinstance(location_raw, (list, tuple)) or len(location_raw) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v))
                       for v in location_raw)):
            raise ValueError("STATSBOMB_LOCATION_INVALID")
        x, y = float(location_raw[0]), float(location_raw[1])
        if not (0 <= x <= 120 and 0 <= y <= 80):
            raise ValueError("STATSBOMB_LOCATION_OUT_OF_BOUNDS")
        location = (x, y)

    for flag in ("under_pressure", "counterpress"):
        if flag in row and row[flag] is not None and type(row[flag]) is not bool:
            raise ValueError(f"STATSBOMB_{flag.upper()}_INVALID")

    canonical = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    known = {
        "id", "index", "period", "timestamp", "minute", "second", "type",
        "possession", "possession_team", "team", "player", "play_pattern",
        "location", "under_pressure", "counterpress",
    }
    extras = {key: value for key, value in row.items() if key not in known}
    return StatsBombEvent(
        event_id=event_id,
        match_id=match_id.strip(),
        event_index=index,
        period=period,
        timestamp_match_ms=elapsed,
        timestamp_match_raw=timestamp,
        minute=minute,
        second=second,
        event_type_id=type_id,
        event_type_name=type_name,
        possession=possession,
        possession_team_id=possession_team_id,
        possession_team_name=possession_team_name,
        team_id=team_id,
        team_name=team_name,
        player_id=player_id,
        player_name=player_name,
        play_pattern_id=pattern_id,
        play_pattern_name=pattern_name,
        location=location,
        under_pressure=row.get("under_pressure"),
        counterpress=row.get("counterpress"),
        raw_attributes=extras,
        payload_sha256=digest,
    )


def adapt_event_file(rows: object, *, match_id: str) -> tuple[StatsBombEvent, ...]:
    if not isinstance(rows, list):
        raise ValueError("STATSBOMB_EVENT_FILE_MUST_BE_ARRAY")
    events = tuple(adapt_event(row, match_id=match_id) for row in rows)
    ids = [event.event_id for event in events]
    indexes = [event.event_index for event in events]
    if len(ids) != len(set(ids)):
        raise ValueError("STATSBOMB_DUPLICATE_EVENT_ID")
    if len(indexes) != len(set(indexes)):
        raise ValueError("STATSBOMB_DUPLICATE_EVENT_INDEX")
    if indexes != sorted(indexes):
        raise ValueError("STATSBOMB_EVENT_ORDER_INVALID")
    return events
