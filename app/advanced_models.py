"""Experimental extensions for football probability modelling.

All functions are deterministic and dependency-light. Dixon-Coles is exposed as
an alternative forecast until chronological backtests justify promotion.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Iterable, Mapping


def recency_weighted_mean(values: Iterable[float], *, decay: float = 0.85) -> float:
    """Weighted mean of oldest-to-newest observations; newest receives weight 1."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in (0, 1]")
    items = [float(value) for value in values]
    if not items:
        raise ValueError("at least one observation is required")
    if any(not math.isfinite(value) for value in items):
        raise ValueError("observations must be finite")
    weights = [decay ** (len(items) - 1 - i) for i in range(len(items))]
    return sum(v * w for v, w in zip(items, weights)) / sum(weights)


def dixon_coles_1x2(
    home_xg: float, away_xg: float, *, rho: float = -0.05, max_goals: int = 12
) -> dict[str, float]:
    """Compute 1X2 probabilities using independent Poisson scores plus DC low-score correction.

    rho is deliberately explicit. Its default is a conservative research starting
    value, not a fitted parameter; tune it on training data only before promotion.
    """
    home_xg, away_xg, rho = float(home_xg), float(away_xg), float(rho)
    if not math.isfinite(home_xg) or home_xg < 0:
        raise ValueError("home_xg must be finite and non-negative")
    if not math.isfinite(away_xg) or away_xg < 0:
        raise ValueError("away_xg must be finite and non-negative")
    if not math.isfinite(rho) or not -0.25 <= rho <= 0.25:
        raise ValueError("rho must be finite and between -0.25 and 0.25")
    if isinstance(max_goals, bool) or not isinstance(max_goals, int) or not 1 <= max_goals <= 30:
        raise ValueError("max_goals must be an integer between 1 and 30")

    def pmf(lam: float) -> list[float]:
        values = [math.exp(-lam)]
        for goals in range(1, max_goals + 1):
            values.append(values[-1] * lam / goals)
        total = sum(values)
        return [v / total for v in values]

    home, away = pmf(home_xg), pmf(away_xg)
    result = {"H": 0.0, "D": 0.0, "A": 0.0}
    for hg, hp in enumerate(home):
        for ag, ap in enumerate(away):
            tau = 1.0
            if hg == 0 and ag == 0:
                tau = 1.0 - home_xg * away_xg * rho
            elif hg == 0 and ag == 1:
                tau = 1.0 + home_xg * rho
            elif hg == 1 and ag == 0:
                tau = 1.0 + away_xg * rho
            elif hg == 1 and ag == 1:
                tau = 1.0 - rho
            if tau < 0:
                raise ValueError("rho and expected goals produce a negative Dixon-Coles score probability")
            probability = hp * ap * tau
            result["H" if hg > ag else "A" if hg < ag else "D"] += probability
    total = sum(result.values())
    if total <= 0 or not math.isfinite(total):
        raise ValueError("Dixon-Coles probabilities could not be normalized")
    return {key: value / total for key, value in result.items()}


def rest_congestion_context(
    matches: Iterable[Mapping[str, Any]],
    home_key: str,
    away_key: str,
    target_date: date,
    *,
    window_days: int = 14,
) -> dict[str, dict[str, int | None]]:
    """Describe rest and recent fixture congestion from past match dates only.

    This is context for reviewers, not a probability adjustment: the data source
    has dates but no verified lineup/injury or match-minute information.
    """
    if isinstance(window_days, bool) or not isinstance(window_days, int) or window_days < 1:
        raise ValueError("window_days must be a positive integer")
    rows = list(matches)
    cutoff = target_date - timedelta(days=window_days)
    result: dict[str, dict[str, int | None]] = {}
    for side, key in (("home", home_key), ("away", away_key)):
        previous = [
            row for row in rows
            if isinstance(row.get("date"), date)
            and row["date"] < target_date
            and key in (row.get("home_key"), row.get("away_key"))
        ]
        last_date = max((row["date"] for row in previous), default=None)
        recent_count = sum(cutoff <= row["date"] < target_date for row in previous)
        result[side] = {
            "days_since_last_match": (target_date - last_date).days if last_date else None,
            "matches_in_previous_14_days": recent_count,
        }
    return result


def blend_1x2(
    models: Mapping[str, Mapping[str, float]], weights: Mapping[str, float]
) -> dict[str, float]:
    """Blend already-calibrated 1X2 models; callers must validate weights out of sample."""
    if not models or set(models) != set(weights):
        raise ValueError("model and weight names must match and be non-empty")
    if any(not math.isfinite(float(w)) or float(w) < 0 for w in weights.values()):
        raise ValueError("weights must be finite and non-negative")
    if sum(float(w) for w in weights.values()) <= 0:
        raise ValueError("at least one model weight must be positive")
    combined = {key: 0.0 for key in ("H", "D", "A")}
    for name, probabilities in models.items():
        if set(probabilities) != {"H", "D", "A"}:
            raise ValueError(f"{name} must provide H, D, and A probabilities")
        vals = [float(probabilities[k]) for k in ("H", "D", "A")]
        if any(not math.isfinite(v) or v < 0 or v > 1 for v in vals) or abs(sum(vals) - 1.0) > 1e-6:
            raise ValueError(f"{name} probabilities must be valid and sum to one")
        for key in combined:
            combined[key] += float(weights[name]) * float(probabilities[key])
    total = sum(combined.values())
    return {key: value / total for key, value in combined.items()}
