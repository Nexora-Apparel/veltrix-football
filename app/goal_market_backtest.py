"""Chronological backtest for BTTS and goal totals.

This research baseline uses only results dated before each forecast date. It is
not a betting recommendation and must not be promoted without out-of-sample
validation. It compares a shrunk, recency-weighted team-goal model against
historical-rate baselines on the exact same evaluated fixtures.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from app.backtest_engine import load_matches
from app.live_predictions import _name_key
from app.prediction import match_probabilities

MARKETS = {
    "btts_yes": lambda hg, ag: int(hg > 0 and ag > 0),
    "btts_no": lambda hg, ag: int(not (hg > 0 and ag > 0)),
    "over_1_5": lambda hg, ag: int(hg + ag >= 2),
    "under_1_5": lambda hg, ag: int(hg + ag < 2),
    "over_2_5": lambda hg, ag: int(hg + ag >= 3),
    "under_2_5": lambda hg, ag: int(hg + ag < 3),
    "over_3_5": lambda hg, ag: int(hg + ag >= 4),
    "under_3_5": lambda hg, ag: int(hg + ag < 4),
}


def _weighted_shrunk_rate(
    observations: list[float], prior: float, *, decay: float = 0.85, prior_strength: float = 4.0
) -> float:
    """Recency-weight observations and shrink small samples toward a league prior."""
    if not observations:
        return prior
    weights = [decay ** (len(observations) - 1 - i) for i in range(len(observations))]
    weight_sum = sum(weights)
    recent_mean = sum(value * weight for value, weight in zip(observations, weights)) / weight_sum
    return (recent_mean * weight_sum + prior * prior_strength) / (weight_sum + prior_strength)


def _market_metrics(rows: list[dict[str, Any]], market: str, probability_key: str) -> dict[str, Any]:
    if not rows:
        return {"matches": 0, "accuracy": None, "brier_score": None, "log_loss": None, "observed_rate": None}
    actuals = [int(row["actual"][market]) for row in rows]
    probs = [min(1.0 - 1e-12, max(1e-12, float(row[probability_key][market]))) for row in rows]
    brier = sum((p - y) ** 2 for p, y in zip(probs, actuals)) / len(rows)
    log_loss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(probs, actuals)) / len(rows)
    accuracy = sum(int((p >= 0.5) == bool(y)) for p, y in zip(probs, actuals)) / len(rows)
    return {
        "matches": len(rows),
        "accuracy": accuracy,
        "brier_score": brier,
        "log_loss": log_loss,
        "observed_rate": sum(actuals) / len(actuals),
    }


def chronological_goal_market_backtest(
    matches: list[dict[str, Any]], *, min_training_matches: int = 1000, team_window: int = 10
) -> dict[str, Any]:
    """Evaluate goal markets chronologically; same-day scores never enter forecasts."""
    if min_training_matches < 1:
        raise ValueError("min_training_matches must be positive")
    if team_window < 1:
        raise ValueError("team_window must be positive")

    ordered = sorted(matches, key=lambda row: (row["match_date"], row["division"], row["home_team"], row["away_team"]))
    history: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=team_window))
    league_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    global_history: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    training_count = 0
    index = 0

    while index < len(ordered):
        day = ordered[index]["match_date"]
        day_matches = []
        while index < len(ordered) and ordered[index]["match_date"] == day:
            day_matches.append(ordered[index])
            index += 1

        # Forecast every match on a date before ingesting any results from that date.
        if training_count >= min_training_matches:
            for match in day_matches:
                division = str(match["division"])
                league_rows = league_history[division]
                baseline_rows = league_rows if len(league_rows) >= 30 else global_history
                if not baseline_rows:
                    continue

                def mean_goal(rows: list[dict[str, Any]], key: str) -> float:
                    return sum(float(row[key]) for row in rows) / len(rows)

                league_home = mean_goal(league_rows, "home_goals") if league_rows else mean_goal(global_history, "home_goals")
                league_away = mean_goal(league_rows, "away_goals") if league_rows else mean_goal(global_history, "away_goals")
                league_home = max(0.15, league_home)
                league_away = max(0.15, league_away)

                home_key = (division, _name_key(match["home_team"]))
                away_key = (division, _name_key(match["away_team"]))
                home_rows = list(history[home_key])
                away_rows = list(history[away_key])
                home_attack = _weighted_shrunk_rate(
                    [float(r["home_goals"]) for r in home_rows if r["venue"] == "home"], league_home
                )
                home_defence = _weighted_shrunk_rate(
                    [float(r["away_goals"]) for r in home_rows if r["venue"] == "home"], league_away
                )
                away_attack = _weighted_shrunk_rate(
                    [float(r["away_goals"]) for r in away_rows if r["venue"] == "away"], league_away
                )
                away_defence = _weighted_shrunk_rate(
                    [float(r["home_goals"]) for r in away_rows if r["venue"] == "away"], league_home
                )

                home_lambda = min(4.5, max(0.15, home_attack * away_defence / league_home))
                away_lambda = min(4.5, max(0.15, away_attack * home_defence / league_away))
                model_result = match_probabilities(home_lambda, away_lambda)
                model_probs = {
                    "btts_yes": float(model_result["btts_yes"]),
                    "btts_no": float(model_result["btts_no"]),
                    "over_1_5": float(model_result["totals"]["over_1_5"]),
                    "under_1_5": float(model_result["totals"]["under_1_5"]),
                    "over_2_5": float(model_result["totals"]["over_2_5"]),
                    "under_2_5": float(model_result["totals"]["under_2_5"]),
                    "over_3_5": float(model_result["totals"]["over_3_5"]),
                    "under_3_5": float(model_result["totals"]["under_3_5"]),
                }

                base_probs = {}
                for market, event in MARKETS.items():
                    base_probs[market] = sum(event(int(r["home_goals"]), int(r["away_goals"])) for r in baseline_rows) / len(baseline_rows)
                actual = {market: event(int(match["home_goals"]), int(match["away_goals"])) for market, event in MARKETS.items()}
                predictions.append({
                    "match_date": day,
                    "division": division,
                    "home_team": match["home_team"],
                    "away_team": match["away_team"],
                    "actual": actual,
                    "model": model_probs,
                    "baseline": base_probs,
                    "home_xg": home_lambda,
                    "away_xg": away_lambda,
                    "training_matches_before_date": training_count,
                })

        # Only after all forecasts for the day are formed do results update state.
        for match in day_matches:
            division = str(match["division"])
            home_key = (division, _name_key(match["home_team"]))
            away_key = (division, _name_key(match["away_team"]))
            history[home_key].append({
                "venue": "home",
                "home_goals": int(match["home_goals"]),
                "away_goals": int(match["away_goals"]),
            })
            history[away_key].append({
                "venue": "away",
                "home_goals": int(match["home_goals"]),
                "away_goals": int(match["away_goals"]),
            })
            league_history[division].append(match)
            global_history.append(match)
            training_count += 1

    metrics = {}
    for market in MARKETS:
        metrics[market] = {
            "model": _market_metrics(predictions, market, "model"),
            "historical_rate_baseline": _market_metrics(predictions, market, "baseline"),
        }
    return {
        "status": "RESEARCH_BACKTEST_NOT_PROOF_OF_PROFIT",
        "method": "recency_weighted_venue_split_goal_rates_with_shrinkage",
        "min_training_matches": min_training_matches,
        "team_window": team_window,
        "test_matches": len(predictions),
        "first_test_date": predictions[0]["match_date"] if predictions else None,
        "last_test_date": predictions[-1]["match_date"] if predictions else None,
        "markets": metrics,
        "predictions": predictions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Chronological BTTS and Over/Under backtest")
    parser.add_argument("--input", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/goal_market_backtest.json")
    parser.add_argument("--min-training-matches", type=int, default=1000)
    parser.add_argument("--team-window", type=int, default=10)
    args = parser.parse_args()
    matches = load_matches(args.input)
    report = chronological_goal_market_backtest(
        matches, min_training_matches=args.min_training_matches, team_window=args.team_window
    )
    report["dataset"] = {
        "input_file": Path(args.input).name,
        "rows_loaded": len(matches),
        "first_match_date": min(row["match_date"] for row in matches),
        "last_match_date": max(row["match_date"] for row in matches),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "predictions"}
    print(json.dumps(summary, indent=2))
    print(f"Report saved: {args.output}")


if __name__ == "__main__":
    main()
