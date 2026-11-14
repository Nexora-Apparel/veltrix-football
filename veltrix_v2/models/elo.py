"""Point-in-time Elo rating state for VELTRIX 2.0.

This module produces rating features, not calibrated 1X2 probabilities.
Only provenance-certified results available and recorded by the requested
cutoff can update a rating. Same-time fixtures are applied as one batch so
input ordering cannot leak one result into another.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Iterable

from .poisson import MatchObservation, observation_eligible_as_of


MODEL_VERSION = "veltrix-elo-ratings-v1"


@dataclass(frozen=True)
class TeamRating:
    competition_id: str
    team_id: str
    rating: float
    matches_played: int


@dataclass(frozen=True)
class EloSnapshot:
    model_version: str
    cutoff_at: datetime
    competition_id: str
    home_team: TeamRating
    away_team: TeamRating
    home_advantage_points: float
    expected_home_score: float
    rating_difference: float
    eligible_match_count: int
    excluded_non_certifiable_count: int


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _event_time(match: MatchObservation) -> datetime:
    if match.kickoff_at is not None:
        return match.kickoff_at.astimezone(timezone.utc)
    return datetime.combine(
        match.kickoff_date + timedelta(days=2), time.min, tzinfo=timezone.utc
    )


def ratings_as_of(
    observations: Iterable[MatchObservation],
    *,
    competition_id: str,
    home_team_id: str,
    away_team_id: str,
    cutoff_at: datetime,
    initial_rating: float = 1500.0,
    k_factor: float = 20.0,
    home_advantage_points: float = 60.0,
) -> EloSnapshot:
    """Reconstruct competition-specific Elo ratings strictly before cutoff.

    Elo is returned as a feature snapshot. This function deliberately does
    not convert ratings into 1X2 probabilities; that mapping needs its own
    chronological calibration and must be evaluated against the same fixtures.
    """
    if not _aware(cutoff_at):
        raise ValueError("ELO_CUTOFF_MUST_BE_TIMEZONE_AWARE")
    if not all(isinstance(value, str) and value.strip() for value in (
        competition_id, home_team_id, away_team_id
    )) or home_team_id == away_team_id:
        raise ValueError("ELO_TARGET_IDENTITY_INVALID")
    for name, value, allow_zero in (
        ("INITIAL_RATING", initial_rating, False),
        ("K_FACTOR", k_factor, False),
        ("HOME_ADVANTAGE", home_advantage_points, True),
    ):
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or (value < 0 if allow_zero else value <= 0)):
            raise ValueError(f"ELO_{name}_INVALID")

    rows = list(observations)
    id_counts: dict[str, int] = {}
    for row in rows:
        if isinstance(row, MatchObservation) and isinstance(row.fixture_id, str):
            id_counts[row.fixture_id] = id_counts.get(row.fixture_id, 0) + 1

    eligible: list[MatchObservation] = []
    non_certifiable = 0
    for row in rows:
        if not isinstance(row, MatchObservation) or row.competition_id != competition_id:
            continue
        if id_counts.get(row.fixture_id, 0) != 1:
            continue
        if not row.point_in_time_certifiable:
            non_certifiable += 1
            continue
        if observation_eligible_as_of(row, cutoff_at=cutoff_at, competition_id=competition_id):
            eligible.append(row)

    # Each timestamp is an indivisible round: all expected scores are computed
    # from the pre-round ratings and only then are rating changes applied.
    grouped: dict[datetime, list[MatchObservation]] = {}
    for row in eligible:
        grouped.setdefault(_event_time(row), []).append(row)

    ratings: dict[str, float] = {}
    played: dict[str, int] = {}
    for event_at in sorted(grouped):
        deltas: dict[str, float] = {}
        appearances: dict[str, int] = {}
        for row in sorted(grouped[event_at], key=lambda item: item.fixture_id):
            home_rating = ratings.get(row.home_team_id, float(initial_rating))
            away_rating = ratings.get(row.away_team_id, float(initial_rating))
            difference = home_rating + float(home_advantage_points) - away_rating
            expected_home = 1.0 / (1.0 + 10.0 ** (-difference / 400.0))
            actual_home = 1.0 if row.home_goals > row.away_goals else (
                0.5 if row.home_goals == row.away_goals else 0.0
            )
            change = float(k_factor) * (actual_home - expected_home)
            deltas[row.home_team_id] = deltas.get(row.home_team_id, 0.0) + change
            deltas[row.away_team_id] = deltas.get(row.away_team_id, 0.0) - change
            appearances[row.home_team_id] = appearances.get(row.home_team_id, 0) + 1
            appearances[row.away_team_id] = appearances.get(row.away_team_id, 0) + 1
        for team_id, change in deltas.items():
            ratings[team_id] = ratings.get(team_id, float(initial_rating)) + change
        for team_id, count in appearances.items():
            played[team_id] = played.get(team_id, 0) + count

    if played.get(home_team_id, 0) == 0:
        raise ValueError("ELO_HOME_TEAM_HAS_NO_CERTIFIED_HISTORY")
    if played.get(away_team_id, 0) == 0:
        raise ValueError("ELO_AWAY_TEAM_HAS_NO_CERTIFIED_HISTORY")

    home = ratings.get(home_team_id, float(initial_rating))
    away = ratings.get(away_team_id, float(initial_rating))
    difference = home + float(home_advantage_points) - away
    expected = 1.0 / (1.0 + 10.0 ** (-difference / 400.0))
    return EloSnapshot(
        model_version=MODEL_VERSION,
        cutoff_at=cutoff_at,
        competition_id=competition_id,
        home_team=TeamRating(competition_id, home_team_id, home, played[home_team_id]),
        away_team=TeamRating(competition_id, away_team_id, away, played[away_team_id]),
        home_advantage_points=float(home_advantage_points),
        expected_home_score=expected,
        rating_difference=difference,
        eligible_match_count=len(eligible),
        excluded_non_certifiable_count=non_certifiable,
    )
