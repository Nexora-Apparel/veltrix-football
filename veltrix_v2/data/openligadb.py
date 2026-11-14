"""Offline OpenLigaDB response parser.

This module accepts archived response bytes only. It performs no HTTP, database,
secret, quota, scheduling or provider-dispatch operations. Provider update
metadata is preserved as update metadata and is never promoted to publication
or availability time. Parsed rows are not PIT-certified observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any


def _aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _integer(value: object, *, minimum: int = 0) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        return None
    return value


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


@dataclass(frozen=True, slots=True)
class OpenLigaDBResult:
    result_type_id: int | None
    result_type_kind: str | None
    result_name: str | None
    result_order_id: int | None
    points: int


@dataclass(frozen=True, slots=True)
class OpenLigaDBMatch:
    provider_match_id: int
    provider_league_id: int
    league_shortcut: str | None
    league_name: str | None
    league_season: int | None
    kickoff_at: datetime
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    match_is_finished: bool
    provider_update_at: datetime | None
    results: tuple[OpenLigaDBResult, ...]
    retrieved_at: datetime
    raw_response_sha256: str


@dataclass(frozen=True, slots=True)
class OpenLigaDBRejectedRow:
    row_index: int
    provider_match_id: int | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class OpenLigaDBParseReport:
    raw_response_sha256: str
    retrieved_at: datetime
    matches: tuple[OpenLigaDBMatch, ...]
    rejected_rows: tuple[OpenLigaDBRejectedRow, ...]
    root_error: str | None = None

    @property
    def accepted_count(self) -> int:
        return len(self.matches)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_rows)


def _parse_result_rows(value: object) -> tuple[OpenLigaDBResult, ...] | None:
    if value is None:
        return ()
    if not isinstance(value, list):
        return None
    parsed: list[OpenLigaDBResult] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        points = _integer(item.get("points"))
        if points is None:
            return None
        result_type_id = item.get("resultTypeID")
        if result_type_id is not None and _integer(result_type_id) is None:
            return None
        result_order_id = item.get("resultOrderID")
        if result_order_id is not None and _integer(result_order_id) is None:
            return None
        kind = item.get("resultTypeKind")
        name = item.get("resultName")
        if kind is not None and _text(kind) is None:
            return None
        if name is not None and _text(name) is None:
            return None
        parsed.append(OpenLigaDBResult(
            result_type_id=result_type_id,
            result_type_kind=_text(kind),
            result_name=_text(name),
            result_order_id=result_order_id,
            points=points,
        ))
    return tuple(parsed)


def _parse_match(
    item: object, *, row_index: int, retrieved_at: datetime, raw_hash: str
) -> OpenLigaDBMatch | OpenLigaDBRejectedRow:
    if not isinstance(item, dict):
        return OpenLigaDBRejectedRow(row_index, None, "MATCH_ROW_NOT_OBJECT")

    match_id = _integer(item.get("matchID"), minimum=1)
    if match_id is None:
        return OpenLigaDBRejectedRow(row_index, None, "MATCH_ID_INVALID")

    league_id = _integer(item.get("leagueId"), minimum=1)
    home = item.get("team1")
    away = item.get("team2")
    if league_id is None:
        return OpenLigaDBRejectedRow(row_index, match_id, "LEAGUE_ID_INVALID")
    if not isinstance(home, dict) or not isinstance(away, dict):
        return OpenLigaDBRejectedRow(row_index, match_id, "TEAM_OBJECT_MISSING")

    home_id = _integer(home.get("teamId"), minimum=1)
    away_id = _integer(away.get("teamId"), minimum=1)
    home_name = _text(home.get("teamName"))
    away_name = _text(away.get("teamName"))
    if None in (home_id, away_id, home_name, away_name) or home_id == away_id:
        return OpenLigaDBRejectedRow(row_index, match_id, "TEAM_IDENTITY_INVALID")

    kickoff = _aware_datetime(item.get("matchDateTimeUTC"))
    if kickoff is None:
        return OpenLigaDBRejectedRow(row_index, match_id, "UTC_KICKOFF_MISSING_OR_UNTRUSTED")

    finished = item.get("matchIsFinished")
    if type(finished) is not bool:
        return OpenLigaDBRejectedRow(row_index, match_id, "FINISHED_FLAG_INVALID")

    results = _parse_result_rows(item.get("matchResults"))
    if results is None:
        return OpenLigaDBRejectedRow(row_index, match_id, "RESULT_ROWS_INVALID")

    season = item.get("leagueSeason")
    if season is not None and _integer(season, minimum=1) is None:
        return OpenLigaDBRejectedRow(row_index, match_id, "LEAGUE_SEASON_INVALID")

    return OpenLigaDBMatch(
        provider_match_id=match_id,
        provider_league_id=league_id,
        league_shortcut=_text(item.get("leagueShortcut")),
        league_name=_text(item.get("leagueName")),
        league_season=season,
        kickoff_at=kickoff,
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        match_is_finished=finished,
        provider_update_at=_aware_datetime(item.get("lastUpdateDateTime")),
        results=results,
        retrieved_at=retrieved_at,
        raw_response_sha256=raw_hash,
    )


def parse_openligadb_response(
    raw_response: bytes, *, retrieved_at: datetime
) -> OpenLigaDBParseReport:
    """Parse one exact archived API response; never infer publication time.

    The API's lastUpdateDateTime is exposed as provider_update_at only. It is
    not source_published_at, available_at, or proof of revision completeness.
    All parsed matches remain unapproved and non-certifiable until independently
    crosswalked and passed through the generic rights/temporal evidence capture.
    """
    if not isinstance(raw_response, bytes):
        raise TypeError("RAW_RESPONSE_MUST_BE_BYTES")
    if not isinstance(retrieved_at, datetime) or retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("RETRIEVED_AT_MUST_BE_TIMEZONE_AWARE")

    raw_hash = sha256(raw_response).hexdigest()
    try:
        decoded = raw_response.decode("utf-8")
        payload: Any = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return OpenLigaDBParseReport(raw_hash, retrieved_at, (), (), "JSON_DECODE_FAILED")

    if not isinstance(payload, list):
        return OpenLigaDBParseReport(raw_hash, retrieved_at, (), (), "ROOT_MUST_BE_ARRAY")

    parsed_rows = [
        _parse_match(row, row_index=index, retrieved_at=retrieved_at, raw_hash=raw_hash)
        for index, row in enumerate(payload)
    ]

    id_counts: dict[int, int] = {}
    for row in parsed_rows:
        if isinstance(row, OpenLigaDBMatch):
            id_counts[row.provider_match_id] = id_counts.get(row.provider_match_id, 0) + 1

    accepted: list[OpenLigaDBMatch] = []
    rejected: list[OpenLigaDBRejectedRow] = []
    for row_index, row in enumerate(parsed_rows):
        if isinstance(row, OpenLigaDBRejectedRow):
            rejected.append(row)
        elif id_counts[row.provider_match_id] > 1:
            rejected.append(OpenLigaDBRejectedRow(
                row_index=row_index,
                provider_match_id=row.provider_match_id,
                reason_code="DUPLICATE_PROVIDER_MATCH_ID",
            ))
        else:
            accepted.append(row)

    return OpenLigaDBParseReport(
        raw_response_sha256=raw_hash,
        retrieved_at=retrieved_at,
        matches=tuple(accepted),
        rejected_rows=tuple(sorted(rejected, key=lambda row: row.row_index)),
    )
