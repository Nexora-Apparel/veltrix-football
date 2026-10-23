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
        return {"match_date": day, "division": division, "home_team": home, "away_team": away,
                "home_goals": hg, "away_goals": ag, "result": "H" if hg > ag else "A" if hg < ag else "D"}
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
                    "poisson": poisson, "elo": elo})
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
    metrics = {}
    for model_name in ("poisson", "elo"):
        brier, logloss, correct = [], [], 0
        for row in scored:
            probs = row[model_name]
            brier.append(sum((probs[outcome] - float(row["actual"] == outcome)) ** 2 for outcome in ("H", "D", "A")))
            logloss.append(-math.log(max(1e-15, probs[row["actual"]])))
            correct += int(max(probs, key=probs.get) == row["actual"])
        metrics[model_name] = {"matches": len(scored), "brier_score": sum(brier) / len(brier),
            "log_loss": sum(logloss) / len(logloss), "result_accuracy": correct / len(scored)}
    winner = min(metrics, key=lambda name: metrics[name]["log_loss"])
    return {"status": "BACKTESTED_NOT_PROOF_OF_PROFIT", "test_matches": len(scored),
        "first_test_date": scored[0]["match_date"], "last_test_date": scored[-1]["match_date"],
        "models": metrics, "lower_log_loss_model": winner,
        "notes": ["Chronological test; matches on the same date are predicted before that date's results are added.",
                  "Poisson model uses shrunk historical venue-specific goals for/against; Elo is a separate baseline.",
                  "No ROI claim: odds coverage, timestamp quality and probability calibration must be audited separately."],
        "predictions": scored}


def write_report(result: dict[str, Any], output: str | Path) -> None:
    report = {key: value for key, value in result.items() if key != "predictions"}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
