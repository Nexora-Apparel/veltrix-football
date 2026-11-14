"""Strict parser for OpenFootball Football.TXT season archives.

The source format supplies calendar dates but generally no exact kickoff
clock/timezone. Parsed observations therefore retain kickoff_date and never
invent kickoff_at. Snapshot availability comes from the exact repository
commit timestamp supplied by the caller; import time is recorded separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import re
import unicodedata

from veltrix_v2.models.poisson import MatchObservation


_DATE_LINE = re.compile(r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})$")
_MATCHDAY_LINE = re.compile(r"(?:Matchday|Round)\s+(\d+)", re.IGNORECASE)
_SCORE_LINE = re.compile(r"\s+(\d+)\s*-\s*(\d+)\s*$")
_MONTHS = {name: number for number, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
)}


@dataclass(frozen=True)
class OpenFootballArchive:
    competition_id: str
    season_title: str
    source_path: str
    snapshot_commit_sha: str
    snapshot_available_at: datetime
    imported_at: datetime
    content_sha256: str
    fixture_line_count: int
    result_count: int
    rejected_result_count: int
    rejected_annotations: tuple[str, ...]
    observations: tuple[MatchObservation, ...]


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _team_id(competition_id: str, name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if not slug:
        raise ValueError("TEAM_NAME_CANNOT_BE_NORMALIZED")
    return f"openfootball:{competition_id}:{slug}"


def parse_archive(
    text: str,
    *,
    competition_id: str,
    source_path: str,
    snapshot_commit_sha: str,
    snapshot_available_at: datetime,
    imported_at: datetime,
) -> OpenFootballArchive:
    """Parse scored fixtures using conservative, provenance-backed timestamps.

    snapshot_available_at must be the commit timestamp for the exact source
    file version. imported_at must be the actual ingestion timestamp. A
    result is rejected when its snapshot timestamp is too early to prove the
    match had finished even under the most conservative timezone bound.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("ARCHIVE_TEXT_EMPTY")
    if not isinstance(competition_id, str) or not competition_id.strip():
        raise ValueError("COMPETITION_ID_REQUIRED")
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("SOURCE_PATH_REQUIRED")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", snapshot_commit_sha or ""):
        raise ValueError("SNAPSHOT_COMMIT_SHA_INVALID")
    if not _aware(snapshot_available_at) or not _aware(imported_at):
        raise ValueError("SNAPSHOT_AND_IMPORT_TIMESTAMPS_MUST_BE_AWARE")
    if imported_at < snapshot_available_at:
        raise ValueError("IMPORT_PRECEDES_SNAPSHOT_PUBLICATION")

    lines = text.splitlines()
    season_title = next((line[2:].strip() for line in lines if line.startswith("= ")), "")
    if not season_title:
        raise ValueError("SEASON_TITLE_MISSING")

    current_date: date | None = None
    matchday = "unknown"
    fixture_lines = 0
    result_count = 0
    rejected = 0
    rejected_annotations: list[str] = []
    observations: list[MatchObservation] = []
    seen_ids: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("="):
            continue
        day_match = _MATCHDAY_LINE.search(stripped)
        if day_match:
            matchday = day_match.group(1)
            continue
        date_match = _DATE_LINE.fullmatch(stripped)
        if date_match:
            month_name, day_text, year_text = date_match.groups()
            try:
                current_date = date(int(year_text), _MONTHS[month_name], int(day_text))
            except (KeyError, ValueError):
                current_date = None
            continue
        if " v " not in stripped:
            continue
        fixture_lines += 1
        if current_date is None:
            rejected += 1
            continue
        home_name, away_and_score = re.split(r"\s+v\s+", stripped, maxsplit=1)
        score_match = _SCORE_LINE.search(away_and_score)
        if not score_match:
            continue
        home_goals, away_goals = int(score_match.group(1)), int(score_match.group(2))
        annotation = score_match.group(3)
        away_name = away_and_score[:score_match.start()].strip()
        home_name = home_name.strip()
        if not home_name or not away_name:
            rejected += 1
            continue
        if annotation:
            rejected += 1
            rejected_annotations.append(annotation.strip().upper())
            continue
        identity = "|".join((source_path, matchday, current_date.isoformat(),
                             home_name.casefold(), away_name.casefold()))
        fixture_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if fixture_id in seen_ids:
            rejected += 1
            continue
        seen_ids.add(fixture_id)

        safe_boundary = datetime.combine(
            current_date + timedelta(days=2), time.min, tzinfo=timezone.utc
        )
        if snapshot_available_at.astimezone(timezone.utc) < safe_boundary:
            rejected += 1
            continue
        observations.append(MatchObservation(
            fixture_id=fixture_id,
            competition_id=competition_id,
            home_team_id=_team_id(competition_id, home_name),
            away_team_id=_team_id(competition_id, away_name),
            kickoff_at=None,
            available_at=snapshot_available_at,
            recorded_at=imported_at,
            home_goals=home_goals,
            away_goals=away_goals,
            kickoff_date=current_date,
        ))
        result_count += 1

    return OpenFootballArchive(
        competition_id=competition_id, season_title=season_title,
        source_path=source_path, snapshot_commit_sha=snapshot_commit_sha.lower(),
        snapshot_available_at=snapshot_available_at, imported_at=imported_at,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        fixture_line_count=fixture_lines, result_count=result_count,
        rejected_result_count=rejected, rejected_annotations=tuple(rejected_annotations),
        observations=tuple(observations),
    )
