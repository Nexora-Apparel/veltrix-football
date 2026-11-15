"""Training-fold Dixon-Coles low-score dependence parameter estimation.

The fitter consumes only caller-supplied training-fold score-rate tuples. It
never reads evaluation targets or timestamps and must be invoked separately
inside each chronological training fold.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class DixonColesFit:
    rho: float
    log_likelihood: float
    observations: int
    grid_step: float
    converged: bool
    method: str = "bounded_profile_grid_mle"


def _tau(h: int, a: int, lh: float, la: float, rho: float) -> float:
    if h == 0 and a == 0:
        return 1.0 - lh * la * rho
    if h == 0 and a == 1:
        return 1.0 + lh * rho
    if h == 1 and a == 0:
        return 1.0 + la * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def fit_dixon_coles_rho(
    training_rows: Iterable[tuple[float, float, int, int]],
    *,
    rho_min: float = -0.2,
    rho_max: float = 0.2,
    grid_step: float = 0.001,
    minimum_rows: int = 30,
) -> DixonColesFit:
    """Fit rho by profile likelihood over independent Poisson score rates.

    Each row is (expected_home_goals, expected_away_goals, home_goals,
    away_goals). Rates must have been estimated using the same training fold.
    The function refuses small samples and invalid/non-positive tau factors.
    """
    rows = list(training_rows)
    if len(rows) < minimum_rows:
        raise ValueError("DIXON_COLES_TRAINING_SAMPLE_TOO_SMALL")
    if not all(math.isfinite(x) for x in (rho_min, rho_max, grid_step)):
        raise ValueError("DIXON_COLES_SEARCH_PARAMETERS_INVALID")
    if rho_min >= rho_max or grid_step <= 0 or rho_min < -1 or rho_max > 1:
        raise ValueError("DIXON_COLES_SEARCH_RANGE_INVALID")
    clean = []
    for lh, la, hg, ag in rows:
        if (not math.isfinite(lh) or not math.isfinite(la) or lh <= 0 or la <= 0
                or not isinstance(hg, int) or isinstance(hg, bool) or hg < 0
                or not isinstance(ag, int) or isinstance(ag, bool) or ag < 0):
            raise ValueError("DIXON_COLES_TRAINING_ROW_INVALID")
        clean.append((lh, la, hg, ag))
    candidates = []
    count = int(math.floor((rho_max - rho_min) / grid_step))
    for i in range(count + 1):
        rho = rho_min + i * grid_step
        ll = 0.0
        valid = True
        for lh, la, hg, ag in clean:
            tau = _tau(hg, ag, lh, la, rho)
            if tau <= 0 or not math.isfinite(tau):
                valid = False
                break
            ll += (-lh + hg * math.log(lh) - math.lgamma(hg + 1)
                   - la + ag * math.log(la) - math.lgamma(ag + 1)
                   + math.log(tau))
        if valid and math.isfinite(ll):
            candidates.append((ll, rho))
    if not candidates:
        raise ValueError("DIXON_COLES_NO_VALID_PARAMETER")
    best_ll, best_rho = max(candidates, key=lambda x: (x[0], -abs(x[1])))
    return DixonColesFit(
        rho=best_rho, log_likelihood=best_ll, observations=len(clean),
        grid_step=grid_step,
        converged=(best_rho not in (rho_min, rho_min + count * grid_step)),
    )

@dataclass(frozen=True)
class FittedDixonColesPrediction:
    prediction: object
    fit: DixonColesFit


def predict_dixon_coles_match(
    observations: Iterable[object], *,
    competition_id: str, home_team_id: str, away_team_id: str,
    kickoff_at, cutoff_at, minimum_fit_rows: int = 30,
    rho_min: float = -0.2, rho_max: float = 0.2, grid_step: float = 0.001,
):
    """Fit rho from rolling, strictly earlier training predictions, then score target.

    For every rho-training match, its independent Poisson rates are estimated
    from observations available before that match's kickoff. The target's
    fitted rho is therefore never estimated from target or later outcomes.
    """
    from datetime import timedelta
    from veltrix_v2.models.poisson import (
        MatchObservation, observation_eligible_as_of, predict_match,
    )

    source = list(observations)
    if any(not isinstance(row, MatchObservation) for row in source):
        raise ValueError("DIXON_COLES_OBSERVATION_TYPE_INVALID")
    source.sort(key=lambda row: row.kickoff_at or row.available_at)
    rate_rows = []
    for historical in source:
        if historical.competition_id != competition_id:
            continue
        if historical.point_in_time_certifiable is not True:
            continue
        if historical.kickoff_at is None:
            continue
        historical_cutoff = historical.kickoff_at - timedelta(seconds=1)
        if historical_cutoff >= cutoff_at:
            continue
        prior = [
            row for row in source
            if row.fixture_id != historical.fixture_id
            and row.competition_id == competition_id
            and row.point_in_time_certifiable is True
            and observation_eligible_as_of(row, cutoff_at=historical_cutoff,
                                           competition_id=competition_id)
        ]
        try:
            baseline = predict_match(
                prior, competition_id=competition_id,
                home_team_id=historical.home_team_id,
                away_team_id=historical.away_team_id,
                kickoff_at=historical.kickoff_at,
                cutoff_at=historical_cutoff,
            )
        except (TypeError, ValueError):
            continue
        rate_rows.append((
            baseline.expected_home_goals, baseline.expected_away_goals,
            historical.home_goals, historical.away_goals,
        ))
    fitted = fit_dixon_coles_rho(
        rate_rows, minimum_rows=minimum_fit_rows, rho_min=rho_min,
        rho_max=rho_max, grid_step=grid_step,
    )
    target_prediction = predict_match(
        source, competition_id=competition_id,
        home_team_id=home_team_id, away_team_id=away_team_id,
        kickoff_at=kickoff_at, cutoff_at=cutoff_at,
        dixon_coles_rho=fitted.rho,
    )
    return FittedDixonColesPrediction(target_prediction, fitted)
