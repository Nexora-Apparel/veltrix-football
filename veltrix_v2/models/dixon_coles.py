"""Independent VELTRIX v2 Dixon-Coles scoreline head (unfitted research implementation).

Inputs are externally estimated expected-goal rates and rho. This module does not
fit parameters, infer rates from legacy code, calibrate, or publish predictions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .scoreline import ScorelineDistribution, ScorelineProbability


@dataclass(frozen=True, slots=True)
class DixonColesForecast:
    distribution: ScorelineDistribution
    expected_home_goals_input: float
    expected_away_goals_input: float
    rho: float
    max_goals: int
    retained_mass: float
    tail_mass: float
    normalization: str = "explicit_conditional_on_retained_scoreline_support"


def _poisson_pmf(rate: float, maximum: int) -> list[float]:
    values = [math.exp(-rate)]
    for goals in range(1, maximum + 1):
        values.append(values[-1] * rate / goals)
    return values


def _tau(home: int, away: int, lam: float, mu: float, rho: float) -> float:
    if home == 0 and away == 0:
        return 1.0 - lam * mu * rho
    if home == 0 and away == 1:
        return 1.0 + lam * rho
    if home == 1 and away == 0:
        return 1.0 + mu * rho
    if home == 1 and away == 1:
        return 1.0 - rho
    return 1.0


def build_dixon_coles_forecast(
    *,
    fixture_id: str,
    expected_home_goals: float,
    expected_away_goals: float,
    rho: float = 0.0,
    tail_tolerance: float = 1e-8,
    initial_max_goals: int = 8,
    maximum_max_goals: int = 20,
    model_version: str = "veltrix-v2-dixon-coles-0.1",
) -> DixonColesForecast:
    """Build a coherent joint scoreline distribution with explicit tail diagnostics.

    The finite support is conditionally normalized only after the omitted tail is
    below tail_tolerance. The tail is reported, never silently discarded.
    """
    for name, value in (
        ("expected_home_goals", expected_home_goals),
        ("expected_away_goals", expected_away_goals),
        ("rho", rho),
        ("tail_tolerance", tail_tolerance),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"DIXON_COLES_INVALID_{name.upper()}")
    if expected_home_goals <= 0 or expected_away_goals <= 0:
        raise ValueError("DIXON_COLES_GOAL_RATES_MUST_BE_POSITIVE")
    if not 0 < tail_tolerance < 0.01:
        raise ValueError("DIXON_COLES_TAIL_TOLERANCE_INVALID")
    if type(initial_max_goals) is not int or type(maximum_max_goals) is not int:
        raise ValueError("DIXON_COLES_MAX_GOALS_INVALID")
    if not 2 <= initial_max_goals <= maximum_max_goals <= 30:
        raise ValueError("DIXON_COLES_MAX_GOALS_INVALID")
    if not fixture_id.strip() or not model_version.strip():
        raise ValueError("DIXON_COLES_IDENTITY_REQUIRED")

    lam, mu = float(expected_home_goals), float(expected_away_goals)
    rho_value = float(rho)
    low_score_taus = (
        _tau(0, 0, lam, mu, rho_value),
        _tau(0, 1, lam, mu, rho_value),
        _tau(1, 0, lam, mu, rho_value),
        _tau(1, 1, lam, mu, rho_value),
    )
    if any(not math.isfinite(value) or value <= 0 for value in low_score_taus):
        raise ValueError("DIXON_COLES_RHO_PRODUCES_NONPOSITIVE_LOW_SCORE_MASS")

    maximum = initial_max_goals
    while True:
        home_pmf = _poisson_pmf(lam, maximum)
        away_pmf = _poisson_pmf(mu, maximum)
        raw = []
        retained = 0.0
        for home in range(maximum + 1):
            for away in range(maximum + 1):
                mass = home_pmf[home] * away_pmf[away] * _tau(home, away, lam, mu, rho_value)
                if not math.isfinite(mass) or mass < 0:
                    raise ValueError("DIXON_COLES_INVALID_SCORELINE_MASS")
                raw.append((home, away, mass))
                retained += mass
        tail = max(0.0, 1.0 - retained)
        if tail <= tail_tolerance:
            break
        if maximum >= maximum_max_goals:
            raise ValueError("DIXON_COLES_TAIL_MASS_EXCEEDS_TOLERANCE")
        maximum = min(maximum_max_goals, maximum + 2)

    if retained <= 0 or retained > 1.0 + 1e-9:
        raise ValueError("DIXON_COLES_RETAINED_MASS_INVALID")
    rows = tuple(
        ScorelineProbability(home, away, mass / retained)
        for home, away, mass in raw
    )
    distribution = ScorelineDistribution(fixture_id, model_version, rows)
    return DixonColesForecast(
        distribution=distribution,
        expected_home_goals_input=lam,
        expected_away_goals_input=mu,
        rho=rho_value,
        max_goals=maximum,
        retained_mass=retained,
        tail_mass=tail,
    )
