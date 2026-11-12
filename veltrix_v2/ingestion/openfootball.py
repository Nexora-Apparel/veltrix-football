"""Read-only OpenFootball JSON parser with explicit timestamp precision.

OpenFootball records often carry a local date and optional local clock time without
an IANA timezone. This module deliberately does not manufacture UTC timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class OpenFootballMatch:
    source_index: int
    round_name: str | None
    match_date: date
    local_time: time | None
    home_name: str
    away_name: str
    full_time_home: int | None
    full_time_away: int | None
    half_time_home: int | None
    half_time_away: int | None
    timestamp_precision: str
    raw_date: str
    raw_time: str | None

    @property
    def has_full_time_score(self) -> bool:
        return self.full_time_home is not None and self.full_time_away is not None


def _score_pair(value: object, field: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError(f"{field} must be a two-element score array")
    home, away = value
    if type(home) is not int or type(away) is not int or home < 0 or away < 0:
        raise ValueError(f"{field} scores must be non-negative integers")
    return home, away


def parse_match(raw: Mapping[str, Any], source_index: int) -> OpenFootballMatch:
    raw_date = raw.get("date")
    if not isinstance(raw_date, str):
        raise ValueError("match date is required as an ISO date string")
    match_date = date.fromisoformat(raw_date)
    raw_time = raw.get("time")
    local_time = time.fromisoformat(raw_time) if isinstance(raw_time, str) and raw_time else None
    home, away = raw.get("team1"), raw.get("team2")
    if not isinstance(home, str) or not home.strip() or not isinstance(away, str) or not away.strip():
        raise ValueError("both team names are required")
    score = raw.get("score") or {}
    if not isinstance(score, Mapping):
        raise ValueError("score must be an object")
    ft = _score_pair(score.get("ft"), "score.ft")
    ht = _score_pair(score.get("ht"), "score.ht")
    return OpenFootballMatch(
        source_index=source_index,
        round_name=raw.get("round") if isinstance(raw.get("round"), str) else None,
        match_date=match_date,
        local_time=local_time,
        home_name=home.strip(),
        away_name=away.strip(),
        full_time_home=ft[0] if ft else None,
        full_time_away=ft[1] if ft else None,
        half_time_home=ht[0] if ht else None,
        half_time_away=ht[1] if ht else None,
        timestamp_precision=(
            "date_only" if local_time is None
            else "local_datetime_with_utc_offset" if local_time.utcoffset() is not None
            else "local_datetime_unzoned"
        ),
        raw_date=raw_date,
        raw_time=raw_time if isinstance(raw_time, str) else None,
    )


def parse_dataset(payload: Mapping[str, Any]) -> tuple[str, tuple[OpenFootballMatch, ...]]:
    name = payload.get("name")
    matches = payload.get("matches")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("dataset name is required")
    if not isinstance(matches, list):
        raise ValueError("dataset matches must be an array")
    parsed = tuple(parse_match(row, i) for i, row in enumerate(matches) if isinstance(row, Mapping))
    if len(parsed) != len(matches):
        raise ValueError("every dataset match must be an object")
    return name, parsed
