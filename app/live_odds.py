"""Parse de-vigged 1X2 market consensus from API-Football odds snapshots."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


_ALLOWED_BET_NAMES = {
    "match winner",
    "1x2",
    "match result",
    "full time result",
    "full-time result",
}


def _parse_odds(values: Any) -> dict[str, float] | None:
    if not isinstance(values, list):
        return None
    result: dict[str, float] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        label = str(item.get("value", "")).strip().casefold()
        if label in {"home", "1"}:
            key = "home_win"
        elif label in {"draw", "x"}:
            key = "draw"
        elif label in {"away", "2"}:
            key = "away_win"
        else:
            continue
        try:
            odd = float(item.get("odd"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(odd) and odd > 1.0:
            result[key] = odd
    if set(result) != {"home_win", "draw", "away_win"}:
        return None
    return result


def _devig(odds: dict[str, float]) -> dict[str, float]:
    implied = {key: 1.0 / value for key, value in odds.items()}
    total = sum(implied.values())
    return {key: value / total for key, value in implied.items()}


def extract_market_probabilities(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Return equal-weight mean de-vigged 1X2 probabilities per fixture.

    Only full-time 1X2-style markets are accepted. Incomplete bookmaker markets
    and other bet types are ignored; no raw odds are treated as probabilities.
    """
    response = payload.get("response")
    if not isinstance(response, list):
        raise ValueError("Odds payload must contain a response list.")

    probabilities_by_fixture: dict[int, list[dict[str, float]]] = defaultdict(list)
    updates_by_fixture: dict[int, list[str]] = defaultdict(list)
    for item in response:
        fixture_id = (item.get("fixture") or {}).get("id")
        if not isinstance(fixture_id, int) or isinstance(fixture_id, bool):
            continue
        update = str(item.get("update") or "").strip()
        bookmakers = item.get("bookmakers")
        if not isinstance(bookmakers, list):
            continue
        for bookmaker in bookmakers:
            bets = bookmaker.get("bets") if isinstance(bookmaker, dict) else None
            if not isinstance(bets, list):
                continue
            for bet in bets:
                if not isinstance(bet, dict):
                    continue
                name = str(bet.get("name") or "").strip().casefold()
                if name not in _ALLOWED_BET_NAMES:
                    continue
                odds = _parse_odds(bet.get("values"))
                if odds is None:
                    continue
                probabilities_by_fixture[fixture_id].append(_devig(odds))
                if update:
                    updates_by_fixture[fixture_id].append(update)
                break

    result: dict[int, dict[str, Any]] = {}
    for fixture_id, bookmaker_probabilities in probabilities_by_fixture.items():
        count = len(bookmaker_probabilities)
        consensus = {
            outcome: sum(row[outcome] for row in bookmaker_probabilities) / count
            for outcome in ("home_win", "draw", "away_win")
        }
        total = sum(consensus.values())
        consensus = {key: value / total for key, value in consensus.items()}
        updates = updates_by_fixture.get(fixture_id, [])
        result[fixture_id] = {
            "model": "market_consensus",
            "probabilities": consensus,
            "bookmakers_count": count,
            "updated_at": max(updates) if updates else None,
            "method": "equal-weight mean of bookmaker-specific de-vigged 1X2 probabilities",
        }
    return result
