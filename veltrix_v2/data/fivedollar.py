"""Strict, read-only 5Dollar historical fixture/result parser for Phase 2."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture

PROVIDER = "5DollarFootballAPI"
SOURCE_ID = "5dollarfootballapi"
AVAILABILITY_LAG = timedelta(days=4)
AVAILABILITY_BASIS = "provider_finished_status_conservative_4d"


class FixturePageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedFixturePage:
    fixtures: tuple[HistoricalFixture, ...]
    page: int
    per_page: int
    has_more: bool
    response_sha256: str
    quota_limit: int | None
    quota_remaining: int | None
    quota_reset: str | None


def _positive_id(value: object, field: str) -> str:
    if isinstance(value, bool):
        raise FixturePageError(f"{field}_INVALID")
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return str(int(value.strip()))
    raise FixturePageError(f"{field}_INVALID")


def _aware_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FixturePageError(f"{field}_MISSING")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FixturePageError(f"{field}_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixturePageError(f"{field}_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _kickoff(row: dict) -> datetime:
    text_value = row.get("kickoff_utc")
    timestamp = row.get("kickoff_ts")
    parsed = _aware_utc(text_value, "FIXTURE_KICKOFF") if text_value else None
    if timestamp is not None:
        if isinstance(timestamp, bool) or not (
            isinstance(timestamp, int)
            or (isinstance(timestamp, str) and timestamp.strip().isdigit())
        ):
            raise FixturePageError("FIXTURE_KICKOFF_EPOCH_INVALID")
        try:
            epoch = datetime.fromtimestamp(int(timestamp), timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise FixturePageError("FIXTURE_KICKOFF_EPOCH_INVALID") from exc
        if parsed is not None and abs((parsed - epoch).total_seconds()) > 1:
            raise FixturePageError("FIXTURE_KICKOFF_TIMESTAMP_CONFLICT")
        parsed = parsed or epoch
    if parsed is None:
        raise FixturePageError("FIXTURE_KICKOFF_MISSING")
    return parsed


def _score(goals: object) -> tuple[int | None, int | None]:
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


def _header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.casefold()
    return next((str(v) for k, v in headers.items() if str(k).casefold() == target), None)


def _integer_header(headers: Mapping[str, str], name: str) -> int | None:
    value = _header(headers, name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_fixture_page(
    raw_body: bytes,
    *,
    headers: Mapping[str, str],
    retrieved_at_utc: datetime,
    rights_approval_id: str,
) -> ParsedFixturePage:
    """Parse one exact provider response; raw bytes are retained separately."""
    if not isinstance(raw_body, bytes) or not raw_body:
        raise FixturePageError("PROVIDER_RESPONSE_BODY_REQUIRED")
    if retrieved_at_utc.tzinfo is None or retrieved_at_utc.utcoffset() is None:
        raise FixturePageError("RETRIEVAL_TIME_NOT_TIMEZONE_AWARE")
    if not rights_approval_id.strip():
        raise FixturePageError("RIGHTS_APPROVAL_ID_REQUIRED")
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FixturePageError("PROVIDER_RESPONSE_INVALID_JSON") from exc
    if not isinstance(body, dict) or body.get("success") not in (1, True):
        raise FixturePageError("PROVIDER_RESPONSE_UNSUCCESSFUL")
    rows = body.get("data")
    if not isinstance(rows, list):
        raise FixturePageError("FIXTURE_DATA_NOT_LIST")
    pagination = body.get("pagination") if isinstance(body.get("pagination"), dict) else {}
    if not {"page", "per_page", "has_more"} <= set(pagination):
        raise FixturePageError("PAGINATION_METADATA_INCOMPLETE")
    if not isinstance(pagination.get("has_more"), bool):
        raise FixturePageError("PAGINATION_HAS_MORE_INVALID")
    try:
        page = int(pagination["page"])
        per_page = int(pagination["per_page"])
    except (TypeError, ValueError) as exc:
        raise FixturePageError("PAGINATION_METADATA_INVALID") from exc
    if page < 1 or per_page < 1 or len(rows) > per_page:
        raise FixturePageError("PAGINATION_METADATA_INVALID")

    retrieved = retrieved_at_utc.astimezone(timezone.utc)
    fixtures: list[HistoricalFixture] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise FixturePageError(f"FIXTURE_ROW_NOT_OBJECT:{index}")
        fixture_id = _positive_id(row.get("id"), "FIXTURE_ID")
        if fixture_id in seen_ids:
            raise FixturePageError(f"DUPLICATE_FIXTURE_ID_IN_PAGE:{fixture_id}")
        seen_ids.add(fixture_id)
        league = row.get("league") if isinstance(row.get("league"), dict) else {}
        teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        competition_id = _positive_id(league.get("id"), "COMPETITION_ID")
        home_id = _positive_id(home.get("id"), "HOME_TEAM_ID")
        away_id = _positive_id(away.get("id"), "AWAY_TEAM_ID")
        if home_id == away_id:
            raise FixturePageError(f"HOME_AWAY_TEAM_ID_COLLISION:{fixture_id}")
        competition_name = str(league.get("name") or "").strip()
        home_name = str(home.get("name") or "").strip()
        away_name = str(away.get("name") or "").strip()
        if not competition_name or not home_name or not away_name:
            raise FixturePageError(f"FIXTURE_TEAM_OR_COMPETITION_NAME_MISSING:{fixture_id}")
        kickoff = _kickoff(row)
        raw_status = str(row.get("status") or "unknown").casefold()
        status_map = {
            "scheduled": FixtureStatus.SCHEDULED,
            "live": FixtureStatus.LIVE,
            "in_play": FixtureStatus.LIVE,
            "finished": FixtureStatus.FINISHED,
            "postponed": FixtureStatus.POSTPONED,
            "cancelled": FixtureStatus.CANCELLED,
            "abandoned": FixtureStatus.ABANDONED,
        }
        status = status_map.get(raw_status, FixtureStatus.UNKNOWN)
        home_score = away_score = None
        if status is FixtureStatus.FINISHED:
            home_score, away_score = _score(row.get("goals"))
            if home_score is None or away_score is None:
                status = FixtureStatus.UNKNOWN
        payload = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        payload_hash = hashlib.sha256(payload).hexdigest()
        available_at = kickoff + AVAILABILITY_LAG if status is FixtureStatus.FINISHED else None
        season = league.get("season")
        fixtures.append(HistoricalFixture(
            provider=PROVIDER,
            source_id=SOURCE_ID,
            provider_fixture_id=fixture_id,
            provider_competition_id=competition_id,
            provider_home_team_id=home_id,
            provider_away_team_id=away_id,
            competition_name=competition_name[:160],
            home_team_name=home_name[:160],
            away_team_name=away_name[:160],
            kickoff_at_utc=kickoff,
            season_key=str(season)[:40] if season is not None else None,
            status=status,
            home_score=home_score,
            away_score=away_score,
            payload=row,
            payload_sha256=payload_hash,
            retrieved_at_utc=retrieved,
            source_event_time_utc=kickoff,
            available_at_utc=available_at,
            availability_basis=AVAILABILITY_BASIS if available_at else "not_settled",
            point_in_time_certifiable=False,
            rights_approval_id=rights_approval_id,
        ))
    return ParsedFixturePage(
        fixtures=tuple(fixtures),
        page=page,
        per_page=per_page,
        has_more=pagination["has_more"],
        response_sha256=hashlib.sha256(raw_body).hexdigest(),
        quota_limit=_integer_header(headers, "X-RateLimit-Limit"),
        quota_remaining=_integer_header(headers, "X-RateLimit-Remaining"),
        quota_reset=_header(headers, "X-RateLimit-Reset"),
    )
