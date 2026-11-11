"""5DollarFootballAPI historical finished-match adapter for V2 research.

Only final scores and canonical provider IDs are ingested. Bookmaker odds,
Elo, form fields and other non-point-in-time columns are deliberately ignored.
The provider does not supply historical result-publication timestamps, so the
adapter applies a fixed four-day post-kickoff availability lag. This is a
conservative retrospective proxy, not source-timestamp certification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Iterable

from veltrix_v2.models.poisson_strength import TrainingMatch

SOURCE_ID = "5dollarfootballapi"
AVAILABILITY_BASIS = "provider_finished_status_conservative_4d"
AVAILABILITY_LAG = timedelta(days=4)


@dataclass(frozen=True, slots=True)
class FiveDollarHistoryManifest:
    source_id: str
    retrieved_at_utc: str
    source_response_sha256: str
    row_count: int
    competition_keys: tuple[str, ...]
    first_kickoff_utc: str
    last_kickoff_utc: str
    skipped_not_finished: int
    skipped_recent_embargo: int
    invalid_rows: int
    duplicate_fixture_ids: int
    availability_basis: str
    point_in_time_certifiable: bool
    model_training_approved: bool
    attribution_required: bool
    raw_redistribution_allowed: bool


@dataclass(frozen=True, slots=True)
class FiveDollarHistory:
    matches: tuple[TrainingMatch, ...]
    manifest: FiveDollarHistoryManifest


def _aware_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"FIVEDOLLAR_{field.upper()}_MUST_BE_AWARE")
    return value.astimezone(timezone.utc)


def _kickoff(row: dict[str, Any]) -> datetime:
    value = row.get("kickoff_utc")
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("FIVEDOLLAR_KICKOFF_NOT_AWARE")
        return parsed.astimezone(timezone.utc)
    timestamp = row.get("kickoff_ts")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        raise ValueError("FIVEDOLLAR_KICKOFF_MISSING")
    return datetime.fromtimestamp(timestamp, timezone.utc)


def _positive_id(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return str(int(value.strip()))
    return None


def _score(value: Any) -> int | None:
    if type(value) is int and value >= 0:
        return value
    return None


def load_fivedollar_finished_matches(
    rows: Iterable[dict[str, Any]],
    *,
    retrieved_at_utc: datetime,
) -> FiveDollarHistory:
    retrieved = _aware_utc(retrieved_at_utc, "retrieved_at_utc")
    raw_rows = tuple(rows)
    canonical = json.dumps(raw_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    source_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    matches: list[TrainingMatch] = []
    seen: set[str] = set()
    skipped_not_finished = skipped_recent = invalid = duplicates = 0

    for row in raw_rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        if row.get("status") != "finished":
            skipped_not_finished += 1
            continue
        fixture_id = _positive_id(row.get("id"))
        league = row.get("league")
        teams = row.get("teams")
        goals = row.get("goals")
        league_id = _positive_id(league.get("id")) if isinstance(league, dict) else None
        home = teams.get("home") if isinstance(teams, dict) else None
        away = teams.get("away") if isinstance(teams, dict) else None
        home_id = _positive_id(home.get("id")) if isinstance(home, dict) else None
        away_id = _positive_id(away.get("id")) if isinstance(away, dict) else None
        home_goals = _score(goals.get("home")) if isinstance(goals, dict) else None
        away_goals = _score(goals.get("away")) if isinstance(goals, dict) else None
        if (
            fixture_id is None or league_id is None or home_id is None or away_id is None
            or home_id == away_id or home_goals is None or away_goals is None
        ):
            invalid += 1
            continue
        if fixture_id in seen:
            duplicates += 1
            continue
        seen.add(fixture_id)
        try:
            kickoff = _kickoff(row)
        except (ValueError, OverflowError, OSError):
            invalid += 1
            continue
        available_at = kickoff + AVAILABILITY_LAG
        if kickoff >= retrieved or available_at > retrieved:
            skipped_recent += 1
            continue
        observation_payload = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        observation_hash = hashlib.sha256(
            f"{retrieved.isoformat()}|{observation_payload}".encode("utf-8")
        ).hexdigest()
        matches.append(TrainingMatch(
            fixture_id=f"5dollar:{fixture_id}",
            competition_key=f"5dollar:{league_id}",
            season="rolling-365d",
            kickoff_utc=kickoff,
            available_at_utc=available_at,
            home_team_id=f"5dollar:{league_id}:{home_id}",
            away_team_id=f"5dollar:{league_id}:{away_id}",
            home_goals=home_goals,
            away_goals=away_goals,
            source_observation_id=f"5dollar:{observation_hash}",
            quality_state="valid",
            availability_basis=AVAILABILITY_BASIS,
        ))
    matches.sort(key=lambda item: (item.kickoff_utc, item.fixture_id))
    if not matches:
        raise ValueError("FIVEDOLLAR_NO_ELIGIBLE_FINISHED_MATCHES")
    manifest = FiveDollarHistoryManifest(
        source_id=SOURCE_ID,
        retrieved_at_utc=retrieved.isoformat(),
        source_response_sha256=source_hash,
        row_count=len(matches),
        competition_keys=tuple(sorted({item.competition_key for item in matches})),
        first_kickoff_utc=matches[0].kickoff_utc.isoformat(),
        last_kickoff_utc=matches[-1].kickoff_utc.isoformat(),
        skipped_not_finished=skipped_not_finished,
        skipped_recent_embargo=skipped_recent,
        invalid_rows=invalid,
        duplicate_fixture_ids=duplicates,
        availability_basis=AVAILABILITY_BASIS,
        point_in_time_certifiable=False,
        model_training_approved=True,
        attribution_required=True,
        raw_redistribution_allowed=False,
    )
    return FiveDollarHistory(matches=tuple(matches), manifest=manifest)
