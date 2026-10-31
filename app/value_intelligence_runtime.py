"""Attach auditable shadow value-intelligence diagnostics to daily forecasts.

Reads only timestamp-eligible The Odds API snapshots already attached to each
fixture. It does not make provider requests, alter base forecasts, create alerts,
or change the existing certificate-gated value screen.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.value_intelligence import (market_consensus, shrink_to_market, evaluate_price,\n    poisson_scoreline_markets, ensemble_probabilities, bayesian_market_update, opportunity_quality_score)
from app.value_bets_runtime import _eligible_snapshot, _eligible_quote, _map_outcomes


MARKETS = {
    "1X2": ("h2h", {"home_win", "draw", "away_win"}),
    "BTTS": ("btts", {"yes", "no"}),
    "OVER_UNDER_1_5": ("totals", {"over", "under"}),
    "OVER_UNDER_2_5": ("totals", {"over", "under"}),
    "OVER_UNDER_3_5": ("totals", {"over", "under"}),
}


def _model_market_probabilities(prediction: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    model = str(prediction.get("model") or "")
    raw = prediction.get("poisson_probabilities") if model == "experimental_elo_by_competition" else prediction.get("probabilities") if model == "experimental_recent_goals_poisson" else None
    raw = raw if isinstance(raw, Mapping) else {}
    result: dict[str, dict[str, float]] = {}
    one_x_two = {
        "home_win": raw.get("home_win", raw.get("H")),
        "draw": raw.get("draw", raw.get("D")),
        "away_win": raw.get("away_win", raw.get("A")),
    }
    if all(_valid_probability(v) for v in one_x_two.values()):
        result["1X2"] = {k: float(v) for k, v in one_x_two.items()}
    btts = prediction.get("btts_yes")
    if _valid_probability(btts):
        result["BTTS"] = {"yes": float(btts), "no": 1.0 - float(btts)}
    for line in (1.5, 2.5, 3.5):
        suffix = str(line).replace(".", "_")
        value = prediction.get(f"over_{suffix}")
        if _valid_probability(value):
            result[f"OVER_UNDER_{suffix}"] = {"over": float(value), "under": 1.0 - float(value)}
    return result


def _valid_probability(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return 0.0 <= number <= 1.0


def screen_fixture_value_intelligence(prediction: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = prediction.get("the_odds_api_market_odds")
    if not _eligible_snapshot(snapshot, prediction):
        return {
            "status": "NO_ELIGIBLE_TIMESTAMPED_ODDS",
            "markets": {},
            "release_status": "LOCKED_SHADOW_MODE",
        }
    odds_markets = snapshot.get("markets") if isinstance(snapshot.get("markets"), Mapping) else {}
    home = str(prediction.get("home_team") or "")
    away = str(prediction.get("away_team") or "")
    model_markets = _model_market_probabilities(prediction)
    output: dict[str, Any] = {}
    for market, (provider_market, required) in MARKETS.items():
        if market not in model_markets:
            output[market] = {"status": "NO_ELIGIBLE_MODEL_PROBABILITY"}
            continue
        bookmaker_sets: list[dict[str, Any]] = []
        price_rows: list[dict[str, Any]] = []
        for book in odds_markets.get(provider_market) or []:
            if not isinstance(book, Mapping) or not _eligible_quote(book, snapshot, prediction):
                continue
            mapped = _map_outcomes(book.get("outcomes"), home, away, market)
            if not required.issubset(mapped):
                continue
            clean = {key: float(mapped[key]) for key in required}
            bookmaker_sets.append(clean)
            price_rows.append({
                "bookmaker": str(book.get("bookmaker") or "UNKNOWN"),
                "last_update": book.get("last_update"),
                "odds": clean,
            })
        consensus = market_consensus(bookmaker_sets)
        if consensus.get("status") not in {"CONSENSUS_READY", "SINGLE_BOOK_ONLY"}:
            output[market] = {
                "status": consensus.get("status"),
                "bookmaker_count": 0,
                "release_status": "LOCKED_SHADOW_MODE",
            }
            continue
        bayesian = bayesian_market_update(model_markets[market], consensus.get("probabilities", {}), model_prior_weight=0.35)\n        blended = shrink_to_market(bayesian.get("probabilities") if bayesian.get("status") == "UPDATED" else model_markets[market], consensus, model_weight=0.35)
        candidates = []
        for row in price_rows:
            for outcome, price in row["odds"].items():
                conservative_p = blended["conservative_lower_bound"].get(outcome)
                if conservative_p is None:
                    continue
                evaluated = evaluate_price(conservative_p, price)
                if evaluated.get("status") == "SHADOW_CANDIDATE":
                    candidates.append({
                        "selection": outcome,
                        "bookmaker": row["bookmaker"],
                        "last_update": row["last_update"],
                        **evaluated,
                    })
        candidates.sort(key=lambda x: x["expected_value_per_unit"], reverse=True)
        output[market] = {
            "status": "SHADOW_CANDIDATES_FOUND" if candidates else "NO_QUALIFYING_SHADOW_PRICE",
            "bookmaker_count": consensus.get("bookmaker_count", 0),
            "market_consensus_probabilities": consensus.get("probabilities", {}),
            "bookmaker_probability_dispersion": consensus.get("dispersion", {}),
            "model_probabilities": model_markets[market],
            "market_shrunk_probabilities": blended.get("probabilities", {}),
            "conservative_screening_probabilities": blended.get("conservative_lower_bound", {}),
            "raw_model_edge": blended.get("raw_model_edge", {}),
            "candidates": candidates[:5],
            "quote_timestamps": [row["last_update"] for row in price_rows],
            "bookmaker_quotes": price_rows,
            "method": blended.get("method"),\n            "bayesian_update": bayesian,\n            "model_ensemble_source": "model_probability_sets" if isinstance(prediction.get("model_probability_sets"), Mapping) else "single_model_or_scoreline",
            "uncertainty_note": blended.get("note"),
            "release_status": "LOCKED_SHADOW_MODE",
        }
    return {
        "status": "EVALUATED" if output else "NO_ELIGIBLE_MARKETS",
        "source": "The Odds API",
        "snapshot_fetched_at": snapshot.get("fetched_at"),
        "markets": output,
        "release_status": "LOCKED_SHADOW_MODE",
        "note": "Research diagnostics only. No forecast probabilities are modified and no betting alerts are enabled.",
    }


def attach_value_intelligence(report: dict[str, Any]) -> dict[str, Any]:
    predictions = report.get("predictions")
    if not isinstance(predictions, list):
        predictions = []
        report["predictions"] = predictions
    counts: dict[str, int] = {key: 0 for key in MARKETS}
    evaluated = 0
    candidates = 0
    for prediction in predictions:
        if not isinstance(prediction, dict):
            continue
        diagnostics = screen_fixture_value_intelligence(prediction)
        prediction["value_intelligence"] = diagnostics
        if diagnostics.get("status") == "EVALUATED":
            evaluated += 1
        for market, details in (diagnostics.get("markets") or {}).items():
            if details.get("bookmaker_count", 0):
                counts[market] += int(details["bookmaker_count"])
            candidates += len(details.get("candidates") or [])
    report["value_intelligence"] = {
        "engine": "VELTRIX_VALUE_INTELLIGENCE_V1",
        "status": "SHADOW_MODE",
        "fixtures_evaluated": evaluated,
        "bookmaker_price_sets_by_market": counts,
        "shadow_candidate_count": candidates,
        "alerts_enabled": False,
        "release_status": "LOCKED_SHADOW_MODE",
        "note": "Market consensus, model shrinkage and quote-level screening are research-only. Existing value certificate remains authoritative.",
    }
    return report
