"""Chronological football model evaluation using historical full-time scores.

The backtest intentionally predicts each calendar day's matches before updating
ratings/statistics with that day's results. It compares a shrunk attack/defence
Poisson model with a simple Elo-derived 1X2 model. This is an evaluation tool,
not a claim that either model is profitable.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable


def _poisson_probs(lam: float, cap: int = 12) -> list[float]:
    if not math.isfinite(lam) or lam < 0:
        raise ValueError("Expected goals must be finite and non-negative")
    probs = [math.exp(-lam)]
    for k in range(1, cap + 1):
        probs.append(probs[-1] * lam / k)
    total = sum(probs)
    return [p / total for p in probs]


def poisson_1x2(home_lambda: float, away_lambda: float) -> dict[str, float]:
    home, away = _poisson_probs(home_lambda), _poisson_probs(away_lambda)
    h = d = a = 0.0
    for hg, hp in enumerate(home):
        for ag, ap in enumerate(away):
            p = hp * ap
            if hg > ag:
                h += p
            elif hg == ag:
                d += p
            else:
                a += p
    total = h + d + a
    return {"H": h / total, "D": d / total, "A": a / total}


def _elo_probs(home_rating: float, away_rating: float, home_advantage: float, draw_rate: float) -> dict[str, float]:
    # Standard Elo expected score converted into win/loss shares, with a
    # draw-rate prior estimated only from matches already observed.
    expected_home = 1.0 / (1.0 + 10.0 ** (-(home_rating + home_advantage - away_rating) / 400.0))
    draw = min(0.40, max(0.10, draw_rate))
    non_draw = 1.0 - draw
    return {"H": non_draw * expected_home, "D": draw, "A": non_draw * (1.0 - expected_home)}


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _normalize_match(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        day = str(row.get("match_date") or row.get("date") or "")[:10]
        division = str(row.get("division") or row.get("league") or "").strip()
        home = str(row.get("home_team") or row.get("HomeTeam") or "").strip()
        away = str(row.get("away_team") or row.get("AwayTeam") or "").strip()
        hg = int(float(row.get("home_goals", row.get("FTHome"))))
        ag = int(float(row.get("away_goals", row.get("FTAway"))))
        from datetime import date
        date.fromisoformat(day)
        if not division or not home or not away or home.casefold() == away.casefold() or min(hg, ag) < 0:
            return None
        normalized = {"match_date": day, "division": division, "home_team": home, "away_team": away,
                "home_goals": hg, "away_goals": ag, "result": "H" if hg > ag else "A" if hg < ag else "D"}
        existing_market = row.get("market")
        if isinstance(existing_market, dict) and all(_safe_float(existing_market.get(k)) is not None for k in ("H", "D", "A")):
            vals = [_safe_float(existing_market[k]) for k in ("H", "D", "A")]
            if all(v >= 0 for v in vals) and sum(vals) > 0:
                total = sum(vals)
                normalized["market"] = {k: v / total for k, v in zip(("H", "D", "A"), vals)}
        else:
            odds = [_safe_float(row.get(key)) for key in ("home_odds", "draw_odds", "away_odds")]
            if all(value is not None and value > 1.0 for value in odds):
                implied = [1.0 / value for value in odds]
                total = sum(implied)
                if total > 0:
                    normalized["market"] = {key: value / total for key, value in zip(("H", "D", "A"), implied)}
        return normalized
    except (TypeError, ValueError):
        return None


def load_matches(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        rows = [_normalize_match(row) for row in csv.DictReader(f)]
    valid = [r for r in rows if r is not None]
    valid.sort(key=lambda r: (r["match_date"], r["division"], r["home_team"], r["away_team"]))
    if len(valid) < 100:
        raise ValueError(f"Need at least 100 valid completed matches for a meaningful backtest; found {len(valid)}")
    return valid


def _score_probabilities(rows: list[dict[str, Any]], model_name: str, *, bins: int = 10) -> dict[str, Any]:
    """Score multiclass forecasts and report one-vs-rest reliability by probability bin."""
    outcomes = ("H", "D", "A")
    brier_values: list[float] = []
    logloss_values: list[float] = []
    correct = 0
    calibration: dict[str, Any] = {}
    for row in rows:
        probs = row[model_name]
        actual = row["actual"]
        brier_values.append(sum((probs[outcome] - float(actual == outcome)) ** 2 for outcome in outcomes))
        logloss_values.append(-math.log(max(1e-15, min(1.0, probs[actual]))))
        correct += int(max(probs, key=probs.get) == actual)
    for outcome in outcomes:
        bucket_counts = [0] * bins
        predicted_sums = [0.0] * bins
        observed_sums = [0] * bins
        for row in rows:
            probability = min(1.0, max(0.0, float(row[model_name][outcome])))
            index = min(bins - 1, int(probability * bins))
            bucket_counts[index] += 1
            predicted_sums[index] += probability
            observed_sums[index] += float(row["actual"] == outcome)
        reliability = []
        weighted_gap = 0.0
        for index, count in enumerate(bucket_counts):
            if not count:
                continue
            mean_predicted = predicted_sums[index] / count
            observed_rate = observed_sums[index] / count
            weighted_gap += count / len(rows) * abs(mean_predicted - observed_rate)
            reliability.append({
                "bin_lower": index / bins,
                "bin_upper": (index + 1) / bins,
                "matches": count,
                "mean_predicted_probability": mean_predicted,
                "observed_frequency": observed_rate,
                "absolute_gap": abs(mean_predicted - observed_rate),
            })
        calibration[outcome] = {
            "expected_calibration_error": weighted_gap,
            "reliability_bins": reliability,
        }
    return {
        "matches": len(rows),
        "brier_score": sum(brier_values) / len(brier_values),
        "log_loss": sum(logloss_values) / len(logloss_values),
        "result_accuracy": correct / len(rows),
        "calibration": calibration,
    }


def chronological_backtest(matches: Iterable[dict[str, Any]], *, min_training_matches: int = 100,
                           form_window: int = 10, elo_k: float = 20.0,
                           home_elo_advantage: float = 55.0) -> dict[str, Any]:
    """Walk forward by date; never use results from the prediction date as inputs."""
    if min_training_matches < 1 or form_window < 1 or elo_k <= 0:
        raise ValueError("Training minimum, form window and Elo K must be positive")
    clean = [r for raw in matches if (r := _normalize_match(raw)) is not None]
    clean.sort(key=lambda r: (r["match_date"], r["division"], r["home_team"], r["away_team"]))
    if not clean:
        raise ValueError("No valid matches supplied")

    # Per-league team history stores (goals scored, goals conceded) split by venue.
    venue_history: dict[tuple[str, str, str], deque[tuple[int, int]]] = defaultdict(lambda: deque(maxlen=form_window))
    ratings: dict[tuple[str, str], float] = defaultdict(lambda: 1500.0)
    league_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0]) # matches, home goals, away goals
    league_draws: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    scored: list[dict[str, Any]] = []
    history_count = 0

    # Same-day matches are all predicted before any result from that date is ingested.
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in clean:
        by_date[match["match_date"]].append(match)

    for day in sorted(by_date):
        todays = by_date[day]
        for m in todays:
            lid, home, away = m["division"], m["home_team"], m["away_team"]
            totals = league_totals[lid]
            if history_count >= min_training_matches and totals[0] >= 10:
                avg_home = max(0.15, totals[1] / totals[0])
                avg_away = max(0.15, totals[2] / totals[0])
                # Shrink sparse venue samples toward the league scoring average.
                def rate(team: str, venue: str, index: int, prior: float) -> float:
                    hist = list(venue_history[(lid, team, venue)])
                    values = [x[index] for x in hist]
                    strength = 5.0
                    return (sum(values) + strength * prior) / (len(values) + strength)
                home_attack = rate(home, "home", 0, avg_home) / avg_home
                away_defence = rate(away, "away", 1, avg_home) / avg_home
                away_attack = rate(away, "away", 0, avg_away) / avg_away
                home_defence = rate(home, "home", 1, avg_away) / avg_away
                home_lambda = min(5.0, max(0.15, avg_home * home_attack * away_defence))
                away_lambda = min(5.0, max(0.15, avg_away * away_attack * home_defence))
                poisson = poisson_1x2(home_lambda, away_lambda)
                draws = league_draws[lid]
                draw_rate = (draws[1] + 3.0) / (draws[0] + 10.0)
                elo = _elo_probs(ratings[(lid, home)], ratings[(lid, away)], home_elo_advantage, draw_rate)
                scored.append({"match_date": day, "division": lid, "home_team": home, "away_team": away,
                    "actual": m["result"], "home_goals": m["home_goals"], "away_goals": m["away_goals"],
                    "home_expected_goals": home_lambda, "away_expected_goals": away_lambda,
                    "poisson": poisson, "elo": elo,
                    **({"market": m["market"]} if "market" in m else {})})
        # Update ratings and form only after all fixtures on this date were forecast.
        for m in todays:
            lid, home, away = m["division"], m["home_team"], m["away_team"]
            hg, ag = m["home_goals"], m["away_goals"]
            rh, ra = ratings[(lid, home)], ratings[(lid, away)]
            expected = 1.0 / (1.0 + 10.0 ** (-(rh + home_elo_advantage - ra) / 400.0))
            actual_score = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
            goal_weight = min(2.0, 1.0 + abs(hg - ag) * 0.1)
            delta = elo_k * goal_weight * (actual_score - expected)
            ratings[(lid, home)] = rh + delta
            ratings[(lid, away)] = ra - delta
            venue_history[(lid, home, "home")].append((hg, ag))
            venue_history[(lid, away, "away")].append((ag, hg))
            league_totals[lid][0] += 1
            league_totals[lid][1] += hg
            league_totals[lid][2] += ag
            league_draws[lid][0] += 1
            league_draws[lid][1] += int(hg == ag)
            history_count += 1

    if not scored:
        raise ValueError("No test predictions produced; lower min_training_matches or supply more history")
    metrics = {name: _score_probabilities(scored, name) for name in ("poisson", "elo")}
    winner = min(metrics, key=lambda name: metrics[name]["log_loss"])
    # Compare de-vigged odds against both models on the same covered fixtures.
    odds_rows = [row for row in scored if "market" in row]
    odds_subset_metrics = {}
    if odds_rows:
        odds_subset_metrics = {name: _score_probabilities(odds_rows, name) for name in ("poisson", "elo", "market")}
    return {"status": "BACKTESTED_NOT_PROOF_OF_PROFIT", "test_matches": len(scored),
        "first_test_date": scored[0]["match_date"], "last_test_date": scored[-1]["match_date"],
        "models": metrics, "lower_log_loss_model": winner,
        "historical_odds_subset": {"matches_with_valid_1x2_odds": len(odds_rows), "models_compared_on_same_matches": odds_subset_metrics,
            "warning": "Historical odds are indicative only; timestamp and closing-line quality are not verified."},
        "notes": ["Chronological test; matches on the same date are predicted before that date's results are added.",
                  "Poisson model uses shrunk historical venue-specific goals for/against; Elo is a separate baseline.",
                  "No ROI claim: odds coverage, timestamp quality and closing-line quality must be audited separately.",
                  "Calibration is diagnostic only; no fitted recalibration is applied to predictions."],
        "predictions": scored}


def write_report(result: dict[str, Any], output: str | Path) -> None:
    report = {key: value for key, value in result.items() if key != "predictions"}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
