"""Training-fold Dixon-Coles low-score dependence parameter estimation.

The fitter consumes only caller-supplied training-fold score-rate tuples. It
never reads evaluation targets or timestamps and must be invoked separately
inside each chronological training fold.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import heapq
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
class DixonColesTrainingRateRow:
    fixture_id: str
    kickoff_at: object
    available_at: object
    recorded_at: object
    expected_home_goals: float
    expected_away_goals: float
    home_goals: int
    away_goals: int


def build_dixon_coles_rate_history(
    observations: Iterable[object], *, competition_id: str, as_of,
) -> tuple[DixonColesTrainingRateRow, ...]:
    """Precompute rolling PIT Poisson rates in one chronological pass.

    Earlier fixtures enter the active statistics only once both their
    availability and recording clocks are at or before each historical
    kickoff. This is O(n log n), avoids repeated full-fold model fits, and
    preserves the exact conservative target-cutoff rule.
    """
    from veltrix_v2.models.poisson import (
        MatchObservation, observation_eligible_as_of,
    )
    source = list(observations)
    if any(not isinstance(row, MatchObservation) for row in source):
        raise ValueError("DIXON_COLES_OBSERVATION_TYPE_INVALID")
    counts: dict[str, int] = {}
    for row in source:
        counts[row.fixture_id] = counts.get(row.fixture_id, 0) + 1
    source = [row for row in source
              if counts.get(row.fixture_id) == 1
              and row.competition_id == competition_id
              and row.point_in_time_certifiable is True
              and row.kickoff_at is not None
              and observation_eligible_as_of(row, cutoff_at=as_of,
                                             competition_id=competition_id)]
    source.sort(key=lambda row: (row.kickoff_at, row.fixture_id))

    # Heap entries are ready_at, sequence, observation. The sequence avoids
    # comparing dataclass objects when two source clocks are identical.
    pending = []
    sequence = 0
    active_count = 0
    league_home_sum = league_away_sum = 0.0
    home_stats: dict[str, list[float]] = {}
    away_stats: dict[str, list[float]] = {}
    rate_rows: list[DixonColesTrainingRateRow] = []

    def add_active(row):
        nonlocal active_count, league_home_sum, league_away_sum
        active_count += 1
        league_home_sum += row.home_goals
        league_away_sum += row.away_goals
        hs = home_stats.setdefault(row.home_team_id, [0.0, 0.0, 0.0])
        hs[0] += row.home_goals
        hs[1] += row.away_goals
        hs[2] += 1
        aw = away_stats.setdefault(row.away_team_id, [0.0, 0.0, 0.0])
        aw[0] += row.away_goals
        aw[1] += row.home_goals
        aw[2] += 1

    for index, historical in enumerate(source):
        cutoff = historical.kickoff_at - timedelta(seconds=1)
        while pending and pending[0][0] <= cutoff:
            _, _, ready_row = heapq.heappop(pending)
            add_active(ready_row)

        home = home_stats.get(historical.home_team_id)
        away = away_stats.get(historical.away_team_id)
        if active_count and home and away and home[2] > 0 and away[2] > 0:
            league_home = league_home_sum / active_count
            league_away = league_away_sum / active_count
            if league_home > 0 and league_away > 0:
                home_attack = (home[0] + 5.0 * league_home) / (home[2] + 5.0)
                home_defence = (home[1] + 5.0 * league_away) / (home[2] + 5.0)
                away_attack = (away[0] + 5.0 * league_away) / (away[2] + 5.0)
                away_defence = (away[1] + 5.0 * league_home) / (away[2] + 5.0)
                home_rate = min(max(home_attack * away_defence / league_home, 0.05), 5.0)
                away_rate = min(max(away_attack * home_defence / league_away, 0.05), 5.0)
                rate_rows.append(DixonColesTrainingRateRow(
                    fixture_id=historical.fixture_id,
                    kickoff_at=historical.kickoff_at,
                    available_at=historical.available_at,
                    recorded_at=historical.recorded_at,
                    expected_home_goals=home_rate,
                    expected_away_goals=away_rate,
                    home_goals=historical.home_goals,
                    away_goals=historical.away_goals,
                ))

        ready_at = max(historical.available_at, historical.recorded_at)
        heapq.heappush(pending, (ready_at, sequence, historical))
        sequence += 1

    return tuple(rate_rows)


@dataclass(frozen=True)
class FittedDixonColesPrediction:
    prediction: object
    fit: DixonColesFit


def predict_dixon_coles_match(
    observations: Iterable[object], *,
    competition_id: str, home_team_id: str, away_team_id: str,
    kickoff_at, cutoff_at, minimum_fit_rows: int = 30,
    rho_min: float = -0.2, rho_max: float = 0.2, grid_step: float = 0.001,
    rate_history: Iterable[DixonColesTrainingRateRow] | None = None,
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
    precomputed = (
        build_dixon_coles_rate_history(source, competition_id=competition_id, as_of=cutoff_at)
        if rate_history is None else tuple(rate_history)
    )
    if any(not isinstance(row, DixonColesTrainingRateRow) for row in precomputed):
        raise ValueError("DIXON_COLES_RATE_HISTORY_INVALID")
    # The target fold admits only rate rows whose result was both available
    # and recorded by this exact target cutoff and whose match predates target.
    rate_rows = [
        (row.expected_home_goals, row.expected_away_goals,
         row.home_goals, row.away_goals)
        for row in precomputed
        if row.kickoff_at < kickoff_at
        and row.available_at <= cutoff_at
        and row.recorded_at <= cutoff_at
    ]
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
