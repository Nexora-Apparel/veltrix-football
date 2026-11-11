"""OpenPlay match, competition-season coverage and known-issue join.

Preserves the pinned release's native identifiers and unzoned date strings. The
match-level xG model identity is the authoritative key passed to player/shot adapters.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"OPENPLAY_MATCH_REQUIRED_FIELD:{key}")
    return str(value).strip()


def _optional_int(value: object, key: str) -> int | None:
    if value in (None, ""):
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"OPENPLAY_MATCH_INVALID_INTEGER:{key}")
    return value


def _bool_or_none(value: object, key: str) -> bool | None:
    if value in (None, ""):
        return None
    if type(value) is bool:
        return value
    if value in (0, "0", "false", "False", "FALSE"):
        return False
    if value in (1, "1", "true", "True", "TRUE"):
        return True
    raise ValueError(f"OPENPLAY_MATCH_INVALID_BOOLEAN:{key}")


@dataclass(frozen=True, slots=True)
class OpenPlayMatchRecord:
    match_id: str
    competition_code: str
    season: str
    source_match_date: str
    home_team_id: str
    away_team_id: str
    home_score: int | None
    away_score: int | None
    xg_model_id: str
    score_matches_events: bool | None
    source_scraped_at: str | None
    competition_season_in_scope: bool
    competition_season_coverage_pct: float | None
    competition_season_matches_played: int | None
    competition_season_matches_with_events: int | None
    competition_season_gaps: int | None
    known_gap: bool
    data_issue_codes: tuple[str, ...]
    quality_state: str
    payload_sha256: str
    source_release: str = "data-v0.1.0"

    def __post_init__(self):
        object.__setattr__(self, "data_issue_codes", tuple(self.data_issue_codes))


def adapt_match_record(
    row: Mapping[str, object],
    *,
    coverage_rows: Sequence[Mapping[str, object]],
    known_gap_rows: Sequence[Mapping[str, object]] = (),
    data_issue_rows: Sequence[Mapping[str, object]] = (),
) -> OpenPlayMatchRecord:
    if not isinstance(row, Mapping):
        raise ValueError("OPENPLAY_MATCH_ROW_MUST_BE_MAPPING")
    match_id = _text(row, "match_id")
    comp = _text(row, "comp")
    season = _text(row, "season")
    match_date = _text(row, "date")
    home_id = _text(row, "home_team_id")
    away_id = _text(row, "away_team_id")
    if home_id == away_id:
        raise ValueError("OPENPLAY_MATCH_TEAMS_MUST_DIFFER")
    xg_model = _text(row, "xg_model")

    matching_coverage = [
        item for item in coverage_rows
        if str(item.get("comp", "")).strip() == comp
        and str(item.get("season", "")).strip() == season
    ]
    if len(matching_coverage) > 1:
        raise ValueError("OPENPLAY_DUPLICATE_COMPETITION_SEASON_COVERAGE")
    coverage = matching_coverage[0] if matching_coverage else None

    def coverage_int(key: str) -> int | None:
        if coverage is None or coverage.get(key) in (None, ""):
            return None
        try:
            value = int(coverage[key])
        except (TypeError, ValueError):
            raise ValueError(f"OPENPLAY_INVALID_COVERAGE_VALUE:{key}") from None
        if value < 0:
            raise ValueError(f"OPENPLAY_INVALID_COVERAGE_VALUE:{key}")
        return value

    coverage_pct = None
    if coverage is not None and coverage.get("coverage_pct") not in (None, ""):
        try:
            coverage_pct = float(coverage["coverage_pct"])
        except (TypeError, ValueError):
            raise ValueError("OPENPLAY_INVALID_COVERAGE_VALUE:coverage_pct") from None
        if not 0 <= coverage_pct <= 100:
            raise ValueError("OPENPLAY_INVALID_COVERAGE_VALUE:coverage_pct")
    in_scope = coverage is not None and str(coverage.get("in_v1_scope", "")).strip().casefold() in {
        "true", "1", "yes", "y"
    }

    gaps = [
        item for item in known_gap_rows
        if str(item.get("match_id", "")).strip() == match_id
    ]
    issues = [
        item for item in data_issue_rows
        if str(item.get("match_id", "")).strip() == match_id
    ]
    issue_codes = tuple(sorted({
        str(item.get("issue", "unknown")).strip() or "unknown"
        for item in issues
    }))
    known_gap = bool(gaps)
    if known_gap:
        quality = "quarantined_known_gap"
    elif issue_codes:
        quality = "quarantined_known_data_issue"
    elif not in_scope:
        quality = "quarantined_outside_declared_coverage"
    else:
        quality = "eligible_for_historical_research"

    scraped = row.get("scraped_at")
    scraped_at = None if scraped in (None, "") else str(scraped)
    canonical = json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str).encode()
    return OpenPlayMatchRecord(
        match_id=match_id,
        competition_code=comp,
        season=season,
        source_match_date=match_date,
        home_team_id=home_id,
        away_team_id=away_id,
        home_score=_optional_int(row.get("home_score"), "home_score"),
        away_score=_optional_int(row.get("away_score"), "away_score"),
        xg_model_id=xg_model,
        score_matches_events=_bool_or_none(row.get("score_matches_events"), "score_matches_events"),
        source_scraped_at=scraped_at,
        competition_season_in_scope=in_scope,
        competition_season_coverage_pct=coverage_pct,
        competition_season_matches_played=coverage_int("matches_played"),
        competition_season_matches_with_events=coverage_int("matches_with_events"),
        competition_season_gaps=coverage_int("gaps"),
        known_gap=known_gap,
        data_issue_codes=issue_codes,
        quality_state=quality,
        payload_sha256=hashlib.sha256(canonical).hexdigest(),
    )
