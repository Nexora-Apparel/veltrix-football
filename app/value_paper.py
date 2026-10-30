"""Prospective value-market paper selection and settlement helpers.

Only timestamped, pre-kickoff snapshots are eligible. No bookmaker actions.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _valid_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and 1.01 <= price <= 100 else None


def _prob(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and 0 <= result <= 1 else None


def _devig(prices: dict[str, float]) -> dict[str, float] | None:
    implied = {key: 1 / price for key, price in prices.items()}
    total = sum(implied.values())
    if len(implied) < 2 or total <= 0 or not math.isfinite(total):
        return None
    return {key: value / total for key, value in implied.items()}


def prospective_value_rows(prediction: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Select one highest-edge outcome per market using complete same-book odds."""
    snapshot = prediction.get("the_odds_api_market_odds")
    if not isinstance(snapshot, dict):
        return []
    kickoff = _ts(prediction.get("kickoff_local") or prediction.get("kickoff"))
    fetched = _ts(snapshot.get("fetched_at"))
    commence = _ts(snapshot.get("commence_time"))
    if not kickoff or not fetched or not commence or fetched >= kickoff or commence != kickoff:
        return []
    if (kickoff - fetched).total_seconds() > 24 * 3600:
        return []
    markets = snapshot.get("markets")
    if not isinstance(markets, dict):
        return []

    home_goals, away_goals = result["home_goals"], result["away_goals"]
    home, away = str(prediction.get("home_team") or ""), str(prediction.get("away_team") or "")
    if not home or not away:
        return []
    definitions = [
        ("h2h", "1x2", {"home": home, "draw": "Draw", "away": away},
         {"home": prediction.get("market_probabilities", {}).get("H") if isinstance(prediction.get("market_probabilities"), dict) else None,
          "draw": prediction.get("market_probabilities", {}).get("D") if isinstance(prediction.get("market_probabilities"), dict) else None,
          "away": prediction.get("market_probabilities", {}).get("A") if isinstance(prediction.get("market_probabilities"), dict) else None},
         "home" if home_goals > away_goals else "away" if home_goals < away_goals else "draw", None),
        ("btts", "btts", {"yes": "Yes", "no": "No"},
         {"yes": prediction.get("btts_yes"), "no": (1 - _prob(prediction.get("btts_yes"))) if _prob(prediction.get("btts_yes")) is not None else None},
         "yes" if home_goals > 0 and away_goals > 0 else "no", None),
    ]
    for line in (1.5, 2.5, 3.5):
        key = str(line).replace(".", "_")
        over_key = f"over_{key}"
        p_over = _prob(prediction.get(over_key))
        definitions.append(("totals", over_key, {"over": "Over", "under": "Under"},
            {"over": p_over, "under": 1 - p_over if p_over is not None else None},
            "over" if home_goals + away_goals > line else "under", line))

    rows: list[dict[str, Any]] = []
    for provider_market, market_name, labels, model_probs, actual, line in definitions:
        books = markets.get(provider_market)
        if not isinstance(books, list):
            continue
        book_candidates = []
        for book in books:
            if not isinstance(book, dict):
                continue
            quote_time = _ts(book.get("last_update"))
            if not quote_time or quote_time > fetched or quote_time > kickoff or (kickoff - quote_time).total_seconds() > 24 * 3600:
                continue
            prices: dict[str, float] = {}
            for quote in book.get("outcomes") or []:
                if not isinstance(quote, dict):
                    continue
                name = str(quote.get("name") or "")
                selection = next((k for k, label in labels.items() if name.casefold() == label.casefold()), None)
                if selection is None:
                    continue
                if line is not None:
                    try:
                        if abs(float(quote.get("point")) - line) > 1e-9:
                            continue
                    except (TypeError, ValueError):
                        continue
                price = _valid_price(quote.get("price"))
                if price is not None:
                    prices[selection] = max(price, prices.get(selection, 0))
            if set(prices) != set(labels):
                continue
            market_probs = _devig(prices)
            if not market_probs:
                continue
            book_candidates.append((book, quote_time, prices, market_probs))
        if not book_candidates:
            continue
        # Compare model probabilities with a complete, same-book de-vigged market.
        viable = []
        for book, quote_time, prices, market_probs in book_candidates:
            for selection in labels:
                model_p = _prob(model_probs.get(selection))
                if model_p is None:
                    continue
                edge = model_p - market_probs[selection]
                viable.append((edge, prices[selection], selection, model_p, market_probs[selection], book, quote_time))
        if not viable:
            continue
        edge, price, selection, model_p, market_p, book, quote_time = max(viable, key=lambda x: (x[0], x[1]))
        won = selection == actual
        rows.append({
            "fixture_id": prediction.get("fixture_id"),
            "home_team": home, "away_team": away,
            "market": market_name, "selection": selection,
            "model_probability": model_p, "devigged_market_probability": market_p,
            "decimal_odds": price, "implied_probability": 1 / price, "edge": edge,
            "bookmaker": str(book.get("bookmaker") or "Unknown"),
            "odds_provider": "The Odds API",
            "odds_fetched_at": fetched.isoformat(), "quote_updated_at": quote_time.isoformat(),
            "kickoff": kickoff.isoformat(), "actual_outcome": bool(won),
            "unit_stake": 1.0, "unit_profit": round(price - 1, 6) if won else -1.0,
            "settlement": "WON" if won else "LOST",
            "model": str(prediction.get("goal_markets_model") or prediction.get("model") or "unknown"),
        })
    return rows


def summarize_value_market_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-market settled ROI plus a conservative normal-approximation lower bound."""
    output: dict[str, Any] = {}
    for market in sorted({str(row.get("market")) for row in rows}):
        subset = [row for row in rows if row.get("market") == market]
        returns = [float(row.get("unit_profit", 0)) for row in subset]
        n = len(returns)
        stake = sum(float(row.get("unit_stake", 1)) for row in subset)
        net = sum(returns)
        roi = net / stake if stake else None
        # One-sided 95% normal lower bound on mean unit return, scaled by stake.
        if n > 1 and stake:
            mean = sum(returns) / n
            variance = sum((x - mean) ** 2 for x in returns) / (n - 1)
            lower = (mean - 1.645 * math.sqrt(variance / n)) * n / stake
        else:
            lower = None
        dates = {str(row.get("kickoff", ""))[:10] for row in subset if row.get("kickoff")}
        timestamped = sum(bool(_ts(row.get("quote_updated_at")) and _ts(row.get("odds_fetched_at"))) for row in subset)
        output[market] = {
            "settled_bets": n, "distinct_match_dates": len(dates),
            "wins": sum(bool(row.get("actual_outcome")) for row in subset),
            "net_units": net, "paper_roi": roi,
            "roi_lower_95_normal_approx": lower,
            "timestamped_odds_coverage": timestamped / n if n else 0.0,
            "notice": "Prospective paper-only estimate; normal-approximation lower bound is diagnostic, not a release-grade confidence interval."
        }
    return output
