"""Frozen, date-safe Platt calibration for live BTTS and full-time totals probabilities.

Calibration coefficients are fitted only on the historical training window and
are applied to future fixtures. This module never changes 1X2 probabilities.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Mapping

MARKET_FIELDS = {
    "btts_yes": "btts_yes",
    "over_1_5": "over_1_5",
    "over_2_5": "over_2_5",
    "over_3_5": "over_3_5",
}


def _valid_probability(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and 0.0 <= number <= 1.0


def _platt(probability: float, intercept: float, slope: float) -> float:
    p = min(1.0 - 1e-6, max(1e-6, probability))
    logit = math.log(p / (1.0 - p))
    z = max(-700.0, min(700.0, intercept + slope * logit))
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def apply_goal_market_calibration(
    report: dict[str, Any],
    backtest_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the frozen chronological holdout calibrators to report forecasts."""
    live = backtest_report.get("live_pipeline") or {}
    goal = live.get("goal_markets") or {}
    experiment = goal.get("chronological_calibration_experiment") or {}
    rolling = goal.get("rolling_origin_calibration") or {}
    cutoff = str(experiment.get("calibration_cutoff_date") or "")
    calibrators: dict[str, tuple[float, float]] = {}
    failures: dict[str, str] = {}
    for market in MARKET_FIELDS:
        item = (experiment.get("markets") or {}).get(market) or {}
        rolling_item = (rolling.get("markets") or {}).get(market) or {}
        if (
            item.get("status") != "CALIBRATION_FIT_EVALUATED_ON_LATER_DATES"
            or item.get("improved_brier_and_log_loss") is not True
            or rolling_item.get("status") != "CALIBRATION_DIAGNOSTIC_PASS"
            or int(rolling_item.get("folds_evaluated") or 0) < 4
            or int((rolling_item.get("raw") or {}).get("matches") or 0) < 1000
            or int(item.get("calibration_matches") or 0) < 1000
            or int(item.get("test_matches") or 0) < 1000
        ):
            failures[market] = "Chronological holdout and four-fold rolling calibration requirements are not satisfied."
            continue
        try:
            intercept = float(item["platt_intercept"])
            slope = float(item["platt_slope"])
        except (KeyError, TypeError, ValueError):
            failures[market] = "Calibration coefficients are missing."
            continue
        if not math.isfinite(intercept) or not math.isfinite(slope):
            failures[market] = "Calibration coefficients are non-finite."
            continue
        calibrators[market] = (intercept, slope)

    if not cutoff:
        failures["cutoff_date"] = "Calibration training cutoff date is missing."
    dataset_provenance = backtest_report.get("dataset_provenance") or {}
    dataset_sha256 = dataset_provenance.get("sha256") if isinstance(dataset_provenance, Mapping) else None
    if not isinstance(dataset_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", dataset_sha256):
        failures["dataset_provenance"] = "A verified SHA-256 historical dataset fingerprint is required."
    canonical = {
        "cutoff": cutoff,
        "model_family": "experimental_recent_goals_poisson",
        "dataset_sha256": dataset_sha256,
        "coefficients": {key: list(value) for key, value in sorted(calibrators.items())},
    }
    version = "goal-platt-" + hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    predictions = report.get("predictions")
    applied: list[str] = []
    compatible_forecasts = 0
    applied_forecasts = 0
    if isinstance(predictions, list):
        for prediction in predictions:
            if not isinstance(prediction, dict):
                continue
            # The frozen coefficients were evaluated on the team-history
            # recent-goals Poisson model. Do not transfer them to a different
            # fallback model such as a competition-only prior.
            model_name = prediction.get("goal_markets_model") or prediction.get("model")
            if model_name != "experimental_recent_goals_poisson":
                continue
            raw_values = {}
            for market, field in MARKET_FIELDS.items():
                raw = prediction.get(field)
                if market not in calibrators or not _valid_probability(raw):
                    continue
                raw_values[field] = float(raw)
                intercept, slope = calibrators[market]
                prediction[field] = round(_platt(float(raw), intercept, slope), 6)
                if market not in applied:
                    applied.append(market)
            if raw_values:
                compatible_forecasts += 1
                applied_forecasts += 1
                existing = prediction.get("raw_goal_market_probabilities")
                if not isinstance(existing, dict):
                    prediction["raw_goal_market_probabilities"] = raw_values
                prediction["goal_market_calibration"] = {
                    "status": "APPLIED_PROSPECTIVELY",
                    "model_version": version,
                    "training_cutoff_date": cutoff,
                    "markets": sorted(raw_values),
                }
    complete = len(calibrators) == len(MARKET_FIELDS) and not failures
    applied_status = "APPLIED_PROSPECTIVELY" if complete and applied_forecasts > 0 else (
        "NO_COMPATIBLE_FORECASTS" if complete else "PARTIAL_OR_UNAVAILABLE"
    )
    report["goal_market_calibration"] = {
        "status": applied_status,
        "model_version": version if applied_status == "APPLIED_PROSPECTIVELY" else None,
        "training_cutoff_date": cutoff or None,
        "dataset_sha256": dataset_sha256,
        "markets": sorted(applied),
        "compatible_forecasts": compatible_forecasts,
        "applied_forecasts": applied_forecasts,
        "failures": failures,
        "training_method": experiment.get("method"),
        "note": "Frozen Platt coefficients were fitted before the later-date holdout and applied only to future report fixtures.",
    }
    return report
