"""Poisson / Dixon-Coles score-grid prediction head.

Research component: produces coherent 1X2, BTTS and totals probabilities from
pre-match expected goals. Parameters must be fitted on training windows only.
"""
from __future__ import annotations

import math
from typing import Any


def _poisson_pmf(rate: float, max_goals: int) -> list[float]:
    values = [math.exp(-rate)]
    for goals in range(1, max_goals + 1):
        values.append(values[-1] * rate / goals)
    return values


def dixon_coles_markets(
    home_lambda: float,
    away_mu: float,
    *,
    rho: float = -0.05,
    max_goals: int = 20,
    totals_lines: tuple[float, ...] = (0.5, 1.5, 2.5, 3.5, 4.5),
) -> dict[str, Any]:
    """Return a coherent score matrix and market probabilities.

    The four low-score cells receive the Dixon-Coles tau correction. The
    resulting finite grid is normalized once, after correction. A 20-goal
    ceiling makes truncation negligible for ordinary football rates; callers
    receive the omitted independent-Poisson tail estimate as a diagnostic.
    """
    lam, mu, rho = float(home_lambda), float(away_mu), float(rho)
    if not math.isfinite(lam) or not math.isfinite(mu) or lam <= 0 or mu <= 0:
        raise ValueError("expected goals must be finite and positive")
    if lam > 10 or mu > 10:
        raise ValueError("expected goals above 10 are outside supported football range")
    if not math.isfinite(rho) or not -0.25 <= rho <= 0.25:
        raise ValueError("rho must be finite and between -0.25 and 0.25")
    if isinstance(max_goals, bool) or not isinstance(max_goals, int) or not 12 <= max_goals <= 40:
        raise ValueError("max_goals must be an integer between 12 and 40")
    if not totals_lines or any(not math.isfinite(float(x)) or float(x) < 0 for x in totals_lines):
        raise ValueError("totals_lines must contain finite non-negative values")

    hp, ap = _poisson_pmf(lam, max_goals), _poisson_pmf(mu, max_goals)
    grid: list[list[float]] = []
    for h, ph in enumerate(hp):
        row = []
        for a, pa in enumerate(ap):
            tau = 1.0
            if h == 0 and a == 0:
                tau = 1.0 - lam * mu * rho
            elif h == 0 and a == 1:
                tau = 1.0 + lam * rho
            elif h == 1 and a == 0:
                tau = 1.0 + mu * rho
            elif h == 1 and a == 1:
                tau = 1.0 - rho
            if tau < 0:
                raise ValueError("rho produces a negative low-score probability")
            row.append(ph * pa * tau)
        grid.append(row)

    mass = sum(sum(row) for row in grid)
    if not math.isfinite(mass) or mass <= 0:
        raise ValueError("score probability mass is invalid")
    grid = [[p / mass for p in row] for row in grid]

    home_win = draw = away_win = btts_yes = 0.0
    totals_over = {float(line): 0.0 for line in totals_lines}
    scorelines = []
    for h, row in enumerate(grid):
        for a, probability in enumerate(row):
            if h > a:
                home_win += probability
            elif h == a:
                draw += probability
            else:
                away_win += probability
            if h > 0 and a > 0:
                btts_yes += probability
            for line in totals_over:
                if h + a > line:
                    totals_over[line] += probability
            scorelines.append((probability, h, a))

    tail_home = max(0.0, 1.0 - sum(hp))
    tail_away = max(0.0, 1.0 - sum(ap))
    markets = {
        "1x2": {"H": home_win, "D": draw, "A": away_win},
        "btts": {"yes": btts_yes, "no": 1.0 - btts_yes},
        "totals": {
            str(line): {"over": probability, "under": 1.0 - probability}
            for line, probability in sorted(totals_over.items())
        },
    }
    return {
        "status": "SHADOW_RESEARCH",
        "expected_goals": {"home_lambda": lam, "away_mu": mu},
        "rho": rho,
        "max_goals": max_goals,
        "truncated_poisson_tail_estimate": {
            "home": tail_home, "away": tail_away,
            "upper_bound_union": min(1.0, tail_home + tail_away),
        },
        "markets": markets,
        "top_scorelines": [
            {"score": f"{h}-{a}", "probability": p}
            for p, h, a in sorted(scorelines, reverse=True)[:10]
        ],
    }
