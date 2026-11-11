"""Read-only adapter for the archived Club-Football-Match-Data CSV.

The Veltrix artifact contains date-only match records, not exact kickoff or
source-publication timestamps. This adapter therefore marks every row with a
conservative four-calendar-day availability surrogate. It is suitable only
for exploratory retrospective walk-forward diagnostics, never production
certification. Odds, Elo and in-match statistics are deliberately ignored.
"""
from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable

from veltrix_v2.models.poisson_strength import TrainingMatch

EXPECTED_SOURCE = "xgabora/Club-Football-Match-Data"
SEASON_KEY = "cfmd-2020-2026-continuous"
AVAILABILITY_BASIS = "date_only_conservative_4d"
REQUIRED_COLUMNS = {
    "source", "division", "match_date", "home_team", "away_team",
    "home_goals", "away_goals", "full_time_result",
}


@dataclass(frozen=True, slots=True)
class ClubFootballDatasetManifest:
    source: str
    dataset_sha256: str
    dataset_bytes: int
    row_count: int
    competition_keys: tuple[str, ...]
    first_match_date: str
    last_match_date: str
    retrieved_at_utc: str
    availability_basis: str
    exact_kickoff_times_available: bool
    source_publication_timestamps_available: bool
    point_in_time_certifiable: bool
    ignored_feature_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClubFootballDataset:
    matches: tuple[TrainingMatch, ...]
    manifest: ClubFootballDatasetManifest


def _team_key(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().casefold())
    if not normalized:
        raise ValueError("CFMD_TEAM_NAME_REQUIRED")
    return normalized


def _score(value: str, field: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"CFMD_INVALID_{field.upper()}") from None
    if not number.is_integer() or number < 0:
        raise ValueError(f"CFMD_INVALID_{field.upper()}")
    return int(number)


def load_club_football_match_data(
    path: str | Path,
    *,
    retrieved_at_utc: datetime,
    divisions: Iterable[str],
) -> ClubFootballDataset:
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if retrieved_at_utc.tzinfo is None or retrieved_at_utc.utcoffset() is None:
        raise ValueError("CFMD_RETRIEVAL_TIMESTAMP_MUST_BE_AWARE")
    retrieved = retrieved_at_utc.astimezone(timezone.utc)
    requested = tuple(sorted(set(divisions)))
    if not requested or any(not isinstance(code, str) or not code.strip() for code in requested):
        raise ValueError("CFMD_DIVISIONS_REQUIRED")
    raw = source_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows: list[TrainingMatch] = []
    seen: set[tuple[str, str, str, str]] = set()
    dates: list[date] = []
    selected = set(requested)
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not REQUIRED_COLUMNS <= set(reader.fieldnames):
            raise ValueError("CFMD_REQUIRED_COLUMNS_MISSING")
        for line_number, record in enumerate(reader, start=2):
            division = str(record.get("division", "")).strip()
            if division not in selected:
                continue
            if str(record.get("source", "")).strip() != EXPECTED_SOURCE:
                raise ValueError("CFMD_SOURCE_IDENTITY_MISMATCH")
            match_day = date.fromisoformat(str(record.get("match_date", "")).strip())
            home_name = str(record.get("home_team", "")).strip()
            away_name = str(record.get("away_team", "")).strip()
            home_key, away_key = _team_key(home_name), _team_key(away_name)
            if home_key == away_key:
                raise ValueError("CFMD_HOME_AWAY_TEAM_IDENTITY_COLLISION")
            key = (division, match_day.isoformat(), home_key, away_key)
            if key in seen:
                raise ValueError("CFMD_DUPLICATE_MATCH_KEY")
            seen.add(key)
            home_goals = _score(record.get("home_goals", ""), "home_goals")
            away_goals = _score(record.get("away_goals", ""), "away_goals")
            expected_result = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
            if str(record.get("full_time_result", "")).strip().upper() != expected_result:
                raise ValueError("CFMD_FULL_TIME_RESULT_CONFLICT")
            # Date-only source: noon UTC is a neutral date anchor, not a claimed kickoff.
            kickoff_anchor = datetime.combine(match_day, time(12, 0), tzinfo=timezone.utc)
            # Four-day lag is deliberately conservative and still only a proxy.
            available_anchor = datetime.combine(match_day + timedelta(days=4), time.min, tzinfo=timezone.utc)
            fixture_digest = hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:24]
            rows.append(TrainingMatch(
                fixture_id=f"cfmd:{division}:{fixture_digest}",
                competition_key=f"cfmd:{division}",
                season=SEASON_KEY,
                kickoff_utc=kickoff_anchor,
                available_at_utc=available_anchor,
                home_team_id=f"cfmd:{division}:{home_key}",
                away_team_id=f"cfmd:{division}:{away_key}",
                home_goals=home_goals,
                away_goals=away_goals,
                source_observation_id=f"cfmd:{digest}:row:{line_number}",
                quality_state="valid",
                availability_basis=AVAILABILITY_BASIS,
            ))
            dates.append(match_day)
    if not rows:
        raise ValueError("CFMD_NO_ROWS_FOR_REQUESTED_DIVISIONS")
    matches = tuple(sorted(rows, key=lambda row: (row.kickoff_utc, row.fixture_id)))
    ignored = tuple(sorted(
        set()
        | {"home_elo", "away_elo", "home_odds", "draw_odds", "away_odds",
           "over25_odds", "under25_odds", "half_time_home_goals",
           "half_time_away_goals", "home_shots", "away_shots",
           "home_shots_on_target", "away_shots_on_target",
           "home_form3", "away_form3", "home_form5", "away_form5"}
    ))
    manifest = ClubFootballDatasetManifest(
        source=EXPECTED_SOURCE,
        dataset_sha256=digest,
        dataset_bytes=len(raw),
        row_count=len(matches),
        competition_keys=tuple(sorted({row.competition_key for row in matches})),
        first_match_date=min(dates).isoformat(),
        last_match_date=max(dates).isoformat(),
        retrieved_at_utc=retrieved.isoformat(),
        availability_basis=AVAILABILITY_BASIS,
        exact_kickoff_times_available=False,
        source_publication_timestamps_available=False,
        point_in_time_certifiable=False,
        ignored_feature_columns=ignored,
    )
    return ClubFootballDataset(matches=matches, manifest=manifest)
