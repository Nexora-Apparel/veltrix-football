"""Experimental extensions for football probability modelling.

All functions are deterministic and dependency-light. Dixon-Coles is exposed as
an alternative forecast until chronological backtests justify promotion.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Iterable, Mapping


def recency_weighted_mean(values: Iterable[float], *, decay: float = 0.85) -> float:
    """Weighted mean of oldest-to-newest observations; newest receives weight 1."""
    if not 0 < decay <= 1:
        raise ValueError("decay must be in (0, 1]")
    items = [float(value) for value in values]
    if not items:
        raise ValueError("at least one observation is required")
    if any(not math.isfinite(value) for value in items):
        raise ValueError("observations must be finite")
    weights = [decay ** (len(items) - 1 - i) for i in range(len(items))]
    return sum(v * w for v, w in zip(items, weights)) / sum(weights)


def dixon_coles_1x2(
    home_xg: float, away_xg: float, *, rho: float = -0.05, max_goals: int = 12
) -> dict[str, float]:
    """Compute 1X2 probabilities using independent Poisson scores plus DC low-score correction.

    rho is deliberately explicit. Its default is a conservative research starting
    value, not a fitted parameter; tune it on training data only before promotion.
    """
    home_xg, away_xg, rho = float(home_xg), float(away_xg), float(rho)
    if not math.isfinite(home_xg) or home_xg < 0:
        raise ValueError("home_xg must be finite and non-negative")
    if not math.isfinite(away_xg) or away_xg < 0:
        raise ValueError("away_xg must be finite and non-negative")
    if not math.isfinite(rho) or not -0.25 <= rho <= 0.25:
        raise ValueError("rho must be finite and between -0.25 and 0.25")
    if isinstance(max_goals, bool) or not isinstance(max_goals, int) or not 1 <= max_goals <= 30:
        raise ValueError("max_goals must be an integer between 1 and 30")

    def pmf(lam: float) -> list[float]:
        values = [math.exp(-lam)]
        for goals in range(1, max_goals + 1):
            values.append(values[-1] * lam / goals)
        total = sum(values)
        return [v / total for v in values]

    home, away = pmf(home_xg), pmf(away_xg)
    result = {"H": 0.0, "D": 0.0, "A": 0.0}
    for hg, hp in enumerate(home):
        for ag, ap in enumerate(away):
            tau = 1.0
            if hg == 0 and ag == 0:
                tau = 1.0 - home_xg * away_xg * rho
            elif hg == 0 and ag == 1:
                tau = 1.0 + home_xg * rho
            elif hg == 1 and ag == 0:
                tau = 1.0 + away_xg * rho
            elif hg == 1 and ag == 1:
                tau = 1.0 - rho
            if tau < 0:
                raise ValueError("rho and expected goals produce a negative Dixon-Coles score probability")
            probability = hp * ap * tau
            result["H" if hg > ag else "A" if hg < ag else "D"] += probability
    total = sum(result.values())
    if total <= 0 or not math.isfinite(total):
        raise ValueError("Dixon-Coles probabilities could not be normalized")
    return {key: value / total for key, value in result.items()}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two validated venue coordinates."""
    import math
    values = (lat1, lon1, lat2, lon2)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("venue coordinates must be finite")
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        raise ValueError("venue coordinates are outside valid ranges")
    rad = math.pi / 180
    dlat, dlon = (lat2 - lat1) * rad, (lon2 - lon1) * rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))


def rest_congestion_context(
    matches: Iterable[Mapping[str, Any]],
    home_key: str,
    away_key: str,
    target_date: date,
    *,
    window_days: int = 14,
    target_venue_coordinates: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Measure rest/congestion and coordinate-backed travel using prior matches only.

    Travel is emitted only when both the prior match venue and target venue have
    valid coordinates. Missing coordinates remain explicitly unavailable.
    This context is not applied to probabilities until separately validated.
    """
    if isinstance(window_days, bool) or not isinstance(window_days, int) or window_days < 1:
        raise ValueError("window_days must be a positive integer")
    rows = list(matches)
    result: dict[str, dict[str, Any]] = {}
    for side, key in (("home", home_key), ("away", away_key)):
        previous = [
            row for row in rows
            if isinstance(row.get("date"), date)
            and row["date"] < target_date
            and key in (row.get("home_key"), row.get("away_key"))
        ]
        previous.sort(key=lambda row: row["date"])
        last = previous[-1] if previous else None
        last_date = last.get("date") if last else None
        counts = {
            f"matches_in_previous_{days}_days": sum(
                (target_date - row["date"]).days <= days for row in previous
            )
            for days in (7, 14, 30)
        }
        travel_km = None
        travel_status = "UNAVAILABLE_TARGET_VENUE_COORDINATES"
        if target_venue_coordinates is not None:
            travel_status = "UNAVAILABLE_PREVIOUS_VENUE_COORDINATES"
            if last is not None:
                try:
                    target_lat = float(target_venue_coordinates["latitude"])
                    target_lon = float(target_venue_coordinates["longitude"])
                    previous_lat = float(last["venue_latitude"])
                    previous_lon = float(last["venue_longitude"])
                    travel_km = _haversine_km(previous_lat, previous_lon, target_lat, target_lon)
                    travel_status = "VERIFIED_COORDINATE_DISTANCE"
                except (KeyError, TypeError, ValueError):
                    pass
        result[side] = {
            "days_since_last_match": (target_date - last_date).days if last_date else None,
            "matches_in_previous_7_days": counts["matches_in_previous_7_days"],
            "matches_in_previous_14_days": counts["matches_in_previous_14_days"],
            "matches_in_previous_30_days": counts["matches_in_previous_30_days"],
            "travel_distance_km": round(travel_km, 1) if travel_km is not None else None,
            "travel_status": travel_status,
        }
    return result


def blend_1x2(
    models: Mapping[str, Mapping[str, float]], weights: Mapping[str, float]
) -> dict[str, float]:
    """Blend already-calibrated 1X2 models; callers must validate weights out of sample."""
    if not models or set(models) != set(weights):
        raise ValueError("model and weight names must match and be non-empty")
    if any(not math.isfinite(float(w)) or float(w) < 0 for w in weights.values()):
        raise ValueError("weights must be finite and non-negative")
    if sum(float(w) for w in weights.values()) <= 0:
        raise ValueError("at least one model weight must be positive")
    combined = {key: 0.0 for key in ("H", "D", "A")}
    for name, probabilities in models.items():
        if set(probabilities) != {"H", "D", "A"}:
            raise ValueError(f"{name} must provide H, D, and A probabilities")
        vals = [float(probabilities[k]) for k in ("H", "D", "A")]
        if any(not math.isfinite(v) or v < 0 or v > 1 for v in vals) or abs(sum(vals) - 1.0) > 1e-6:
            raise ValueError(f"{name} probabilities must be valid and sum to one")
        for key in combined:
            combined[key] += float(weights[name]) * float(probabilities[key])
    total = sum(combined.values())
    return {key: value / total for key, value in combined.items()}
