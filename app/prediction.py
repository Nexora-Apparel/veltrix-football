"""Transparent Poisson goal model for baseline football probabilities.

Expected-goal inputs must come from a documented source/model. This module does
not estimate team strength or fetch data; it only converts supplied lambdas
into mathematically consistent probabilities.
"""
from __future__ import annotations

import math
from typing import Any


def _validate_lambda(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite, non-negative number")
    return value


def _validate_max_goals(max_goals: int) -> int:
    if isinstance(max_goals, bool) or not isinstance(max_goals, int) or not 1 <= max_goals <= 30:
        raise ValueError("max_goals must be an integer between 1 and 30")
    return max_goals


def poisson_pmf(lam: float, max_goals: int = 12) -> list[float]:
    """Return P(X=k) for k=0..max_goals, plus omitted tail mass is not included."""
    lam = _validate_lambda(lam, "lambda")
    _validate_max_goals(max_goals)
    probabilities = [math.exp(-lam)]
    for goals in range(1, max_goals + 1):
        probabilities.append(probabilities[-1] * lam / goals)
    return probabilities


def match_probabilities(home_xg: float, away_xg: float, max_goals: int = 12) -> dict[str, Any]:
    """Calculate 1X2, BTTS, totals and scoreline probabilities from independent Poisson goals."""
    home_xg = _validate_lambda(home_xg, "home_xg")
    away_xg = _validate_lambda(away_xg, "away_xg")
    _validate_max_goals(max_goals)

    home = poisson_pmf(home_xg, max_goals)
    away = poisson_pmf(away_xg, max_goals)
    # Renormalize the truncated distributions so reported markets sum to one.
    home_total, away_total = sum(home), sum(away)
    home = [p / home_total for p in home]
    away = [p / away_total for p in away]

    home_win = draw = away_win = over_15 = over_25 = over_35 = btts = 0.0
    scorelines: list[dict[str, float | int]] = []
    for h, hp in enumerate(home):
        for a, ap in enumerate(away):
            p = hp * ap
            scorelines.append({"home_goals": h, "away_goals": a, "probability": p})
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
            if h + a >= 2:
                over_15 += p
            if h + a >= 3:
                over_25 += p
            if h + a >= 4:
                over_35 += p
            if h > 0 and a > 0:
                btts += p

    # Normalize 1X2 for tiny floating point differences.
    outcome_total = home_win + draw + away_win
    outcomes = {
        "home_win": home_win / outcome_total,
        "draw": draw / outcome_total,
        "away_win": away_win / outcome_total,
    }
    scorelines.sort(key=lambda row: float(row["probability"]), reverse=True)
    return {
        "method": "independent_poisson_baseline",
        "home_xg": home_xg,
        "away_xg": away_xg,
        "max_goals_per_team": max_goals,
        "truncated_tail_renormalized": True,
        "one_x_two": outcomes,
        "double_chance": {
            "home_or_draw": outcomes["home_win"] + outcomes["draw"],
            "draw_or_away": outcomes["draw"] + outcomes["away_win"],
            "home_or_away": outcomes["home_win"] + outcomes["away_win"],
        },
        "btts_yes": btts,
        "btts_no": 1.0 - btts,
        "totals": {
            "over_1_5": over_15,
            "under_1_5": 1.0 - over_15,
            "over_2_5": over_25,
            "under_2_5": 1.0 - over_25,
            "over_3_5": over_35,
            "under_3_5": 1.0 - over_35,
        },
        "most_likely_scorelines": scorelines[:5],
    }


def evaluate_decimal_odds(probability: float, decimal_odds: float) -> dict[str, float | bool]:
    """Compare one model probability with decimal odds; does not recommend a bet."""
    probability = float(probability)
    decimal_odds = float(decimal_odds)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    if not math.isfinite(decimal_odds) or decimal_odds <= 1.0:
        raise ValueError("decimal_odds must be finite and greater than 1.0")
    implied_probability = 1.0 / decimal_odds
    expected_return_per_unit = probability * decimal_odds - 1.0
    edge_percentage_points = (probability - implied_probability) * 100.0
    return {
        "model_probability": probability,
        "decimal_odds": decimal_odds,
        "raw_implied_probability": implied_probability,
        "edge_percentage_points": edge_percentage_points,
        "expected_return_per_unit": expected_return_per_unit,
        "positive_model_edge": edge_percentage_points > 0,
    }
