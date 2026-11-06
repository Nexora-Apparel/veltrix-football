"""Typed 5Dollar fixture extraction preserving provider IDs and settlement status."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256

from veltrix_v2.identity.registry import ProviderFixtureSourceIdentity
from veltrix_v2.ingestion.ports import RawProviderRecord


class FiveDollarFixtureStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    IN_PLAY = "IN_PLAY"
    FINISHED = "FINISHED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class FiveDollarFixtureRecord:
    source_identity: ProviderFixtureSourceIdentity
    status: FiveDollarFixtureStatus
    raw_status: str
    home_team_name: str
    away_team_name: str
    competition_name: str
    completed_home_goals: int | None
    completed_away_goals: int | None
    status_reason: str | None
    status_code: str | None
    raw_payload_sha256: str

    @property
    def is_settled_result(self) -> bool:
        return (
            self.status is FiveDollarFixtureStatus.FINISHED
            and self.completed_home_goals is not None
            and self.completed_away_goals is not None
        )


def _parse_kickoff(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("FIXTURE_KICKOFF_MISSING")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("FIXTURE_KICKOFF_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("FIXTURE_KICKOFF_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _completed_score(goals: object) -> tuple[int | None, int | None]:
    if not isinstance(goals, dict):
        return None, None
    home, away = goals.get("home"), goals.get("away")
    if (
        isinstance(home, bool) or isinstance(away, bool)
        or not isinstance(home, int) or not isinstance(away, int)
        or home < 0 or away < 0
    ):
        return None, None
    return home, away


def parse_fixture_record(raw: RawProviderRecord) -> FiveDollarFixtureRecord:
    """Extract one fixture from the exact provider response bytes.

    Unknown and incomplete results remain non-settled. The provider has no
    explicit postponed/cancelled statuses; do not invent them.
    """
    if raw.provider != "5DollarFootballAPI" or raw.data_class != "fixtures":
        raise ValueError("FIVEDOLLAR_FIXTURE_RECORD_PROVIDER_OR_CLASS_MISMATCH")
    if raw.provider_record_id != raw.provider_fixture_id:
        raise ValueError("PROVIDER_RECORD_FIXTURE_ID_MISMATCH")
    if not all((
        raw.provider_fixture_id,
        raw.provider_competition_id,
        raw.provider_home_team_id,
        raw.provider_away_team_id,
    )):
        raise ValueError("FIVEDOLLAR_FIXTURE_SOURCE_IDS_INCOMPLETE")
    try:
        payload = json.loads(raw.raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("FIVEDOLLAR_FIXTURE_RESPONSE_INVALID_JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("FIVEDOLLAR_FIXTURE_RESPONSE_SHAPE_INVALID")
    fixture = next(
        (
            item for item in payload["data"]
            if isinstance(item, dict) and str(item.get("id")) == raw.provider_fixture_id
        ),
        None,
    )
    if fixture is None:
        raise ValueError("PROVIDER_FIXTURE_ID_NOT_FOUND_IN_RAW_RESPONSE")

    league = fixture.get("league") if isinstance(fixture.get("league"), dict) else {}
    teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    if (
        str(league.get("id")) != raw.provider_competition_id
        or str(home.get("id")) != raw.provider_home_team_id
        or str(away.get("id")) != raw.provider_away_team_id
    ):
        raise ValueError("PROVIDER_FIXTURE_SOURCE_IDENTITY_MISMATCH")

    kickoff = _parse_kickoff(fixture.get("kickoff_utc"))
    kickoff_ts = fixture.get("kickoff_ts")
    if kickoff_ts is not None:
        try:
            seconds = int(kickoff_ts)
        except (TypeError, ValueError) as exc:
            raise ValueError("FIXTURE_KICKOFF_EPOCH_INVALID") from exc
        if abs(kickoff.timestamp() - seconds) > 1:
            raise ValueError("FIXTURE_KICKOFF_TIMESTAMP_CONFLICT")

    raw_status = str(fixture.get("status") or "unknown").casefold()
    status_map = {
        "scheduled": FiveDollarFixtureStatus.SCHEDULED,
        "in_play": FiveDollarFixtureStatus.IN_PLAY,
        "finished": FiveDollarFixtureStatus.FINISHED,
        "unknown": FiveDollarFixtureStatus.UNKNOWN,
    }
    status = status_map.get(raw_status, FiveDollarFixtureStatus.UNKNOWN)
    home_goals = away_goals = None
    status_reason = fixture.get("status_reason")
    if status is FiveDollarFixtureStatus.FINISHED:
        home_goals, away_goals = _completed_score(fixture.get("goals"))
        if home_goals is None or away_goals is None:
            status = FiveDollarFixtureStatus.UNKNOWN
            status_reason = "result_unconfirmed"
    source_identity = ProviderFixtureSourceIdentity(
        provider=raw.provider,
        source_id=raw.source_id,
        provider_fixture_id=raw.provider_fixture_id,
        provider_competition_id=raw.provider_competition_id,
        provider_home_team_id=raw.provider_home_team_id,
        provider_away_team_id=raw.provider_away_team_id,
        squad_category=None,
        kickoff_at_utc=kickoff,
    )
    return FiveDollarFixtureRecord(
        source_identity=source_identity,
        status=status,
        raw_status=raw_status,
        home_team_name=str(home.get("name") or ""),
        away_team_name=str(away.get("name") or ""),
        competition_name=str(league.get("name") or ""),
        completed_home_goals=home_goals,
        completed_away_goals=away_goals,
        status_reason=str(status_reason) if status_reason is not None else None,
        status_code=str(fixture.get("status_code")) if fixture.get("status_code") is not None else None,
        raw_payload_sha256=sha256(raw.raw_payload).hexdigest(),
    )
