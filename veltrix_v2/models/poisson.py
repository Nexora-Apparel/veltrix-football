"""Point-in-time, results-only Poisson baseline for VELTRIX 2.0.

This is a new model implementation. It does not import or call legacy
prediction, calibration, prior, feature, or value-bet code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Iterable


MODEL_VERSION = "veltrix-results-poisson-v1"
MAX_GOALS = 12


class InsufficientHistoryError(ValueError):
    """Raised when either team has no eligible result history."""


@dataclass(frozen=True)
class MatchObservation:
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime | None
    available_at: datetime
    recorded_at: datetime
    home_goals: int
    away_goals: int
    kickoff_date: date | None = None


@dataclass(frozen=True)
class PoissonPrediction:
    model_version: str
    cutoff_at: datetime
    expected_home_goals: float
    expected_away_goals: float
    home_win: float
    draw: float
    away_win: float
    btts_yes: float
    over_2_5: float
    evidence_match_count: int
    home_team_match_count: int
    away_team_match_count: int
    sample_floor_met: bool
    publishable: bool
    publication_reason: str


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _valid_observation(match: MatchObservation) -> bool:
    if not isinstance(match, MatchObservation):
        return False
    if not all(isinstance(value, str) and value.strip() for value in (
        match.fixture_id, match.competition_id, match.home_team_id, match.away_team_id
    )):
        return False
    if match.home_team_id == match.away_team_id:
        return False
    if not _aware(match.available_at) or not _aware(match.recorded_at):
        return False
    if match.recorded_at < match.available_at:
        return False
    if match.kickoff_at is None:
        if not isinstance(match.kickoff_date, date) or isinstance(match.kickoff_date, datetime):
            return False
        safe_after_date = datetime.combine(
            match.kickoff_date + timedelta(days=2), time.min, tzinfo=timezone.utc
        )
        if match.available_at.astimezone(timezone.utc) < safe_after_date:
            return False
    else:
        if match.kickoff_date is not None or not _aware(match.kickoff_at):
            return False
        if match.available_at < match.kickoff_at:
            return False
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
           for value in (match.home_goals, match.away_goals)):
        return False
    return True



def observation_eligible_as_of(match: MatchObservation, *, cutoff_at: datetime,
                               competition_id: str | None = None) -> bool:
    """Return whether a result is safely usable at a point-in-time cutoff.

    Date-only source records are eligible only from 00:00 UTC two calendar
    days after their source-local match date, conservatively covering civil
    timezone differences. Exact kickoff observations use their timestamp.
    """
    if not _aware(cutoff_at) or not _valid_observation(match):
        return False
    if competition_id is not None and match.competition_id != competition_id:
        return False
    if match.kickoff_at is not None:
        kickoff_precedes_cutoff = match.kickoff_at < cutoff_at
    else:
        safe_boundary = datetime.combine(
            match.kickoff_date + timedelta(days=2), time.min, tzinfo=timezone.utc
        )
        kickoff_precedes_cutoff = cutoff_at.astimezone(timezone.utc) >= safe_boundary
    return kickoff_precedes_cutoff and match.available_at <= cutoff_at and match.recorded_at <= cutoff_at


def _poisson_pmf(mean: float, goals: int) -> float:
    return math.exp(-mean) * (mean ** goals) / math.factorial(goals)


def _posterior_mean(total: int, count: int, league_mean: float, prior_matches: float) -> float:
    return (total + prior_matches * league_mean) / (count + prior_matches)


def predict_match(
    observations: Iterable[MatchObservation],
    *,
    competition_id: str,
    home_team_id: str,
    away_team_id: str,
    kickoff_at: datetime,
    cutoff_at: datetime,
    prior_matches: float = 5.0,
) -> PoissonPrediction:
    """Estimate 1X2, BTTS and O/U 2.5 using only results knowable at cutoff.

    Missing/late timestamps are not inferred. Observations with kickoff,
    publication/availability, or ingestion time after cutoff are excluded.
    Team estimates are shrunk toward same-competition goal rates. If a team
    has zero eligible history, no generic league-only forecast is produced.
    """
    if not all(_aware(value) for value in (kickoff_at, cutoff_at)):
        raise ValueError("CUTOFF_AND_KICKOFF_MUST_BE_TIMEZONE_AWARE")
    if kickoff_at <= cutoff_at:
        raise ValueError("TARGET_KICKOFF_MUST_BE_AFTER_CUTOFF")
    if not all(isinstance(value, str) and value.strip() for value in (
        competition_id, home_team_id, away_team_id
    )) or home_team_id == away_team_id:
        raise ValueError("TARGET_FIXTURE_IDENTITY_INVALID")
    if (not isinstance(prior_matches, (int, float)) or isinstance(prior_matches, bool)
            or not math.isfinite(prior_matches) or prior_matches <= 0):
        raise ValueError("PRIOR_STRENGTH_INVALID")

    candidates = list(observations)
    fixture_id_counts: dict[str, int] = {}
    for candidate in candidates:
        if isinstance(candidate, MatchObservation) and isinstance(candidate.fixture_id, str):
            fixture_id_counts[candidate.fixture_id] = fixture_id_counts.get(candidate.fixture_id, 0) + 1

    eligible: list[MatchObservation] = []
    for match in candidates:
        if not _valid_observation(match):
            continue
        # Conflicting or repeated fixture identities are excluded independent of input order.
        if fixture_id_counts.get(match.fixture_id, 0) != 1:
            continue
        if not observation_eligible_as_of(match, cutoff_at=cutoff_at, competition_id=competition_id):
            continue
        eligible.append(match)

    if not eligible:
        raise InsufficientHistoryError("NO_POINT_IN_TIME_ELIGIBLE_COMPETITION_HISTORY")

    home_team = [m for m in eligible if home_team_id in (m.home_team_id, m.away_team_id)]
    away_team = [m for m in eligible if away_team_id in (m.home_team_id, m.away_team_id)]
    if not home_team:
        raise InsufficientHistoryError("HOME_TEAM_HAS_NO_ELIGIBLE_HISTORY")
    if not away_team:
        raise InsufficientHistoryError("AWAY_TEAM_HAS_NO_ELIGIBLE_HISTORY")

    league_home_total = sum(m.home_goals for m in eligible)
    league_away_total = sum(m.away_goals for m in eligible)
    league_home_mean = league_home_total / len(eligible)
    league_away_mean = league_away_total / len(eligible)
    if league_home_mean <= 0 or league_away_mean <= 0:
        raise InsufficientHistoryError("COMPETITION_GOAL_BASELINE_INVALID")

    def team_rates(team_id: str) -> tuple[float, float, int]:
        scored = conceded = count = 0
        for m in eligible:
            if m.home_team_id == team_id:
                scored += m.home_goals
                conceded += m.away_goals
                count += 1
            elif m.away_team_id == team_id:
                scored += m.away_goals
                conceded += m.home_goals
                count += 1
        attack_mean = _posterior_mean(scored, count, (league_home_mean + league_away_mean) / 2, prior_matches)
        defence_mean = _posterior_mean(conceded, count, (league_home_mean + league_away_mean) / 2, prior_matches)
        return attack_mean, defence_mean, count

    home_attack, home_conceded, home_count = team_rates(home_team_id)
    away_attack, away_conceded, away_count = team_rates(away_team_id)
    league_mean = (league_home_mean + league_away_mean) / 2
    home_lambda = league_home_mean * (home_attack / league_mean) * (away_conceded / league_mean)
    away_lambda = league_away_mean * (away_attack / league_mean) * (home_conceded / league_mean)
    home_lambda = min(max(home_lambda, 0.05), 5.0)
    away_lambda = min(max(away_lambda, 0.05), 5.0)

    home_probs = [_poisson_pmf(home_lambda, i) for i in range(MAX_GOALS + 1)]
    away_probs = [_poisson_pmf(away_lambda, i) for i in range(MAX_GOALS + 1)]
    mass = sum(home_probs) * sum(away_probs)
    if mass <= 0 or not math.isfinite(mass):
        raise ValueError("POISSON_SCORE_MASS_INVALID")

    h = d = a = btts = over = 0.0
    for hg, hp in enumerate(home_probs):
        for ag, ap in enumerate(away_probs):
            probability = hp * ap / mass
            if hg > ag:
                h += probability
            elif hg == ag:
                d += probability
            else:
                a += probability
            if hg > 0 and ag > 0:
                btts += probability
            if hg + ag >= 3:
                over += probability

    total = h + d + a
    h, d, a = h / total, d / total, a / total
    sample_floor_met = len(eligible) >= 100 and min(home_count, away_count) >= 5
    # Model-level publication remains locked until independent certification.
    publishable = False
    reason = "MODEL_NOT_CERTIFIED" if sample_floor_met else "INSUFFICIENT_EVIDENCE_FOR_MODEL_REVIEW"
    return PoissonPrediction(
        model_version=MODEL_VERSION,
        cutoff_at=cutoff_at,
        expected_home_goals=home_lambda,
        expected_away_goals=away_lambda,
        home_win=h,
        draw=d,
        away_win=a,
        btts_yes=btts,
        over_2_5=over,
        evidence_match_count=len(eligible),
        home_team_match_count=home_count,
        away_team_match_count=away_count,
        sample_floor_met=sample_floor_met,
        publishable=publishable,
        publication_reason=reason,
    )
