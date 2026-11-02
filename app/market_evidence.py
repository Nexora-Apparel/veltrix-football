"""Evidence-gated match features, odds snapshots, CLV and market diagnostics.

This module deliberately fails closed: unverified xG/lineups/PPDA are never
silently substituted with proxies. All timestamps are timezone-aware UTC instants.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

OUTCOMES_1X2 = ("H", "D", "A")


def _aware_utc(value: Any, field: str = "timestamp") -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def verified_feature(value: Any, *, source: str, observed_at: Any,
                     forecast_at: Any, status: str = "VERIFIED") -> dict[str, Any]:
    """Create a feature record only when sourced before forecast time."""
    observed = _aware_utc(observed_at, "observed_at")
    cutoff = _aware_utc(forecast_at, "forecast_at")
    if observed > cutoff:
        raise ValueError("feature timestamp is after forecast cutoff (look-ahead leakage)")
    if not source or status != "VERIFIED":
        raise ValueError("feature requires a named source and VERIFIED status")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("feature value must be finite")
    return {"value": number, "source": source, "observed_at": observed.isoformat(),
            "status": "VERIFIED", "forecast_cutoff": cutoff.isoformat()}


def verified_xg_pair(home: Mapping[str, Any] | None, away: Mapping[str, Any] | None,
                     *, forecast_at: Any) -> dict[str, Any]:
    """Accept only provider-sourced pre-match xG; never relabel goals as xG."""
    if not home or not away:
        return {"status": "UNAVAILABLE", "reason": "verified_home_and_away_xg_required"}
    try:
        h = verified_feature(home["value"], source=str(home["source"]),
                             observed_at=home["observed_at"], forecast_at=forecast_at)
        a = verified_feature(away["value"], source=str(away["source"]),
                             observed_at=away["observed_at"], forecast_at=forecast_at)
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "REJECTED", "reason": str(exc)}
    if h["value"] < 0 or a["value"] < 0:
        return {"status": "REJECTED", "reason": "xG cannot be negative"}
    return {"status": "VERIFIED", "home": h, "away": a}


def confirmed_lineup_strength(players: Iterable[Mapping[str, Any]] | None,
                              *, source: str, confirmed_at: Any,
                              forecast_at: Any) -> dict[str, Any]:
    """Calculate an availability-weighted rating only from a confirmed XI.

    Each player requires a numeric precomputed rating and an explicit
    confirmed_starting_xi=True flag. Ratings must be on a common documented scale.
    """
    if players is None:
        return {"status": "UNAVAILABLE", "reason": "confirmed_starting_xi_not_connected"}
    try:
        observed = _aware_utc(confirmed_at, "confirmed_at")
        cutoff = _aware_utc(forecast_at, "forecast_at")
        rows = list(players)
        if observed > cutoff:
            raise ValueError("confirmed lineup arrived after forecast cutoff")
        if len(rows) != 11 or any(p.get("confirmed_starting_xi") is not True for p in rows):
            raise ValueError("exactly 11 explicitly confirmed starters required")
        ratings = [float(p["rating"]) for p in rows]
        if any(not math.isfinite(x) for x in ratings):
            raise ValueError("lineup ratings must be finite")
        if not source:
            raise ValueError("lineup source is required")
        return {"status": "VERIFIED", "source": source, "confirmed_at": observed.isoformat(),
                "rating_sum": sum(ratings), "rating_mean": sum(ratings) / 11,
                "players": 11}
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "REJECTED", "reason": str(exc)}


def rest_travel_context(previous_matches: Iterable[Mapping[str, Any]],
                        team_id: str, forecast_at: Any,
                        venue_latitude: float | None = None,
                        venue_longitude: float | None = None) -> dict[str, Any]:
    """Measure rest, congestion and verified travel using known prior venue coordinates."""
    cutoff = _aware_utc(forecast_at, "forecast_at")
    rows = []
    for row in previous_matches:
        if str(row.get("team_id")) != str(team_id):
            continue
        try:
            played = _aware_utc(row["played_at"], "played_at")
            if played >= cutoff:
                continue
            rows.append((played, row))
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda item: item[0])
    last = rows[-1] if rows else None
    rest_hours = (cutoff - last[0]).total_seconds() / 3600 if last else None
    counts = {f"matches_last_{days}d": sum(1 for when, _ in rows
              if (cutoff - when).total_seconds() <= days * 86400) for days in (7, 14, 30)}
    travel_km = None
    travel_status = "UNAVAILABLE"
    if last and venue_latitude is not None and venue_longitude is not None:
        lat, lon = last[1].get("venue_latitude"), last[1].get("venue_longitude")
        try:
            lat, lon = float(lat), float(lon)
            target_lat, target_lon = float(venue_latitude), float(venue_longitude)
            if all(math.isfinite(v) for v in (lat, lon, target_lat, target_lon)):
                if not (-90 <= lat <= 90 and -90 <= target_lat <= 90 and -180 <= lon <= 180 and -180 <= target_lon <= 180):
                    raise ValueError("coordinates out of range")
                rad = math.pi / 180
                dlat, dlon = (target_lat-lat)*rad, (target_lon-lon)*rad
                a = math.sin(dlat/2)**2 + math.cos(lat*rad)*math.cos(target_lat*rad)*math.sin(dlon/2)**2
                travel_km = 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))
                travel_status = "VERIFIED_COORDINATE_DISTANCE"
        except (TypeError, ValueError):
            pass
    return {"rest_hours": rest_hours, **counts, "travel_distance_km": travel_km,
            "travel_status": travel_status, "source_matches": len(rows)}


def capture_odds_snapshot(*, fixture_id: str, market: str, selection: str,
                          decimal_odds: float, bookmaker: str, captured_at: Any,
                          source: str, line: float | None = None,
                          quote_id: str | None = None) -> dict[str, Any]:
    """Normalize an immutable quote record. Persist the returned record append-only."""
    odds = float(decimal_odds)
    if not math.isfinite(odds) or odds <= 1.0:
        raise ValueError("decimal_odds must be finite and > 1")
    if not all((fixture_id, market, selection, bookmaker, source)):
        raise ValueError("fixture, market, selection, bookmaker and source are required")
    line_value = None if line is None else float(line)
    if line_value is not None and not math.isfinite(line_value):
        raise ValueError("line must be finite")
    return {"fixture_id": str(fixture_id), "market": str(market).upper(),
            "selection": str(selection), "line": line_value, "decimal_odds": odds,
            "bookmaker": str(bookmaker), "captured_at": _aware_utc(captured_at).isoformat(),
            "source": str(source), "quote_id": quote_id}


def calculate_clv(snapshots: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare earliest pre-match quote to latest quote per bookmaker/market/line/selection.

    CLV is positive when the captured price is better than the closing price.
    Both timestamps are required; this does not infer a close from untimestamped odds.
    """
    groups: dict[tuple, list[tuple[datetime, Mapping[str, Any]]]] = defaultdict(list)
    for row in snapshots:
        try:
            key = (str(row["fixture_id"]), str(row["market"]).upper(),
                   str(row["selection"]), row.get("line"), str(row["bookmaker"]))
            when = _aware_utc(row["captured_at"], "captured_at")
            odds = float(row["decimal_odds"])
            if odds <= 1 or not math.isfinite(odds):
                continue
            groups[key].append((when, row))
        except (KeyError, TypeError, ValueError):
            continue
    results = []
    for key, items in groups.items():
        items.sort(key=lambda item: item[0])
        if len(items) < 2 or items[0][0] == items[-1][0]:
            continue
        opening = float(items[0][1]["decimal_odds"])
        closing = float(items[-1][1]["decimal_odds"])
        results.append({"fixture_id": key[0], "market": key[1], "selection": key[2],
                        "bookmaker": key[4], "opening_odds": opening, "closing_odds": closing,
                        "clv_percent": (opening / closing - 1.0) * 100.0,
                        "positive_clv": opening > closing,
                        "opening_at": items[0][0].isoformat(),
                        "closing_at": items[-1][0].isoformat()})
    return {"status": "MEASURED" if results else "INSUFFICIENT_TIMESTAMPED_QUOTES",
            "quotes_compared": len(results), "mean_clv_percent":
            (sum(r["clv_percent"] for r in results) / len(results)) if results else None,
            "records": results}


def probability_distribution_audit(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare predicted H/D/A frequency with actual class frequency on scored fixtures."""
    counts = {key: 0 for key in OUTCOMES_1X2}
    predicted = {key: [] for key in OUTCOMES_1X2}
    scored = 0
    for row in rows:
        probs = row.get("probabilities")
        actual = row.get("actual")
        if not isinstance(probs, Mapping) or actual not in OUTCOMES_1X2:
            continue
        try:
            p = {key: float(probs[key]) for key in OUTCOMES_1X2}
        except (KeyError, TypeError, ValueError):
            continue
        if any(not math.isfinite(v) or v < 0 or v > 1 for v in p.values()) or abs(sum(p.values()) - 1) > 1e-5:
            continue
        scored += 1
        counts[actual] += 1
        for key in OUTCOMES_1X2:
            predicted[key].append(p[key])
    if not scored:
        return {"status": "NO_VALID_SCORED_ROWS", "matches": 0}
    actual_share = {key: counts[key] / scored for key in OUTCOMES_1X2}
    predicted_share = {key: sum(values) / scored for key, values in predicted.items()}
    gaps = {key: predicted_share[key] - actual_share[key] for key in OUTCOMES_1X2}
    return {"status": "AUDITED", "matches": scored, "actual_share": actual_share,
            "mean_predicted_probability": predicted_share, "share_gap": gaps,
            "severe_class_imbalance": any(abs(gap) >= 0.08 for gap in gaps.values()),
            "home_overprediction": gaps["H"] >= 0.08,
            "draw_underprediction": gaps["D"] <= -0.08}


def binary_market_metrics(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute strictly proper Brier/log-loss metrics for one binary market."""
    clean = []
    for row in rows:
        try:
            p, y = float(row["probability"]), int(row["actual"])
            if not math.isfinite(p) or not 0 <= p <= 1 or y not in (0, 1):
                continue
            clean.append((min(1-1e-15, max(1e-15, p)), y))
        except (KeyError, TypeError, ValueError):
            continue
    if not clean:
        return {"matches": 0, "brier_score": None, "log_loss": None}
    n = len(clean)
    return {"matches": n, "brier_score": sum((p-y)**2 for p,y in clean)/n,
            "log_loss": -sum(y*math.log(p)+(1-y)*math.log(1-p) for p,y in clean)/n,
            "observed_frequency": sum(y for _,y in clean)/n,
            "mean_predicted_probability": sum(p for p,_ in clean)/n}


def feature_readiness_audit(features: Mapping[str, Any]) -> dict[str, Any]:
    """Report feature readiness without inventing missing xG/lineup/PPDA values."""
    required = ("xg", "confirmed_lineups", "rest_travel", "odds_movement", "ppda", "shot_conversion")
    states = {name: (features.get(name) or {}).get("status", "UNAVAILABLE") for name in required}
    return {"features": states, "ready_count": sum(v in ("VERIFIED", "MEASURED") for v in states.values()),
            "total_features": len(required),
            "production_feature_set_ready": all(v in ("VERIFIED", "MEASURED") for v in states.values())}


def ppda_feature(opponent_passes_allowed: Any, defensive_actions: Any, *,
                 source: str, observed_at: Any, forecast_at: Any) -> dict[str, Any]:
    """Compute PPDA only from provider-sourced passes and defensive actions."""
    try:
        passes = float(opponent_passes_allowed)
        actions = float(defensive_actions)
        if not math.isfinite(passes) or not math.isfinite(actions) or passes < 0 or actions <= 0:
            raise ValueError("PPDA requires finite non-negative passes and positive defensive actions")
        record = verified_feature(passes / actions, source=source,
                                  observed_at=observed_at, forecast_at=forecast_at)
        record["metric"] = "PPDA"
        return record
    except (TypeError, ValueError) as exc:
        return {"status": "REJECTED", "reason": str(exc)}


def shot_conversion_feature(goals: Any, shots_on_target: Any, *,
                            source: str, observed_at: Any,
                            forecast_at: Any) -> dict[str, Any]:
    """Compute goals per shot-on-target; denominator must be positive."""
    try:
        scored, shots = float(goals), float(shots_on_target)
        if (not math.isfinite(scored) or not math.isfinite(shots)
                or scored < 0 or shots <= 0 or scored > shots):
            raise ValueError("shot conversion requires 0 <= goals <= shots_on_target and positive shots")
        record = verified_feature(scored / shots, source=source,
                                  observed_at=observed_at, forecast_at=forecast_at)
        record["metric"] = "goals_per_shot_on_target"
        return record
    except (TypeError, ValueError) as exc:
        return {"status": "REJECTED", "reason": str(exc)}


def chronological_market_experiment(rows: Iterable[Mapping[str, Any]],
                                    market_specs: Mapping[str, Mapping[str, str]],
                                    *, minimum_training_matches: int = 1000,
                                    minimum_test_matches: int = 100) -> dict[str, Any]:
    """Score each market independently on disjoint future date blocks.

    Each spec maps a market name to probability_key and actual_key. For 1X2,
    probability_key must contain H/D/A probabilities and actual_key one of H/D/A.
    Binary markets use probabilities in [0,1] and actual outcomes 0/1.
    This evaluates supplied frozen forecasts; it does not fit models or calibrators.
    """
    source = [dict(row) for row in rows]
    dates = sorted({str(row.get("match_date", "")) for row in source if row.get("match_date")})
    report = {"method": "frozen out-of-sample forecasts; expanding date order; per-market scoring",
              "dates": len(dates), "markets": {}}
    if len(dates) < 3:
        return {**report, "status": "INSUFFICIENT_DATES"}
    # Reserve the first 60% of dates as history and split the remainder into
    # up to four non-overlapping test blocks.
    split = max(1, min(len(dates)-1, int(len(dates)*0.60)))
    test_dates = dates[split:]
    blocks = [list(block) for block in _date_blocks(test_dates, 4)]
    for market, spec in market_specs.items():
        probability_key, actual_key = spec.get("probability_key"), spec.get("actual_key")
        folds = []
        for index, block in enumerate(blocks, 1):
            test_set = set(block)
            items = [row for row in source if str(row.get("match_date")) in test_set]
            clean = []
            for row in items:
                p, y = row.get(probability_key), row.get(actual_key)
                if isinstance(p, Mapping):
                    try:
                        probs = {k: float(p[k]) for k in OUTCOMES_1X2}
                        if y not in OUTCOMES_1X2 or any(not math.isfinite(v) or v < 0 or v > 1 for v in probs.values()) or abs(sum(probs.values())-1) > 1e-5:
                            continue
                        clean.append((probs, str(y)))
                    except (KeyError, TypeError, ValueError):
                        continue
                else:
                    try:
                        probability, actual = float(p), int(y)
                        if not math.isfinite(probability) or not 0 <= probability <= 1 or actual not in (0,1):
                            continue
                        clean.append((probability, actual))
                    except (TypeError, ValueError):
                        continue
            training_count = sum(1 for row in source if str(row.get("match_date")) < block[0]
                                 and row.get(probability_key) is not None
                                 and row.get(actual_key) is not None)
            if training_count < minimum_training_matches or len(clean) < minimum_test_matches:
                folds.append({"fold": index, "status": "INSUFFICIENT_MATCHES",
                              "training_matches": training_count, "test_matches": len(clean)})
                continue
            if clean and isinstance(clean[0][0], dict):
                n = len(clean)
                brier = sum(sum((p[k]-float(y==k))**2 for k in OUTCOMES_1X2) for p,y in clean)/n
                loss = -sum(math.log(max(1e-15,p[y])) for p,y in clean)/n
                accuracy = sum(max(p,key=p.get)==y for p,y in clean)/n
                metrics = {"matches":n,"brier_score":brier,"log_loss":loss,"accuracy":accuracy}
            else:
                metrics = binary_market_metrics([{"probability":p,"actual":y} for p,y in clean])
            folds.append({"fold":index,"status":"EVALUATED","training_matches":training_count,
                          "test_matches":len(clean),"test_start":block[0],"test_end":block[-1],
                          "metrics":metrics})
        report["markets"][market] = {"folds":folds,
            "evaluated_folds":sum(f["status"]=="EVALUATED" for f in folds),
            "status":"EVALUATED" if any(f["status"]=="EVALUATED" for f in folds) else "INSUFFICIENT_MATCHES"}
    report["status"] = "EVALUATED" if any(v["evaluated_folds"] for v in report["markets"].values()) else "INSUFFICIENT_MATCHES"
    return report


def _date_blocks(values: list[str], count: int):
    """Yield up to count contiguous, non-overlapping date blocks."""
    if not values:
        return
    size = max(1, math.ceil(len(values) / count))
    for start in range(0, len(values), size):
        yield values[start:start+size]
