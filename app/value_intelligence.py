"""Shadow-mode market intelligence for VELTRIX value research.

This module deliberately does not publish picks or unlock betting. It adds
market-consensus de-vigging, conservative model/market shrinkage, uncertainty
haircuts, and closing-line-value diagnostics as auditable research outputs.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import mean, pstdev
from typing import Any


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def devig(odds: Mapping[str, Any]) -> dict[str, float]:
    """Proportional de-vig for one complete bookmaker outcome set."""
    prices = {str(k): _number(v) for k, v in odds.items()}
    if len(prices) < 2 or any(v is None or v <= 1 for v in prices.values()):
        raise ValueError("A complete set of at least two valid decimal prices is required")
    implied = {k: 1.0 / float(v) for k, v in prices.items()}
    total = sum(implied.values())
    if total <= 0 or not math.isfinite(total):
        raise ValueError("Invalid bookmaker overround")
    return {k: v / total for k, v in implied.items()}


def market_consensus(bookmaker_sets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Median de-vigged probability across complete books, with dispersion."""
    rows: dict[str, list[float]] = {}
    rejected = 0
    for book in bookmaker_sets:
        try:
            probs = devig(book)
        except (TypeError, ValueError):
            rejected += 1
            continue
        for outcome, probability in probs.items():
            rows.setdefault(outcome, []).append(probability)
    if not rows or len({len(v) for v in rows.values()}) != 1:
        return {"status": "INSUFFICIENT_COMPLETE_BOOKS", "bookmaker_count": 0,
                "rejected_bookmaker_sets": rejected, "probabilities": {},
                "dispersion": {}}
    consensus = {k: float(sorted(v)[len(v) // 2]) if len(v) % 2 else mean(sorted(v)[len(v)//2-1:len(v)//2+1])
                 for k, v in rows.items()}
    total = sum(consensus.values())
    if total <= 0:
        raise ValueError("Consensus probabilities cannot be normalized")
    consensus = {k: v / total for k, v in consensus.items()}
    dispersion = {k: pstdev(v) if len(v) > 1 else 0.0 for k, v in rows.items()}
    count = min(len(v) for v in rows.values())
    return {"status": "CONSENSUS_READY" if count >= 2 else "SINGLE_BOOK_ONLY",
            "bookmaker_count": count, "rejected_bookmaker_sets": rejected,
            "probabilities": consensus, "dispersion": dispersion}


def shrink_to_market(
    model_probabilities: Mapping[str, Any],
    consensus: Mapping[str, Any],
    *,
    model_weight: float = 0.35,
    uncertainty_z: float = 1.645,
) -> dict[str, Any]:
    """Shrink estimates toward market and compute a conservative lower bound.

    model_weight is intentionally conservative by default. Dispersion is used
    as a transparent uncertainty penalty, not represented as a formal CI.
    """
    if not 0 <= model_weight <= 1 or uncertainty_z < 0:
        raise ValueError("Invalid shrinkage parameters")
    market = consensus.get("probabilities") or {}
    dispersion = consensus.get("dispersion") or {}
    combined: dict[str, float] = {}
    lower: dict[str, float] = {}
    raw_edge: dict[str, float] = {}
    for key, raw in model_probabilities.items():
        p, m = _number(raw), _number(market.get(key))
        if p is None or m is None or not 0 <= p <= 1 or not 0 <= m <= 1:
            continue
        estimate = model_weight * p + (1.0 - model_weight) * m
        sigma = max(0.0, _number(dispersion.get(key)) or 0.0)
        combined[key] = estimate
        lower[key] = max(0.0, estimate - uncertainty_z * sigma)
        raw_edge[key] = p - m
    return {"method": "MARKET_SHRUNK_MODEL_V1", "model_weight": model_weight,
            "probabilities": combined, "conservative_lower_bound": lower,
            "raw_model_edge": raw_edge,
            "note": "Dispersion haircut is a screening heuristic, not a calibrated confidence interval."}


def evaluate_price(
    probability: float,
    decimal_odds: float,
    *,
    minimum_edge: float = 0.04,
    minimum_ev: float = 0.05,
) -> dict[str, Any]:
    """Evaluate a single price against the conservative probability estimate."""
    p, odds = _number(probability), _number(decimal_odds)
    if p is None or odds is None or not 0 <= p <= 1 or odds <= 1:
        return {"status": "REJECT_INVALID_INPUT"}
    ev = p * odds - 1.0
    implied = 1.0 / odds
    edge = p - implied
    passed = edge >= minimum_edge and ev >= minimum_ev
    return {"status": "SHADOW_CANDIDATE" if passed else "REJECTED",
            "probability_used": p, "decimal_odds": odds,
            "implied_probability": implied, "edge": edge,
            "expected_value_per_unit": ev,
            "release_status": "LOCKED_SHADOW_MODE"}


def closing_line_value(opening_odds: float, closing_odds: float) -> dict[str, Any]:
    """Positive CLV means the taken price was better than the closing price."""
    opening, closing = _number(opening_odds), _number(closing_odds)
    if opening is None or closing is None or opening <= 1 or closing <= 1:
        return {"status": "INVALID_ODDS"}
    opening_prob, closing_prob = 1.0 / opening, 1.0 / closing
    return {"status": "MEASURED",
            "opening_odds": opening, "closing_odds": closing,
            "clv_probability_points": (closing_prob - opening_prob) * 100.0,
            "price_improvement_percent": (opening / closing - 1.0) * 100.0}


def poisson_scoreline_markets(home_lambda: float, away_lambda: float,
                              *, max_goals: int = 10) -> dict[str, float]:
    """Independent-Poisson scoreline simulation for 1X2, BTTS and goal totals."""
    lh, la = _number(home_lambda), _number(away_lambda)
    if lh is None or la is None or lh < 0 or la < 0 or not 1 <= max_goals <= 20:
        raise ValueError("Invalid expected-goal inputs")
    def pmf(lam: float) -> list[float]:
        values = [math.exp(-lam)]
        for k in range(1, max_goals + 1):
            values.append(values[-1] * lam / k)
        return values
    hp, ap = pmf(lh), pmf(la)
    matrix = [(i, j, ph * pa) for i, ph in enumerate(hp) for j, pa in enumerate(ap)]
    mass = sum(x[2] for x in matrix)
    if mass <= 0:
        raise ValueError("Scoreline probability mass is zero")
    home = sum(p for h, a, p in matrix if h > a) / mass
    draw = sum(p for h, a, p in matrix if h == a) / mass
    away = sum(p for h, a, p in matrix if h < a) / mass
    btts = sum(p for h, a, p in matrix if h > 0 and a > 0) / mass
    result = {"home_win": home, "draw": draw, "away_win": away,
              "btts_yes": btts}
    for line in (1.5, 2.5, 3.5):
        over = sum(p for h, a, p in matrix if h + a > line) / mass
        result[f"over_{str(line).replace('.', '_')}"] = over
    return result
