"""Parser for the CC0 FerrerasRP/FootballData JSON archive.

The source reports local-looking match clock strings without a timezone.
Those strings are preserved as source metadata; kickoff_at remains None.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone, timedelta
import hashlib
import json
import re
import unicodedata


SOURCE_ID = "ferrerasrp-footballdata-cc0"
PROVIDER = "FootballData"


@dataclass(frozen=True)
class FootballDataObservation:
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str
    kickoff_date: date
    source_reported_local_time: str
    source_timezone: str
    home_goals: int
    away_goals: int
    round_name: str | None
    provider: str
    source_id: str
    availability_basis: str
    available_at: datetime
    recorded_at: datetime
    point_in_time_certifiable: bool
    payload_sha256: str
    source_row_index: int
    team_name_normalizations: tuple[dict, ...]


@dataclass(frozen=True)
class FootballDataArchiveResult:
    observations: tuple[FootballDataObservation, ...]
    fixture_line_count: int
    result_count: int
    rejected_result_count: int
    not_yet_eligible_count: int
    rejected_annotations: tuple[str, ...]
    team_name_normalizations: tuple[dict, ...]


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return _sha256(raw)


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")


def _normalize_team_name(name: object, names_in_snapshot: set[str]) -> tuple[str | None, dict | None]:
    if not isinstance(name, str) or not name.strip():
        return None, None
    original = name.strip()
    if "\n" not in original and "\r" not in original:
        return original, None
    normalized = re.sub(r"[\r\n]+\s*\d+\s*$", "", original).strip()
    if normalized == original:
        return None, None
    if normalized not in names_in_snapshot:
        return None, {
            "original": original,
            "normalized": normalized,
            "reason": "TRAILING_LINE_NUMBER_BASE_NOT_FOUND_IN_SNAPSHOT",
        }
    return normalized, {
        "original": original,
        "normalized": normalized,
        "reason": "TRAILING_LINE_NUMBER_ARTIFACT_BASE_VERIFIED_IN_SAME_SNAPSHOT",
    }


def parse_json_archive(
    source_text: str,
    *,
    competition_id: str,
    source_path: str,
    snapshot_commit_sha: str,
    snapshot_available_at: datetime,
    imported_at: datetime,
    source_id: str = SOURCE_ID,
) -> FootballDataArchiveResult:
    if not isinstance(competition_id, str) or not competition_id.strip():
        raise ValueError("COMPETITION_ID_REQUIRED")
    if not isinstance(source_path, str) or not source_path.strip():
        raise ValueError("SOURCE_PATH_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{40}", snapshot_commit_sha or ""):
        raise ValueError("SNAPSHOT_COMMIT_SHA_INVALID")
    snapshot_at = _aware(snapshot_available_at, "snapshot_available_at")
    retrieved_at = _aware(imported_at, "imported_at")
    if retrieved_at < snapshot_at:
        raise ValueError("IMPORT_PRECEDES_SOURCE_SNAPSHOT")
    try:
        rows = json.loads(source_text)
    except json.JSONDecodeError:
        raise ValueError("SOURCE_JSON_INVALID") from None
    if not isinstance(rows, list):
        raise ValueError("SOURCE_JSON_ROOT_MUST_BE_ARRAY")

    names_in_snapshot = {
        name.strip()
        for row in rows if isinstance(row, dict)
        for name in (row.get("home"), row.get("away"))
        if isinstance(name, str) and name.strip()
    }
    fixture_lines = len(rows)
    rejected = 0
    not_yet = 0
    observations: list[FootballDataObservation] = []
    rejected_annotations: list[str] = []
    all_normalizations: list[dict] = []
    seen_fixture_ids: set[str] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            rejected += 1
            rejected_annotations.append(f"ROW_{index}:NOT_OBJECT")
            continue
        required = ("match_date", "home", "away", "goals_home", "goals_away")
        if any(field not in row for field in required):
            rejected += 1
            rejected_annotations.append(f"ROW_{index}:REQUIRED_FIELD_MISSING")
            continue
        match_date_text = row.get("match_date")
        if not isinstance(match_date_text, str):
            rejected += 1
            rejected_annotations.append(f"ROW_{index}:MATCH_DATE_INVALID")
            continue
        try:
            local_dt = datetime.strptime(match_date_text.strip(), "%d.%m.%Y %H:%M")
        except ValueError:
            rejected += 1
            rejected_annotations.append(f"ROW_{index}:MATCH_DATE_FORMAT_INVALID")
            continue
        home_name, home_norm = _normalize_team_name(row.get("home"), names_in_snapshot)
        away_name, away_norm = _normalize_team_name(row.get("away"), names_in_snapshot)
        if home_name is None or away_name is None:
            rejected += 1
            rejected_annotations.append(f"ROW_{index}:TEAM_NAME_NORMALIZATION_UNVERIFIED")
            continue
        normalizations = tuple(item for item in (home_norm, away_norm) if item is not None)
        for item in normalizations:
            all_normalizations.append({"row_index": index, "field": "home" if item is home_norm else "away", **item})

        home_goals, away_goals = row.get("goals_home"), row.get("goals_away")
        if (isinstance(home_goals, bool) or not isinstance(home_goals, int) or home_goals < 0
                or isinstance(away_goals, bool) or not isinstance(away_goals, int) or away_goals < 0):
            rejected += 1
            rejected_annotations.append(f"ROW_{index}:SCORE_INVALID")
            continue

        match_day = local_dt.date()
        safe_boundary = datetime.combine(match_day + timedelta(days=2), time.min, tzinfo=timezone.utc)
        if snapshot_at < safe_boundary:
            not_yet += 1
            continue

        home_team_id = f"{source_id}:team:{_slug(home_name)}"
        away_team_id = f"{source_id}:team:{_slug(away_name)}"
        fixture_identity = {
            "source_id": source_id,
            "source_path": source_path,
            "competition_id": competition_id,
            "kickoff_date": match_day.isoformat(),
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        }
        fixture_id = _canonical_hash(fixture_identity)
        if fixture_id in seen_fixture_ids:
            rejected += 1
            rejected_annotations.append(f"ROW_{index}:DUPLICATE_FIXTURE_ID")
            continue
        seen_fixture_ids.add(fixture_id)
        payload_sha = _canonical_hash(row)
        observations.append(FootballDataObservation(
            fixture_id=fixture_id,
            competition_id=competition_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_name=home_name,
            away_team_name=away_name,
            kickoff_date=match_day,
            source_reported_local_time=local_dt.strftime("%H:%M"),
            source_timezone="UNKNOWN",
            home_goals=home_goals,
            away_goals=away_goals,
            round_name=row.get("round") if isinstance(row.get("round"), str) else None,
            provider=PROVIDER,
            source_id=source_id,
            availability_basis="immutable_github_commit_and_import_timestamp_with_date_boundary",
            available_at=snapshot_at,
            recorded_at=retrieved_at,
            point_in_time_certifiable=True,
            payload_sha256=payload_sha,
            source_row_index=index,
            team_name_normalizations=normalizations,
        ))

    return FootballDataArchiveResult(
        observations=tuple(observations),
        fixture_line_count=fixture_lines,
        result_count=len(observations),
        rejected_result_count=rejected,
        not_yet_eligible_count=not_yet,
        rejected_annotations=tuple(rejected_annotations),
        team_name_normalizations=tuple(all_normalizations),
    )
