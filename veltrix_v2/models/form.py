"""Point-in-time team form and schedule features for VELTRIX 2.0."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time, timezone
import math
from typing import Iterable

from .poisson import MatchObservation, observation_eligible_as_of


@dataclass(frozen=True)
class TeamForm:
    competition_id: str
    team_id: str
    matches: int
    wins: int
    draws: int
    losses: int
    points_per_match: float
    goals_for_per_match: float
    goals_against_per_match: float
    goal_difference_per_match: float
    last_five_points_per_match: float
    home_matches: int
    away_matches: int
    home_goals_for_per_match: float | None
    away_goals_for_per_match: float | None
    rest_days: float | None
    latest_result_was_date_only: bool


@dataclass(frozen=True)
class TeamFormSnapshot:
    cutoff_at: datetime
    competition_id: str
    home: TeamForm
    away: TeamForm
    eligible_match_count: int
    excluded_non_certifiable_count: int


def _event_time(row: MatchObservation) -> tuple[datetime, bool]:
    if row.kickoff_at is not None:
        return row.kickoff_at.astimezone(timezone.utc), False
    safe = datetime.combine(
        row.kickoff_date + timedelta(days=2), time.min, tzinfo=timezone.utc
    )
    return safe, True


def _team_form(rows: list[MatchObservation], team_id: str, competition_id: str,
               cutoff_at: datetime) -> TeamForm:
    appearances: list[tuple[datetime, str, int, int, bool, bool]] = []
    for row in rows:
        if row.home_team_id == team_id:
            gf, ga, is_home = row.home_goals, row.away_goals, True
        elif row.away_team_id == team_id:
            gf, ga, is_home = row.away_goals, row.home_goals, False
        else:
            continue
        appearances.append((*_event_time(row), row.fixture_id, gf, ga, is_home))
    appearances.sort(key=lambda item: (item[0], item[2]))
    if not appearances:
        raise ValueError("TEAM_FORM_HISTORY_UNAVAILABLE")

    wins = sum(gf > ga for _, _, _, gf, ga, _ in appearances)
    draws = sum(gf == ga for _, _, _, gf, ga, _ in appearances)
    losses = len(appearances) - wins - draws
    points = 3 * wins + draws
    last_five = appearances[-5:]
    last_points = sum(3 if gf > ga else 1 if gf == ga else 0
                      for _, _, _, gf, ga, _ in last_five)
    home_rows = [item for item in appearances if item[5]]
    away_rows = [item for item in appearances if not item[5]]
    latest_time, latest_date_only = appearances[-1][0], appearances[-1][1]
    rest_days = None if latest_date_only else max(
        0.0, (cutoff_at.astimezone(timezone.utc) - latest_time).total_seconds() / 86400.0
    )
    count = len(appearances)
    return TeamForm(
        competition_id=competition_id, team_id=team_id, matches=count,
        wins=wins, draws=draws, losses=losses,
        points_per_match=points / count,
        goals_for_per_match=sum(x[3] for x in appearances) / count,
        goals_against_per_match=sum(x[4] for x in appearances) / count,
        goal_difference_per_match=sum(x[3] - x[4] for x in appearances) / count,
        last_five_points_per_match=last_points / len(last_five),
        home_matches=len(home_rows), away_matches=len(away_rows),
        home_goals_for_per_match=(sum(x[3] for x in home_rows) / len(home_rows)
                                  if home_rows else None),
        away_goals_for_per_match=(sum(x[3] for x in away_rows) / len(away_rows)
                                  if away_rows else None),
        rest_days=rest_days, latest_result_was_date_only=latest_date_only,
    )


def team_form_as_of(
    observations: Iterable[MatchObservation],
    *,
    competition_id: str,
    home_team_id: str,
    away_team_id: str,
    cutoff_at: datetime,
) -> TeamFormSnapshot:
    """Return form known by cutoff; uncertifiable rows never enter the feature set."""
    if not isinstance(cutoff_at, datetime) or cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("TEAM_FORM_CUTOFF_MUST_BE_TIMEZONE_AWARE")
    if not all(isinstance(x, str) and x.strip() for x in (
        competition_id, home_team_id, away_team_id
    )) or home_team_id == away_team_id:
        raise ValueError("TEAM_FORM_TARGET_IDENTITY_INVALID")

    rows = list(observations)
    counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, MatchObservation) and isinstance(row.fixture_id, str):
            counts[row.fixture_id] = counts.get(row.fixture_id, 0) + 1
    eligible: list[MatchObservation] = []
    excluded = 0
    for row in rows:
        if not isinstance(row, MatchObservation) or row.competition_id != competition_id:
            continue
        if counts.get(row.fixture_id, 0) != 1:
            continue
        if not row.point_in_time_certifiable:
            excluded += 1
            continue
        if observation_eligible_as_of(row, cutoff_at=cutoff_at, competition_id=competition_id):
            eligible.append(row)

    home_rows = [row for row in eligible if home_team_id in (row.home_team_id, row.away_team_id)]
    away_rows = [row for row in eligible if away_team_id in (row.home_team_id, row.away_team_id)]
    if not home_rows:
        raise ValueError("TEAM_FORM_HOME_HISTORY_UNAVAILABLE")
    if not away_rows:
        raise ValueError("TEAM_FORM_AWAY_HISTORY_UNAVAILABLE")
    return TeamFormSnapshot(
        cutoff_at=cutoff_at, competition_id=competition_id,
        home=_team_form(home_rows, home_team_id, competition_id, cutoff_at),
        away=_team_form(away_rows, away_team_id, competition_id, cutoff_at),
        eligible_match_count=len(eligible),
        excluded_non_certifiable_count=excluded,
    )
