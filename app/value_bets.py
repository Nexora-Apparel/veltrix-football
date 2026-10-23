"""Conservative value-bet screening primitives.

This module does not claim that a model is accurate. It screens supplied
probabilities against available decimal odds and defaults to no bet when data
are missing or invalid. Production alerts should only be enabled after
chronological backtesting and probability calibration.
"""
from __future__ import annotations

import math
from typing import Mapping, Any


def _valid_probability(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and 0.0 <= number <= 1.0


def _valid_odds(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 1.0


def devig_probabilities(odds: Mapping[str, float]) -> dict[str, float]:
    """Normalize reciprocal odds to remove the proportional bookmaker margin."""
    if len(odds) < 2 or not all(_valid_odds(v) for v in odds.values()):
        raise ValueError("At least two valid decimal odds greater than 1 are required")
    raw = {key: 1.0 / float(value) for key, value in odds.items()}
    total = sum(raw.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Odds do not produce a valid market probability")
    return {key: value / total for key, value in raw.items()}


def screen_value_bets(
    model_probabilities: Mapping[str, float],
    decimal_odds: Mapping[str, float],
    *,
    min_edge: float = 0.04,
    min_expected_return: float = 0.05,
    min_model_probability: float = 0.45,
    min_odds: float = 1.50,
    max_odds: float = 4.00,
    model_validated: bool = False,
) -> list[dict[str, Any]]:
    """Return candidates passing strict thresholds; otherwise return no bets.

    Edge is model probability minus de-vigged market probability. Expected
    return is p*odds-1 per unit staked, before any limits, slippage or fees.
    Candidates are deliberately suppressed unless the caller explicitly
    confirms that the model has passed out-of-sample validation.
    """
    thresholds = (min_edge, min_expected_return, min_model_probability)
    if any(not math.isfinite(float(x)) for x in thresholds):
        raise ValueError("Thresholds must be finite")
    if min_edge < 0 or min_expected_return < 0 or not 0 <= min_model_probability <= 1:
        raise ValueError("Invalid probability/return thresholds")
    if min_odds <= 1 or max_odds < min_odds:
        raise ValueError("Invalid odds range")
    if not model_validated:
        return []

    keys = set(model_probabilities) & set(decimal_odds)
    if len(keys) < 2:
        return []
    valid = {
        key: float(decimal_odds[key])
        for key in keys
        if _valid_probability(model_probabilities[key]) and _valid_odds(decimal_odds[key])
    }
    if len(valid) < 2:
        return []
    market_probs = devig_probabilities(valid)
    candidates: list[dict[str, Any]] = []
    for key, odds in valid.items():
        probability = float(model_probabilities[key])
        edge = probability - market_probs[key]
        expected_return = probability * odds - 1.0
        if (
            min_odds <= odds <= max_odds
            and probability >= min_model_probability
            and edge >= min_edge
            and expected_return >= min_expected_return
        ):
            candidates.append({
                "selection": key,
                "model_probability": probability,
                "devigged_market_probability": market_probs[key],
                "edge": edge,
                "edge_percentage_points": edge * 100.0,
                "decimal_odds": odds,
                "expected_return_per_unit": expected_return,
                "status": "CANDIDATE_NOT_GUARANTEED",
            })
    return sorted(candidates, key=lambda row: (row["expected_return_per_unit"], row["edge"]), reverse=True)
