"""Independent, leakage-safe team-strength Poisson estimator for VELTRIX v2.

Fits attack/defence strengths from settled, timestamp-qualified scores. It is a
research estimator only: no legacy priors, external provider calls, calibration,
persistence or publication.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TrainingMatch:
    fixture_id: str
    competition_key: str
    season: str
    kickoff_utc: datetime
    available_at_utc: datetime
    home_team_id: str
    away_team_id: str
    home_goals: int
    away_goals: int
    source_observation_id: str
    quality_state: str = "valid"
    availability_basis: str = "unspecified"
    source_training_approved: bool = False

    def __post_init__(self) -> None:
        for field in ("kickoff_utc", "available_at_utc"):
            value = getattr(self, field)
            stamp = value
            if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError(f"POISSON_TRAIN_{field.upper()}_MUST_BE_AWARE")
            object.__setattr__(self, field, stamp.astimezone(timezone.utc))
        if any(not str(getattr(self, field)).strip() for field in (
            "fixture_id", "competition_key", "season", "home_team_id",
            "away_team_id", "source_observation_id",
        )):
            raise ValueError("POISSON_TRAIN_IDENTITY_REQUIRED")
        if self.home_team_id == self.away_team_id:
            raise ValueError("POISSON_TRAIN_TEAMS_MUST_DIFFER")
        if type(self.home_goals) is not int or type(self.away_goals) is not int or min(self.home_goals, self.away_goals) < 0:
            raise ValueError("POISSON_TRAIN_INVALID_SCORE")
        if self.available_at_utc < self.kickoff_utc:
            raise ValueError("POISSON_TRAIN_RESULT_AVAILABLE_BEFORE_KICKOFF")
        if self.availability_basis not in {"unspecified", "source_timestamp", "verified_published_timestamp", "date_only_conservative_4d", "provider_finished_status_conservative_4d"}:
            raise ValueError("POISSON_TRAIN_AVAILABILITY_BASIS_INVALID")
        if type(self.source_training_approved) is not bool:
            raise ValueError("POISSON_TRAIN_SOURCE_APPROVAL_FLAG_MUST_BE_BOOLEAN")


@dataclass(frozen=True, slots=True)
class TeamStrength:
    team_id: str
    attack_log_strength: float
    defence_log_strength: float


@dataclass(frozen=True, slots=True)
class PoissonStrengthModel:
    model_version: str
    competition_key: str
    season: str
    training_cutoff_utc: datetime
    intercept_log_rate: float
    home_advantage_log_rate: float
    teams: tuple[TeamStrength, ...]
    training_match_count: int
    training_team_count: int
    training_fixture_ids: tuple[str, ...]
    training_observation_ids: tuple[str, ...]
    training_availability_bases: tuple[str, ...]
    objective: float
    converged: bool
    iterations: int
    recency_half_life_days: float

    def expected_goals(self, home_team_id: str, away_team_id: str) -> tuple[float, float]:
        if not self.converged:
            raise ValueError("POISSON_PREDICTION_MODEL_NOT_CONVERGED")
        strengths = {row.team_id: row for row in self.teams}
        if home_team_id not in strengths or away_team_id not in strengths:
            raise ValueError("POISSON_PREDICTION_TEAM_NOT_IN_TRAINING")
        if home_team_id == away_team_id:
            raise ValueError("POISSON_PREDICTION_TEAMS_MUST_DIFFER")
        home = strengths[home_team_id]
        away = strengths[away_team_id]
        home_eta = self.intercept_log_rate + self.home_advantage_log_rate + home.attack_log_strength - away.defence_log_strength
        away_eta = self.intercept_log_rate + away.attack_log_strength - home.defence_log_strength
        if max(home_eta, away_eta) > 5 or min(home_eta, away_eta) < -10:
            raise ValueError("POISSON_PREDICTION_RATE_OUT_OF_RANGE")
        return math.exp(home_eta), math.exp(away_eta)


def _objective_gradient(rows, teams, params, ridge):
    n = len(teams)
    intercept, home_adv = params[0], params[1]
    attack = params[2:2+n]
    defence = params[2+n:2+2*n]
    gradient = [0.0] * len(params)
    loss = 0.0
    index = {team: i for i, team in enumerate(teams)}
    for row, weight in rows:
        h, a = index[row.home_team_id], index[row.away_team_id]
        eta_h = intercept + home_adv + attack[h] - defence[a]
        eta_a = intercept + attack[a] - defence[h]
        if max(eta_h, eta_a) > 20 or min(eta_h, eta_a) < -20:
            return float("inf"), [float("inf")] * len(params)
        lam_h, lam_a = math.exp(eta_h), math.exp(eta_a)
        loss += weight * (lam_h - row.home_goals * eta_h + math.lgamma(row.home_goals + 1))
        loss += weight * (lam_a - row.away_goals * eta_a + math.lgamma(row.away_goals + 1))
        dh, da = weight * (lam_h - row.home_goals), weight * (lam_a - row.away_goals)
        gradient[0] += dh + da
        gradient[1] += dh
        gradient[2+h] += dh
        gradient[2+a] += da
        gradient[2+n+a] -= dh
        gradient[2+n+h] -= da
    for i in range(n):
        loss += 0.5 * ridge * (attack[i] ** 2 + defence[i] ** 2)
        gradient[2+i] += ridge * attack[i]
        gradient[2+n+i] += ridge * defence[i]
    loss += 0.5 * ridge * home_adv ** 2
    gradient[1] += ridge * home_adv
    return loss, gradient


def fit_poisson_strength_model(
    matches: Iterable[TrainingMatch],
    *,
    competition_key: str,
    season: str,
    training_cutoff_utc: datetime,
    minimum_matches: int = 40,
    minimum_team_matches: int = 1,
    recency_half_life_days: float = 180.0,
    ridge: float = 0.05,
    learning_rate: float = 0.025,
    max_iterations: int = 6000,
    tolerance: float = 1e-8,
    model_version: str = "veltrix-v2-team-poisson-0.1",
) -> PoissonStrengthModel:
    if training_cutoff_utc.tzinfo is None or training_cutoff_utc.utcoffset() is None:
        raise ValueError("POISSON_TRAIN_CUTOFF_MUST_BE_AWARE")
    cutoff = training_cutoff_utc.astimezone(timezone.utc)
    if not competition_key.strip() or not season.strip() or not model_version.strip():
        raise ValueError("POISSON_TRAIN_SCOPE_REQUIRED")
    numeric_parameters = (recency_half_life_days, ridge, learning_rate, tolerance)
    if (type(minimum_matches) is not int or minimum_matches < 1
        or type(minimum_team_matches) is not int or minimum_team_matches < 1
        or type(max_iterations) is not int or max_iterations < 1
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in numeric_parameters)
        or recency_half_life_days <= 0
        or ridge < 0
        or learning_rate <= 0
        or tolerance <= 0):
        raise ValueError("POISSON_TRAIN_HYPERPARAMETER_INVALID")

    eligible = [
        row for row in matches
        if row.competition_key == competition_key
        and row.season == season
        and row.quality_state == "valid"
        and row.kickoff_utc < cutoff
        and row.available_at_utc <= cutoff
    ]
    eligible.sort(key=lambda row: (row.kickoff_utc, row.fixture_id))
    if any(row.availability_basis == "unspecified" for row in eligible):
        raise ValueError("POISSON_TRAIN_AVAILABILITY_BASIS_REQUIRED")
    if any(not row.source_training_approved for row in eligible):
        raise ValueError("POISSON_TRAIN_SOURCE_NOT_APPROVED_FOR_MODEL_TRAINING")
    fixture_ids = [row.fixture_id for row in eligible]
    observation_ids = [row.source_observation_id for row in eligible]
    if len(fixture_ids) != len(set(fixture_ids)) or len(observation_ids) != len(set(observation_ids)):
        raise ValueError("POISSON_TRAIN_DUPLICATE_PROVENANCE")
    if len(eligible) < minimum_matches:
        raise ValueError(f"POISSON_TRAIN_INSUFFICIENT_MATCHES:{len(eligible)}")
    teams = sorted({row.home_team_id for row in eligible} | {row.away_team_id for row in eligible})
    appearances = {team: 0 for team in teams}
    for row in eligible:
        appearances[row.home_team_id] += 1
        appearances[row.away_team_id] += 1
    if len(teams) < 2 or min(appearances.values()) < minimum_team_matches:
        raise ValueError("POISSON_TRAIN_INSUFFICIENT_TEAM_COVERAGE")

    latest_kickoff = max(row.kickoff_utc for row in eligible)
    weighted_rows = [
        (row, math.exp(-math.log(2.0) * max(0.0, (latest_kickoff - row.kickoff_utc).total_seconds() / 86400.0) / recency_half_life_days))
        for row in eligible
    ]
    mean_goals = sum(row.home_goals + row.away_goals for row in eligible) / (2 * len(eligible))
    if mean_goals <= 0:
        raise ValueError("POISSON_TRAIN_NO_GOALS_OBSERVED")
    params = [math.log(mean_goals), 0.0] + [0.0] * (2 * len(teams))
    first_moment = [0.0] * len(params)
    second_moment = [0.0] * len(params)
    beta1, beta2, epsilon = 0.9, 0.999, 1e-8
    converged = False
    objective = float("inf")
    for iteration in range(1, max_iterations + 1):
        objective, gradient = _objective_gradient(weighted_rows, teams, params, ridge)
        norm = math.sqrt(sum(value * value for value in gradient) / len(gradient))
        if norm < tolerance:
            converged = True
            break
        for j, grad in enumerate(gradient):
            first_moment[j] = beta1 * first_moment[j] + (1 - beta1) * grad
            second_moment[j] = beta2 * second_moment[j] + (1 - beta2) * grad * grad
            m_hat = first_moment[j] / (1 - beta1 ** iteration)
            v_hat = second_moment[j] / (1 - beta2 ** iteration)
            params[j] -= learning_rate * m_hat / (math.sqrt(v_hat) + epsilon)
        n = len(teams)
        attack_mean = sum(params[2:2+n]) / n
        defence_mean = sum(params[2+n:2+2*n]) / n
        for j in range(n):
            params[2+j] -= attack_mean
            params[2+n+j] -= defence_mean
        if not all(math.isfinite(value) for value in params):
            raise ValueError("POISSON_TRAIN_NUMERICAL_DIVERGENCE")
    objective, _ = _objective_gradient(weighted_rows, teams, params, ridge)
    if not math.isfinite(objective):
        raise ValueError("POISSON_TRAIN_NONFINITE_OBJECTIVE")
    n = len(teams)
    team_strengths = tuple(
        TeamStrength(team, params[2+i], params[2+n+i])
        for i, team in enumerate(teams)
    )
    return PoissonStrengthModel(
        model_version, competition_key, season, cutoff, params[0], params[1],
        team_strengths, len(eligible), len(teams), tuple(sorted(fixture_ids)),
        tuple(sorted(observation_ids)),
        tuple(sorted({row.availability_basis for row in eligible})),
        objective, converged, iteration, recency_half_life_days,
    )
