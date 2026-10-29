"""Diagnostic audit for market-defined favourites and underdogs.

Evaluation-only: this does not alter predictions or treat market odds as the
model target. Inputs must contain strictly pre-match, de-vigged 1X2 probabilities
and out-of-sample model forecasts.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

OUTCOMES = ("H", "D", "A")


def _valid_probs(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping) or set(value) != set(OUTCOMES):
        return None
    try:
        probs = {key: float(value[key]) for key in OUTCOMES}
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(p) or p < 0 or p > 1 for p in probs.values()):
        return None
    if abs(sum(probs.values()) - 1.0) > 1e-5:
        return None
    return probs


def _score(rows: list[tuple[dict[str, float], str]]) -> dict[str, Any]:
    if not rows:
        return {"matches": 0, "accuracy": None, "brier_score": None, "log_loss": None}
    count = len(rows)
    brier = 0.0
    log_loss = 0.0
    correct = 0
    for probabilities, actual in rows:
        brier += sum((probabilities[key] - float(actual == key)) ** 2 for key in OUTCOMES)
        log_loss += -math.log(max(1e-15, probabilities[actual]))
        correct += int(max(probabilities, key=probabilities.get) == actual)
    return {
        "matches": count,
        "accuracy": correct / count,
        "brier_score": brier / count,
        "log_loss": log_loss / count,
    }


def audit_favourites_and_underdogs(
    predictions: Iterable[Mapping[str, Any]],
    *,
    model_key: str = "model",
    market_key: str = "market",
) -> dict[str, Any]:
    """Report out-of-sample performance by pre-match market favourite/underdog.

    Each row needs actual ('H', 'D', or 'A'), model probabilities under model_key,
    and de-vigged market probabilities under market_key. Draws are included in
    overall metrics but not classified as favourite/underdog wins. Tied home and
    away market probabilities are excluded from subgroup classification.
    """
    overall: list[tuple[dict[str, float], str]] = []
    favourite_wins: list[tuple[dict[str, float], str]] = []
    underdog_wins: list[tuple[dict[str, float], str]] = []
    model_favourite_probabilities: list[float] = []
    model_underdog_probabilities: list[float] = []
    excluded = 0

    for row in predictions:
        model = _valid_probs(row.get(model_key))
        market = _valid_probs(row.get(market_key))
        actual = row.get("actual")
        if model is None or market is None or actual not in OUTCOMES:
            excluded += 1
            continue
        overall.append((model, actual))
        if abs(market["H"] - market["A"]) < 1e-9:
            continue
        favourite, underdog = ("H", "A") if market["H"] > market["A"] else ("A", "H")
        model_favourite_probabilities.append(model[favourite])
        model_underdog_probabilities.append(model[underdog])
        if actual == favourite:
            favourite_wins.append((model, actual))
        elif actual == underdog:
            underdog_wins.append((model, actual))

    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return {
        "status": "diagnostic_only",
        "classification": "market_favourite_vs_underdog",
        "overall": _score(overall),
        "favourite_wins": _score(favourite_wins),
        "underdog_wins": _score(underdog_wins),
        "matches_with_market_classification": len(model_favourite_probabilities),
        "mean_model_probability_assigned_to_market_favourite": mean(model_favourite_probabilities),
        "mean_model_probability_assigned_to_market_underdog": mean(model_underdog_probabilities),
        "excluded_invalid_rows": excluded,
        "important_note": (
            "This measures performance on market-defined favourites and underdogs; "
            "it does not directly measure club fame or prove causal popularity bias. "
            "Use chronological out-of-sample forecasts and de-vigged pre-match odds."
        ),
    }
