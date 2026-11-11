"""Deterministic overlap reconciliation for OpenFootball and an accepted reference feed.

This module compares supplied snapshots only. It performs no network calls and no
database writes. Team names must be mapped through an explicit caller-supplied
crosswalk; fuzzy identity guessing is intentionally absent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .openfootball import OpenFootballMatch


@dataclass(frozen=True, slots=True)
class ReferenceFixture:
    fixture_id: str
    match_date: str
    home_team_id: str
    away_team_id: str
    home_score: int | None
    away_score: int | None
    status: str


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    openfootball_rows: int
    reference_rows: int
    comparable_rows: int
    matched_rows: int
    missing_openfootball_score: int
    unmatched_openfootball: int
    duplicate_openfootball_keys: int
    duplicate_reference_keys: int
    score_conflicts: int
    identity_conflicts: int
    date_conflicts: int

    @property
    def passed(self) -> bool:
        return (
            self.comparable_rows > 0
            and self.unmatched_openfootball == 0
            and self.duplicate_openfootball_keys == 0
            and self.duplicate_reference_keys == 0
            and self.score_conflicts == 0
            and self.identity_conflicts == 0
            and self.date_conflicts == 0
        )


def _key(match_date: str, home_id: str, away_id: str) -> tuple[str, str, str]:
    return match_date, home_id, away_id


def reconcile_openfootball(
    source_rows: Sequence[OpenFootballMatch],
    reference_rows: Sequence[ReferenceFixture],
    team_id_crosswalk: Mapping[str, str],
) -> ReconciliationSummary:
    """Compare only final-score rows with exact crosswalked team identities."""
    source_keys: dict[tuple[str, str, str], OpenFootballMatch] = {}
    source_duplicates = 0
    missing_score = 0
    identity_conflicts = 0
    for row in source_rows:
        if not row.has_full_time_score:
            missing_score += 1
            continue
        home_id = team_id_crosswalk.get(row.home_name)
        away_id = team_id_crosswalk.get(row.away_name)
        if not home_id or not away_id or home_id == away_id:
            identity_conflicts += 1
            continue
        key = _key(row.match_date.isoformat(), home_id, away_id)
        if key in source_keys:
            source_duplicates += 1
        else:
            source_keys[key] = row

    reference_keys: dict[tuple[str, str, str], ReferenceFixture] = {}
    reference_duplicates = 0
    for row in reference_rows:
        if row.status.lower() not in {"finished", "ft", "final"}:
            continue
        if row.home_score is None or row.away_score is None:
            continue
        key = _key(row.match_date, row.home_team_id, row.away_team_id)
        if key in reference_keys:
            reference_duplicates += 1
        else:
            reference_keys[key] = row

    matched = 0
    unmatched = 0
    score_conflicts = 0
    for key, source in source_keys.items():
        reference = reference_keys.get(key)
        if reference is None:
            unmatched += 1
            continue
        if (source.full_time_home, source.full_time_away) != (reference.home_score, reference.away_score):
            score_conflicts += 1
        else:
            matched += 1

    return ReconciliationSummary(
        openfootball_rows=len(source_rows),
        reference_rows=len(reference_rows),
        comparable_rows=len(source_keys),
        matched_rows=matched,
        missing_openfootball_score=missing_score,
        unmatched_openfootball=unmatched,
        duplicate_openfootball_keys=source_duplicates,
        duplicate_reference_keys=reference_duplicates,
        score_conflicts=score_conflicts,
        identity_conflicts=identity_conflicts,
        date_conflicts=0,
    )
