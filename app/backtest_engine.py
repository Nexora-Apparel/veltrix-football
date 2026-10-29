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

from app.live_predictions import ELO_K, HOME_ELO_ADVANTAGE, MIN_TEAM_MATCHES, _name_key
from app.advanced_models import dixon_coles_1x2, recency_weighted_mean
from app.bias_audit import audit_favourites_and_underdogs


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
        home_score = _safe_float(row.get("home_goals", row.get("FTHome")))
        away_score = _safe_float(row.get("away_goals", row.get("FTAway")))
        if (
            home_score is None or away_score is None
            or not home_score.is_integer() or not away_score.is_integer()
            or home_score < 0 or away_score < 0
        ):
            return None
        hg, ag = int(home_score), int(away_score)
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




def goal_market_probabilities(home_lambda: float, away_lambda: float) -> dict[str, float]:
    """Derive BTTS and goal-total probabilities from the same pre-match xG inputs."""
    home = _poisson_probs(home_lambda)
    away = _poisson_probs(away_lambda)
    btts_yes = sum(hp * ap for hg, hp in enumerate(home) for ag, ap in enumerate(away) if hg > 0 and ag > 0)
    totals = {
        "over_1_5": sum(hp * ap for hg, hp in enumerate(home) for ag, ap in enumerate(away) if hg + ag >= 2),
        "over_2_5": sum(hp * ap for hg, hp in enumerate(home) for ag, ap in enumerate(away) if hg + ag >= 3),
        "over_3_5": sum(hp * ap for hg, hp in enumerate(home) for ag, ap in enumerate(away) if hg + ag >= 4),
    }
    return {
        "btts_yes": btts_yes,
        "btts_no": 1.0 - btts_yes,
        **totals,
        **{key.replace("over", "under"): 1.0 - value for key, value in totals.items()},
    }


def _score_expanding_goal_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score a prior-dates-only historical-frequency baseline."""
    definitions = {
        "btts_yes": lambda r: r["home_goals"] > 0 and r["away_goals"] > 0,
        "over_1_5": lambda r: r["home_goals"] + r["away_goals"] >= 2,
        "over_2_5": lambda r: r["home_goals"] + r["away_goals"] >= 3,
        "over_3_5": lambda r: r["home_goals"] + r["away_goals"] >= 4,
    }
    history = {k: [] for k in definitions}
    pairs = {k: [] for k in definitions}
    ordered = sorted(rows, key=lambda r: str(r.get("match_date", "")))
    i = 0
    while i < len(ordered):
        day = str(ordered[i].get("match_date", ""))
        j = i
        while j < len(ordered) and str(ordered[j].get("match_date", "")) == day:
            j += 1
        day_rows = ordered[i:j]
        for key, outcome_fn in definitions.items():
            prior = history[key]
            p = (sum(prior) + 1.0) / (len(prior) + 2.0)
            for row in day_rows:
                pairs[key].append((p, int(bool(outcome_fn(row)))))
            history[key].extend(int(bool(outcome_fn(row))) for row in day_rows)
        i = j
    markets = {}
    for key, values in pairs.items():
        ps = [min(1 - 1e-15, max(1e-15, p)) for p, _ in values]
        ys = [y for _, y in values]
        n = len(values)
        brier = sum((p-y)**2 for p,y in zip(ps,ys))/n if n else None
        loss = -sum(y*math.log(p)+(1-y)*math.log(1-p) for p,y in zip(ps,ys))/n if n else None
        accuracy = sum((p >= 0.5) == bool(y) for p,y in zip(ps,ys))/n if n else None
        observed = sum(ys)/n if n else None
        mean_p = sum(ps)/n if n else None
        markets[key] = {"matches": n, "brier_score": brier, "log_loss": loss, "accuracy": accuracy, "observed_frequency": observed, "mean_predicted_probability": mean_p}
        inverse = key.replace("yes", "no").replace("over", "under")
        inverse_accuracy = sum(((1-p) >= 0.5) == bool(1-y) for p, y in zip(ps, ys)) / n if n else None
        markets[inverse] = {"matches": n, "brier_score": brier, "log_loss": loss, "accuracy": inverse_accuracy, "observed_frequency": 1-observed if n else None, "mean_predicted_probability": 1-mean_p if n else None}
    return {"method": "expanding historical base rate; prior dates only; Beta(1,1) smoothing", "matches": len(ordered), "markets": markets}

def _score_goal_markets(rows: list[dict[str, Any]], probability_key: str = "goal_markets") -> dict[str, Any]:
    """Score BTTS and totals as binary forecasts using Brier score, log loss and accuracy."""
    definitions = {
        "btts_yes": lambda row: row["home_goals"] > 0 and row["away_goals"] > 0,
        "btts_no": lambda row: row["home_goals"] == 0 or row["away_goals"] == 0,
        "over_1_5": lambda row: row["home_goals"] + row["away_goals"] >= 2,
        "under_1_5": lambda row: row["home_goals"] + row["away_goals"] < 2,
        "over_2_5": lambda row: row["home_goals"] + row["away_goals"] >= 3,
        "under_2_5": lambda row: row["home_goals"] + row["away_goals"] < 3,
        "over_3_5": lambda row: row["home_goals"] + row["away_goals"] >= 4,
        "under_3_5": lambda row: row["home_goals"] + row["away_goals"] < 4,
    }
    result: dict[str, Any] = {"matches": len(rows), "markets": {}, "expanding_base_rate_baseline": _score_expanding_goal_baseline(rows)}
    for market, is_winner in definitions.items():
        evaluated = [
            (float(row[probability_key][market]), bool(is_winner(row)))
            for row in rows if probability_key in row and market in row[probability_key]
        ]
        if not evaluated:
            result["markets"][market] = {"matches": 0, "brier_score": None, "log_loss": None, "accuracy": None}
            continue
        probs = [min(1.0, max(0.0, p)) for p, _ in evaluated]
        outcomes = [int(actual) for _, actual in evaluated]
        count = len(evaluated)
        result["markets"][market] = {
            "matches": count,
            "brier_score": sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / count,
            "log_loss": sum(-math.log(max(1e-15, min(1.0, p if y else 1.0 - p))) for p, y in zip(probs, outcomes)) / count,
            "accuracy": sum((p >= 0.5) == bool(y) for p, y in zip(probs, outcomes)) / count,
            "observed_frequency": sum(outcomes) / count,
            "mean_predicted_probability": sum(probs) / count,
        }
    baseline_markets = result["expanding_base_rate_baseline"]["markets"]
    comparison = {}
    for market, model_metrics in result["markets"].items():
        baseline_metrics = baseline_markets.get(market, {})
        if not model_metrics.get("matches") or not baseline_metrics.get("matches"):
            comparison[market] = {"status": "INSUFFICIENT_MATCHES"}
            continue
        brier_delta = model_metrics["brier_score"] - baseline_metrics["brier_score"]
        log_loss_delta = model_metrics["log_loss"] - baseline_metrics["log_loss"]
        accuracy_delta = model_metrics["accuracy"] - baseline_metrics["accuracy"]
        comparison[market] = {
            "matches": model_metrics["matches"],
            "brier_delta_model_minus_baseline": brier_delta,
            "log_loss_delta_model_minus_baseline": log_loss_delta,
            "accuracy_delta_model_minus_baseline": accuracy_delta,
            "probability_scores_better": brier_delta < 0 and log_loss_delta < 0,
            "interpretation": (
                "MODEL_BEATS_BASELINE_ON_BRIER_AND_LOG_LOSS"
                if brier_delta < 0 and log_loss_delta < 0
                else "MODEL_DOES_NOT_BEAT_BASELINE_ON_BOTH_PROBABILITY_SCORES"
            ),
        }
    result["model_vs_expanding_baseline"] = {
        "delta_convention": "model metric minus baseline metric; negative Brier/log loss is better; positive accuracy is better",
        "markets": comparison,
    }
    return result


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


def _compact_score(rows: list[dict[str, Any]], model_name: str) -> dict[str, Any] | None:
    """Calculate compact metrics without calibration bins for league breakdowns."""
    if not rows:
        return None
    outcomes = ("H", "D", "A")
    brier_total = 0.0
    logloss_total = 0.0
    correct = 0
    for row in rows:
        probabilities = row[model_name]
        actual = row["actual"]
        brier_total += sum(
            (probabilities[outcome] - float(actual == outcome)) ** 2
            for outcome in outcomes
        )
        logloss_total += -math.log(max(1e-15, min(1.0, probabilities[actual])))
        correct += int(max(probabilities, key=probabilities.get) == actual)
    count = len(rows)
    return {
        "matches": count,
        "brier_score": brier_total / count,
        "log_loss": logloss_total / count,
        "result_accuracy": correct / count,
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

    # Separate walk-forward state that mirrors the live experimental model exactly.
    live_team_history: dict[str, deque[tuple[int, int, str]]] = defaultdict(lambda: deque(maxlen=10))
    live_totals = [0, 0, 0]  # matches, home goals, away goals across all competitions
    live_scored: list[dict[str, Any]] = []
    # Separate competition-scoped Elo state mirrors the alternative live model.
    live_elo_ratings: dict[tuple[str, str], float] = defaultdict(lambda: 1500.0)
    live_elo_team_matches: dict[tuple[str, str], int] = defaultdict(int)
    live_elo_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # matches, draws

    # Same-day matches are all predicted before any result from that date is ingested.
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in clean:
        by_date[match["match_date"]].append(match)

    for day in sorted(by_date):
        todays = by_date[day]
        for m in todays:
            if day >= "2020-01-01":
                # Evaluate the exact live-pipeline baseline using only results from
                # strictly earlier dates. Keep this separate from the league-aware
                # research baselines below because their eligibility rules differ.
                home_key, away_key = _name_key(m["home_team"]), _name_key(m["away_team"])
                home_hist = list(live_team_history[home_key])
                away_hist = list(live_team_history[away_key])
                live_elo_probs = None
                division = m["division"]
                competition_totals = live_elo_totals[division]
                if (
                    competition_totals[0] >= 10
                    and live_elo_team_matches[(division, home_key)] >= MIN_TEAM_MATCHES
                    and live_elo_team_matches[(division, away_key)] >= MIN_TEAM_MATCHES
                ):
                    home_rating = live_elo_ratings[(division, home_key)]
                    away_rating = live_elo_ratings[(division, away_key)]
                    expected_home = 1.0 / (
                        1.0 + 10.0 ** (-(home_rating + HOME_ELO_ADVANTAGE - away_rating) / 400.0)
                    )
                    draw_rate = (competition_totals[1] + 3.0) / (competition_totals[0] + 10.0)
                    non_draw = 1.0 - draw_rate
                    live_elo_probs = {
                        "H": non_draw * expected_home,
                        "D": draw_rate,
                        "A": non_draw * (1.0 - expected_home),
                    }
                if len(home_hist) >= 5 and len(away_hist) >= 5 and live_totals[0] > 0:
                    live_home_baseline = max(0.05, live_totals[1] / live_totals[0])
                    live_away_baseline = max(0.05, live_totals[2] / live_totals[0])
    
                    def live_rate(
                        history: list[tuple[int, int, str]],
                        venue: str,
                        scored_prior: float,
                        conceded_prior: float,
                    ) -> tuple[float, float]:
                        relevant = [row for row in history if row[2] == venue] or history
                        weight = len(relevant) / (len(relevant) + 4.0)
                        scored = sum(row[0] for row in relevant) / len(relevant)
                        conceded = sum(row[1] for row in relevant) / len(relevant)
                        return (
                            weight * scored + (1 - weight) * scored_prior,
                            weight * conceded + (1 - weight) * conceded_prior,
                        )
    
                    home_scored, home_conceded = live_rate(
                        home_hist, "home", live_home_baseline, live_away_baseline
                    )
                    away_scored, away_conceded = live_rate(
                        away_hist, "away", live_away_baseline, live_home_baseline
                    )
                    home_xg = min(5.0, max(0.05,
                        live_home_baseline * (home_scored / live_home_baseline)
                        * (away_conceded / live_home_baseline)
                    ))
                    away_xg = min(5.0, max(0.05,
                        live_away_baseline * (away_scored / live_away_baseline)
                        * (home_conceded / live_away_baseline)
                    ))
                    live_probs = poisson_1x2(home_xg, away_xg)

                    # Separate research candidate: recency-weighted venue form and
                    # Dixon-Coles low-score correction. Same-day results are still
                    # excluded because histories are updated only after this loop.
                    def weighted_live_rate(
                        history: list[tuple[int, int, str]],
                        venue: str,
                        scored_prior: float,
                        conceded_prior: float,
                    ) -> tuple[float, float]:
                        relevant = [row for row in history if row[2] == venue] or history
                        weight = len(relevant) / (len(relevant) + 4.0)
                        scored = recency_weighted_mean([row[0] for row in relevant], decay=0.85)
                        conceded = recency_weighted_mean([row[1] for row in relevant], decay=0.85)
                        return (
                            weight * scored + (1 - weight) * scored_prior,
                            weight * conceded + (1 - weight) * conceded_prior,
                        )

                    whs, whc = weighted_live_rate(
                        home_hist, "home", live_home_baseline, live_away_baseline
                    )
                    was, wac = weighted_live_rate(
                        away_hist, "away", live_away_baseline, live_home_baseline
                    )
                    weighted_home_xg = min(5.0, max(0.05,
                        live_home_baseline * (whs / live_home_baseline)
                        * (wac / live_home_baseline)
                    ))
                    weighted_away_xg = min(5.0, max(0.05,
                        live_away_baseline * (was / live_away_baseline)
                        * (whc / live_away_baseline)
                    ))
                    live_dc_probs = dixon_coles_1x2(
                        weighted_home_xg, weighted_away_xg, rho=-0.05
                    )
                    live_scored.append({
                        "match_date": day,
                        "division": m["division"],
                        "home_team": m["home_team"],
                        "away_team": m["away_team"],
                        "actual": m["result"],
                        "home_goals": m["home_goals"],
                        "away_goals": m["away_goals"],
                        "live_poisson": live_probs,
                        "live_goal_markets": goal_market_probabilities(home_xg, away_xg),
                        "live_dc": live_dc_probs,
                        "live_dc_home_xg": weighted_home_xg,
                        "live_dc_away_xg": weighted_away_xg,
                        **({"live_elo": live_elo_probs} if live_elo_probs is not None else {}),
                        **({"market": m["market"]} if "market" in m else {}),
                    })
    
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
                    "goal_markets": goal_market_probabilities(home_lambda, away_lambda),
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

            if day >= "2020-01-01":
                # The live model's global team history is updated only after every
                # match on this date has been forecast, preventing same-day leakage.
                live_team_history[_name_key(home)].append((hg, ag, "home"))
                live_team_history[_name_key(away)].append((ag, hg, "away"))
                live_totals[0] += 1
                live_totals[1] += hg
                live_totals[2] += ag

                division = m["division"]
                home_key, away_key = _name_key(home), _name_key(away)
                home_rating = live_elo_ratings[(division, home_key)]
                away_rating = live_elo_ratings[(division, away_key)]
                expected_home = 1.0 / (
                    1.0 + 10.0 ** (-(home_rating + HOME_ELO_ADVANTAGE - away_rating) / 400.0)
                )
                actual_score = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
                goal_weight = min(2.0, 1.0 + abs(hg - ag) * 0.1)
                delta = ELO_K * goal_weight * (actual_score - expected_home)
                live_elo_ratings[(division, home_key)] = home_rating + delta
                live_elo_ratings[(division, away_key)] = away_rating - delta
                live_elo_team_matches[(division, home_key)] += 1
                live_elo_team_matches[(division, away_key)] += 1
                live_elo_totals[division][0] += 1
                live_elo_totals[division][1] += int(hg == ag)

    if not scored:
        raise ValueError("No test predictions produced; lower min_training_matches or supply more history")
    metrics = {name: _score_probabilities(scored, name) for name in ("poisson", "elo")}
    goal_market_metrics = _score_goal_markets(scored)
    winner = min(metrics, key=lambda name: metrics[name]["log_loss"])

    live_metrics = _score_probabilities(live_scored, "live_poisson") if live_scored else None
    live_goal_market_metrics = _score_goal_markets(live_scored, "live_goal_markets") if live_scored else None
    live_dc_metrics = _score_probabilities(live_scored, "live_dc") if live_scored else None
    live_elo_rows = [row for row in live_scored if "live_elo" in row]
    live_elo_metrics = _score_probabilities(live_elo_rows, "live_elo") if live_elo_rows else None
    live_dates = sorted({row["match_date"] for row in live_scored})
    live_holdout = None
    if live_scored:
        live_holdout_index = min(len(live_dates) - 1, max(0, int(len(live_dates) * 0.8)))
        live_holdout_start = live_dates[live_holdout_index]
        live_holdout_rows = [row for row in live_scored if row["match_date"] >= live_holdout_start]
        live_holdout_metrics = _score_probabilities(live_holdout_rows, "live_poisson")
        live_goal_market_holdout_metrics = _score_goal_markets(live_holdout_rows, "live_goal_markets")
        live_dc_holdout_metrics = _score_probabilities(live_holdout_rows, "live_dc")
        live_elo_holdout_rows = [row for row in live_holdout_rows if "live_elo" in row]
        live_elo_odds_rows = [row for row in live_elo_rows if "market" in row]
        live_elo_holdout_odds_rows = [row for row in live_elo_holdout_rows if "market" in row]
        live_odds_rows = [row for row in live_scored if "market" in row]
        live_holdout_odds_rows = [row for row in live_holdout_rows if "market" in row]
        live_holdout = {
            "method": "latest 20% of unique live-eligible forecast dates",
            "start_date": live_holdout_start,
            "end_date": live_dates[-1],
            "matches": len(live_holdout_rows),
            "metrics": live_holdout_metrics,
            "dixon_coles_alternative": {
                "model": "experimental_recency_weighted_dixon_coles",
                "rho": -0.05,
                "metrics": live_dc_holdout_metrics,
                "model_validated": False,
            },
            "historical_odds_subset": {
                "matches_with_valid_1x2_odds": len(live_holdout_odds_rows),
                "models_compared_on_same_matches": {
                    "live_poisson": _score_probabilities(live_holdout_odds_rows, "live_poisson"),
                    "market": _score_probabilities(live_holdout_odds_rows, "market"),
                } if live_holdout_odds_rows else {},
            },
            "elo_alternative": {
                "matches": len(live_elo_holdout_rows),
                "metrics": _score_probabilities(live_elo_holdout_rows, "live_elo") if live_elo_holdout_rows else None,
                "historical_odds_subset": {
                    "matches_with_valid_1x2_odds": len(live_elo_holdout_odds_rows),
                    "models_compared_on_same_matches": {
                        "live_elo": _score_probabilities(live_elo_holdout_odds_rows, "live_elo"),
                        "market": _score_probabilities(live_elo_holdout_odds_rows, "market"),
                    } if live_elo_holdout_odds_rows else {},
                },
            },
        }
        live_odds_subset = {
            "matches_with_valid_1x2_odds": len(live_odds_rows),
            "models_compared_on_same_matches": {
                "live_poisson": _score_probabilities(live_odds_rows, "live_poisson"),
                "market": _score_probabilities(live_odds_rows, "market"),
            } if live_odds_rows else {},
            "warning": "Historical odds are indicative only; timestamp and closing-line quality are not verified.",
        }
        live_elo_odds_subset = {
            "matches_with_valid_1x2_odds": len(live_elo_odds_rows),
            "models_compared_on_same_matches": {
                "live_elo": _score_probabilities(live_elo_odds_rows, "live_elo"),
                "market": _score_probabilities(live_elo_odds_rows, "market"),
            } if live_elo_odds_rows else {},
            "warning": "Historical odds are indicative only; timestamp and closing-line quality are not verified.",
        }
    else:
        live_odds_subset = {
            "matches_with_valid_1x2_odds": 0,
            "models_compared_on_same_matches": {},
            "warning": "No eligible live-pipeline forecasts were produced.",
        }
        live_elo_odds_subset = {
            "matches_with_valid_1x2_odds": 0,
            "models_compared_on_same_matches": {},
            "warning": "No eligible live Elo forecasts were produced.",
        }

    live_metrics_by_competition: dict[str, Any] = {}
    for division in sorted({str(row["division"]) for row in live_scored}):
        competition_rows = [row for row in live_scored if str(row["division"]) == division]
        competition_elo_rows = [row for row in competition_rows if "live_elo" in row]
        competition_odds_rows = [row for row in competition_rows if "market" in row]
        competition_elo_odds_rows = [row for row in competition_elo_rows if "market" in row]
        competition_holdout_rows = [
            row for row in competition_rows
            if live_holdout and row["match_date"] >= live_holdout["start_date"]
        ]
        competition_elo_holdout_rows = [row for row in competition_holdout_rows if "live_elo" in row]
        competition_holdout_odds_rows = [row for row in competition_holdout_rows if "market" in row]
        competition_elo_holdout_odds_rows = [row for row in competition_elo_holdout_rows if "market" in row]
        live_metrics_by_competition[division] = {
            "live_eligible_matches": len(competition_rows),
            "poisson": _compact_score(competition_rows, "live_poisson"),
            "elo": _compact_score(competition_elo_rows, "live_elo"),
            "historical_odds_matches": len(competition_odds_rows),
            "same_match_market_comparison": {
                "poisson": _compact_score(competition_odds_rows, "live_poisson"),
                "market": _compact_score(competition_odds_rows, "market"),
            } if competition_odds_rows else {},
            "elo_same_match_market_comparison": {
                "elo": _compact_score(competition_elo_odds_rows, "live_elo"),
                "market": _compact_score(competition_elo_odds_rows, "market"),
            } if competition_elo_odds_rows else {},
            "recent_holdout": {
                "matches": len(competition_holdout_rows),
                "poisson": _compact_score(competition_holdout_rows, "live_poisson"),
                "elo": _compact_score(competition_elo_holdout_rows, "live_elo"),
                "same_match_market_comparison": {
                    "poisson": _compact_score(competition_holdout_odds_rows, "live_poisson"),
                    "market": _compact_score(competition_holdout_odds_rows, "market"),
                } if competition_holdout_odds_rows else {},
                "elo_same_match_market_comparison": {
                    "elo": _compact_score(competition_elo_holdout_odds_rows, "live_elo"),
                    "market": _compact_score(competition_elo_holdout_odds_rows, "market"),
                } if competition_elo_holdout_odds_rows else {},
            },
        }

    # Reserve the latest 20% of unique forecast dates as a final-period diagnostic.
    # Forecasts remain walk-forward: each match is predicted before same-day results
    # are ingested. The cutoff is date-based so matches on one date cannot split.
    forecast_dates = sorted({row["match_date"] for row in scored})
    holdout_index = min(len(forecast_dates) - 1, max(0, int(len(forecast_dates) * 0.8)))
    holdout_start = forecast_dates[holdout_index]
    holdout_rows = [row for row in scored if row["match_date"] >= holdout_start]
    holdout_metrics = {name: _score_probabilities(holdout_rows, name) for name in ("poisson", "elo")}
    holdout_goal_market_metrics = _score_goal_markets(holdout_rows)

    # Compare de-vigged odds against both models on the same covered fixtures.
    odds_rows = [row for row in scored if "market" in row]
    odds_subset_metrics = {}
    holdout_odds_rows = [row for row in holdout_rows if "market" in row]
    holdout_odds_metrics = {}
    if odds_rows:
        odds_subset_metrics = {name: _score_probabilities(odds_rows, name) for name in ("poisson", "elo", "market")}
    if holdout_odds_rows:
        holdout_odds_metrics = {name: _score_probabilities(holdout_odds_rows, name) for name in ("poisson", "elo", "market")}
    return {"status": "BACKTESTED_NOT_PROOF_OF_PROFIT", "test_matches": len(scored),
        "first_test_date": scored[0]["match_date"], "last_test_date": scored[-1]["match_date"],
        "models": metrics, "lower_log_loss_model": winner,
        "favourite_underdog_audit": {
            "poisson": audit_favourites_and_underdogs(scored, model_key="poisson"),
            "elo": audit_favourites_and_underdogs(scored, model_key="elo"),
            "note": "Evaluation-only subgroup diagnostic using de-vigged historical market probabilities to classify favourites and underdogs; it does not measure club fame or alter forecasts.",
        },
        "goal_markets": {
            "model": "chronological_shrunk_venue_poisson",
            "metrics": goal_market_metrics,
            "recent_holdout": holdout_goal_market_metrics,
            "note": "BTTS and goal totals are evaluated from pre-match expected goals on chronological predictions; this is not evidence of profitability or validation.",
        },
        "live_pipeline": {"model": "experimental_recent_goals_poisson", "matches": len(live_scored),
            "first_test_date": live_dates[0] if live_dates else None,
            "last_test_date": live_dates[-1] if live_dates else None,
            "metrics": live_metrics,
            "goal_markets": {
                "metrics": live_goal_market_metrics,
                "recent_holdout": live_goal_market_holdout_metrics if live_scored else None,
                "note": "BTTS and totals derived from the same pre-match xG as the live Poisson baseline; research evaluation only.",
            },
            "dixon_coles_alternative": {
                "model": "experimental_recency_weighted_dixon_coles",
                "rho": -0.05,
                "metrics": live_dc_metrics,
                "model_validated": False,
                "note": "Alternative only; fixed rho has not been calibrated on a validation fold.",
            },
            "recent_holdout": live_holdout,
            "metrics_by_competition": live_metrics_by_competition,
            "historical_odds_subset": live_odds_subset,
            "favourite_underdog_audit": {
                "poisson": audit_favourites_and_underdogs(live_scored, model_key="live_poisson"),
                "elo": audit_favourites_and_underdogs(live_elo_rows, model_key="live_elo"),
                "note": "Evaluation-only subgroup diagnostic on market-covered walk-forward fixtures; not a causal measure of fame bias.",
            },
            "elo_alternative": {"model": "experimental_elo_by_competition", "matches": len(live_elo_rows),
                "metrics": live_elo_metrics, "historical_odds_subset": live_elo_odds_subset,
                "recent_holdout": live_holdout.get("elo_alternative") if live_holdout else None,
                "note": "Competition-scoped Elo forecast evaluated only where the production live pipeline would emit a fixture record; scores are independent from Poisson."},
            "note": "Separate walk-forward evaluation of live prediction logic, using only matches dated 2020-01-01 onward. Same-day results are added only after all forecasts for that date."},
        "recent_holdout": {"method": "latest 20% of unique forecast dates", "start_date": holdout_start,
            "end_date": forecast_dates[-1], "matches": len(holdout_rows), "models": holdout_metrics,
            "historical_odds_subset": {"matches_with_valid_1x2_odds": len(holdout_odds_rows),
                "models_compared_on_same_matches": holdout_odds_metrics}},
        "historical_odds_subset": {"matches_with_valid_1x2_odds": len(odds_rows), "models_compared_on_same_matches": odds_subset_metrics,
            "warning": "Historical odds are indicative only; timestamp and closing-line quality are not verified."},
        "notes": ["Chronological test; matches on the same date are predicted before that date's results are added.",
                  "Recent holdout is the latest 20% of forecast dates, evaluated from walk-forward predictions.",
                  "Poisson model uses shrunk historical venue-specific goals for/against; Elo is a separate baseline.",
                  "No ROI claim: odds coverage, timestamp quality and closing-line quality must be audited separately.",
                  "Calibration is diagnostic only; no fitted recalibration is applied to predictions.",
                  "The live pipeline is scored separately with its own team-history eligibility and global baselines."],
        "predictions": scored}


def write_report(result: dict[str, Any], output: str | Path) -> None:
    report = {key: value for key, value in result.items() if key != "predictions"}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
