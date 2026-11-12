"""Rights-approved historical Wyscout shot-event adapter.

The source is the Pappalardo et al. (2019) Soccer Match Event Dataset,
released under CC BY 4.0. It is historical training data only, not a live
provider. The adapter preserves the source-observation ID and conservative
dataset availability time so point-in-time training can reject it for
pre-publication cutoffs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Iterable, Mapping

SOURCE_PROVIDER_ID = "wyscout_open_data"
SOURCE_LICENSE_ID = "cc-by-4.0-pappalardo-2019"
SOURCE_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
SOURCE_PUBLICATION_DATE = datetime(2019, 10, 28, tzinfo=timezone.utc).date()
CONSERVATIVE_AVAILABLE_AT_UTC = datetime(2019, 11, 1, tzinfo=timezone.utc)
ATTRIBUTION = (
    "Shot-event training data: Pappalardo et al. (2019), Wyscout Soccer Match Event Dataset, "
    "CC BY 4.0 — https://doi.org/10.1038/s41597-019-0247-7 "
    "(adapted for the VELTRIX xG model)."
)

_PERIOD_OFFSETS_SECONDS = {
    "1H": 0,
    "2H": 45 * 60,
    "E1": 90 * 60,
    "E2": 105 * 60,
}
_BODY_PART_TAGS = {
    401: "LEFT_FOOT",
    402: "RIGHT_FOOT",
    403: "HEAD_OR_BODY",
}
_GOAL_ZONE_TAGS = {
    1201: "GOAL_LOW_CENTRE",
    1202: "GOAL_LOW_RIGHT",
    1203: "GOAL_MID_CENTRE",
    1204: "GOAL_MID_LEFT",
    1205: "GOAL_LOW_LEFT",
    1206: "GOAL_MID_RIGHT",
    1207: "GOAL_HIGH_CENTRE",
    1208: "GOAL_HIGH_LEFT",
    1209: "GOAL_HIGH_RIGHT",
    1210: "OUT_LOW_RIGHT",
    1211: "OUT_MID_LEFT",
    1212: "OUT_LOW_LEFT",
    1213: "OUT_MID_RIGHT",
    1214: "OUT_HIGH_CENTRE",
    1215: "OUT_HIGH_LEFT",
    1216: "OUT_HIGH_RIGHT",
    1217: "POST_LOW_RIGHT",
    1218: "POST_MID_LEFT",
    1219: "POST_LOW_LEFT",
    1220: "POST_MID_RIGHT",
    1221: "POST_HIGH_CENTRE",
    1222: "POST_HIGH_LEFT",
    1223: "POST_HIGH_RIGHT",
}


def _aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"WYSCOUT_{field.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class WyscoutShotTrainingExample:
    match_id: str
    event_id: str
    competition_key: str
    season: str
    team_id: str
    player_id: str | None
    match_period: str
    event_time_utc: datetime
    event_seconds_in_period: float
    shot_x_pct: float
    shot_y_pct: float
    goal: bool
    body_part: str | None
    goal_zone: str | None
    is_penalty: bool
    is_direct_free_kick: bool
    is_counterattack: bool
    is_opportunity: bool
    is_blocked: bool
    raw_tag_ids: tuple[int, ...]
    source_observation_id: str
    source_available_at_utc: datetime
    source_provider_id: str = SOURCE_PROVIDER_ID
    source_license_id: str = SOURCE_LICENSE_ID
    source_license_url: str = SOURCE_LICENSE_URL

    def __post_init__(self) -> None:
        for field in ("match_id", "event_id", "competition_key", "season", "team_id", "source_observation_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"WYSCOUT_{field.upper()}_REQUIRED")
        object.__setattr__(self, "event_time_utc", _aware_utc(self.event_time_utc, "event_time_utc"))
        object.__setattr__(
            self, "source_available_at_utc",
            _aware_utc(self.source_available_at_utc, "source_available_at_utc"),
        )
        if self.source_available_at_utc < CONSERVATIVE_AVAILABLE_AT_UTC:
            raise ValueError("WYSCOUT_SOURCE_AVAILABILITY_PRECEDES_CONSERVATIVE_RELEASE_DATE")
        if self.event_time_utc > self.source_available_at_utc:
            raise ValueError("WYSCOUT_EVENT_AFTER_SOURCE_AVAILABILITY")
        for field in ("event_seconds_in_period", "shot_x_pct", "shot_y_pct"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
                raise ValueError(f"WYSCOUT_{field.upper()}_INVALID")
        if self.event_seconds_in_period < 0:
            raise ValueError("WYSCOUT_EVENT_SECONDS_NEGATIVE")
        if not 0 <= self.shot_x_pct <= 100 or not 0 <= self.shot_y_pct <= 100:
            raise ValueError("WYSCOUT_SHOT_COORDINATES_OUT_OF_RANGE")
        if type(self.goal) is not bool or any(type(getattr(self, field)) is not bool for field in (
            "is_penalty", "is_direct_free_kick", "is_counterattack", "is_opportunity", "is_blocked",
        )):
            raise ValueError("WYSCOUT_SHOT_FLAGS_MUST_BE_BOOLEAN")
        if self.source_provider_id != SOURCE_PROVIDER_ID or self.source_license_id != SOURCE_LICENSE_ID:
            raise ValueError("WYSCOUT_SOURCE_LICENSE_IDENTITY_MISMATCH")
        object.__setattr__(self, "raw_tag_ids", tuple(self.raw_tag_ids))


def parse_wyscout_shot_events(
    payload: Mapping[str, object] | Iterable[Mapping[str, object]],
    *,
    competition_key: str,
    season: str,
    match_kickoff_utc: datetime,
    source_available_at_utc: datetime,
    source_observation_id: str,
) -> tuple[WyscoutShotTrainingExample, ...]:
    """Parse shot and direct-set-piece attempts from one Wyscout match payload.

    Coordinates are Wyscout percentages in the attacking direction: x=100 is
    the opponent goal. Penalty shoot-outs are excluded from regulation xG.
    """
    kickoff = _aware_utc(match_kickoff_utc, "match_kickoff_utc")
    available = _aware_utc(source_available_at_utc, "source_available_at_utc")
    if available < CONSERVATIVE_AVAILABLE_AT_UTC:
        raise ValueError("WYSCOUT_SOURCE_AVAILABILITY_PRECEDES_CONSERVATIVE_RELEASE_DATE")
    if available < kickoff:
        raise ValueError("WYSCOUT_SOURCE_AVAILABLE_BEFORE_MATCH_KICKOFF")
    if not source_observation_id or not source_observation_id.strip():
        raise ValueError("WYSCOUT_SOURCE_OBSERVATION_ID_REQUIRED")
    if not competition_key.strip() or not season.strip():
        raise ValueError("WYSCOUT_COMPETITION_AND_SEASON_REQUIRED")

    if isinstance(payload, Mapping):
        raw_events = payload.get("events")
    else:
        raw_events = payload
    if not isinstance(raw_events, Iterable) or isinstance(raw_events, (str, bytes, Mapping)):
        raise ValueError("WYSCOUT_EVENTS_ARRAY_REQUIRED")

    output: list[WyscoutShotTrainingExample] = []
    seen_event_ids: set[str] = set()
    for event in raw_events:
        if not isinstance(event, Mapping):
            raise ValueError("WYSCOUT_EVENT_RECORD_INVALID")
        event_name = str(event.get("eventName") or "").strip().casefold()
        sub_event_name = str(event.get("subEventName") or "").strip().casefold()
        is_penalty = event_name == "free kick" and "penalty" in sub_event_name
        is_direct_free_kick = event_name == "free kick" and "free kick shot" in sub_event_name
        if event_name != "shot" and not is_penalty and not is_direct_free_kick:
            continue

        period = str(event.get("matchPeriod") or "").strip().upper()
        if period == "P":
            continue
        if period not in _PERIOD_OFFSETS_SECONDS:
            raise ValueError(f"WYSCOUT_SHOT_PERIOD_UNSUPPORTED:{period or 'missing'}")
        event_seconds = event.get("eventSec")
        if isinstance(event_seconds, bool) or not isinstance(event_seconds, (int, float)) or not isfinite(float(event_seconds)):
            raise ValueError("WYSCOUT_SHOT_EVENT_SECONDS_INVALID")
        if event_seconds < 0:
            raise ValueError("WYSCOUT_SHOT_EVENT_SECONDS_NEGATIVE")

        positions = event.get("positions")
        if not isinstance(positions, list) or not positions or not isinstance(positions[0], Mapping):
            raise ValueError("WYSCOUT_SHOT_START_POSITION_REQUIRED")
        position = positions[0]
        x = position.get("x")
        y = position.get("y")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)) for value in (x, y)):
            raise ValueError("WYSCOUT_SHOT_COORDINATES_INVALID")
        if not 0 <= float(x) <= 100 or not 0 <= float(y) <= 100:
            raise ValueError("WYSCOUT_SHOT_COORDINATES_OUT_OF_RANGE")

        tags = event.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError("WYSCOUT_SHOT_TAGS_INVALID")
        tag_ids = []
        for tag in tags:
            if not isinstance(tag, Mapping) or type(tag.get("id")) is not int:
                raise ValueError("WYSCOUT_SHOT_TAG_RECORD_INVALID")
            tag_ids.append(tag["id"])
        tag_set = set(tag_ids)

        event_id = event.get("id")
        match_id = event.get("matchId")
        team_id = event.get("teamId")
        player_id = event.get("playerId")
        if event_id is None or match_id is None or team_id is None:
            raise ValueError("WYSCOUT_SHOT_IDENTITY_REQUIRED")
        event_key = str(event_id)
        if event_key in seen_event_ids:
            raise ValueError("WYSCOUT_DUPLICATE_SHOT_EVENT_ID")
        seen_event_ids.add(event_key)

        event_time = kickoff + timedelta(
            seconds=_PERIOD_OFFSETS_SECONDS[period] + float(event_seconds)
        )
        if event_time > available:
            raise ValueError("WYSCOUT_SHOT_EVENT_AFTER_SOURCE_AVAILABILITY")

        output.append(WyscoutShotTrainingExample(
            match_id=str(match_id),
            event_id=event_key,
            competition_key=competition_key,
            season=season,
            team_id=str(team_id),
            player_id=str(player_id) if player_id is not None else None,
            match_period=period,
            event_time_utc=event_time,
            event_seconds_in_period=float(event_seconds),
            shot_x_pct=float(x),
            shot_y_pct=float(y),
            goal=101 in tag_set,
            body_part=next((_BODY_PART_TAGS[tag] for tag in _BODY_PART_TAGS if tag in tag_set), None),
            goal_zone=next((_GOAL_ZONE_TAGS[tag] for tag in _GOAL_ZONE_TAGS if tag in tag_set), None),
            is_penalty=is_penalty,
            is_direct_free_kick=is_direct_free_kick,
            is_counterattack=1901 in tag_set,
            is_opportunity=201 in tag_set,
            is_blocked=2101 in tag_set,
            raw_tag_ids=tuple(sorted(tag_set)),
            source_observation_id=source_observation_id,
            source_available_at_utc=available,
        ))
    return tuple(output)
