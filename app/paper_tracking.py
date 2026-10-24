"""Evaluate archived experimental forecasts against completed fixture results.

This is paper tracking only. It does not place bets or certify model quality.
"""
from __future__ import annotations

import math
from typing import Any

COMPLETED_STATUSES = {"FT", "AET", "PEN"}
OUTCOMES = ("H", "D", "A")


def evaluate_report(report: dict[str, Any], results_payload: dict[str, Any]) -> dict[str, Any]:
    """Score report forecasts matched by fixture ID to completed API results."""
    predictions = report.get("predictions")
    results = results_payload.get("response")
    if not isinstance(predictions, list):
        raise ValueError("Prediction report must contain a predictions list.")
    if not isinstance(results, list):
        raise ValueError("Results payload must contain a response list.")

    completed: dict[int, dict[str, Any]] = {}
    for item in results:
        fixture = item.get("fixture") or {}
        fixture_id = fixture.get("id")
        status = (fixture.get("status") or {}).get("short")
        goals = item.get("goals") or {}
        home, away = goals.get("home"), goals.get("away")
        if (
            isinstance(fixture_id, int)
            and status in COMPLETED_STATUSES
            and isinstance(home, int) and not isinstance(home, bool) and home >= 0
            and isinstance(away, int) and not isinstance(away, bool) and away >= 0
        ):
            completed[fixture_id] = {
                "status": status,
                "home_goals": home,
                "away_goals": away,
                "actual": "H" if home > away else "A" if home < away else "D",
            }

    scored: list[dict[str, Any]] = []
    awaiting_result = 0
    withheld = 0
    missing_fixture_id = 0
    for prediction in predictions:
        if prediction.get("status") != "EXPERIMENTAL_ONLY" or not isinstance(prediction.get("probabilities"), dict):
            withheld += 1
            continue
        fixture_id = prediction.get("fixture_id")
        if not isinstance(fixture_id, int):
            missing_fixture_id += 1
            continue
        result = completed.get(fixture_id)
        if result is None:
            awaiting_result += 1
            continue
        probs = prediction["probabilities"]
        try:
            values = {key: float(probs[key]) for key in OUTCOMES}
        except (KeyError, TypeError, ValueError):
            withheld += 1
            continue
        if (
            any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values())
            or abs(sum(values.values()) - 1.0) > 0.02
        ):
            withheld += 1
            continue
        actual = result["actual"]
        scored.append({
            "fixture_id": fixture_id,
            "home_team": prediction.get("home_team"),
            "away_team": prediction.get("away_team"),
            "actual": actual,
            "predicted": max(values, key=values.get),
            "probabilities": values,
            "correct": max(values, key=values.get) == actual,
            "home_goals": result["home_goals"],
            "away_goals": result["away_goals"],
        })

    count = len(scored)
    if count:
        brier = sum(
            sum((row["probabilities"][key] - float(row["actual"] == key)) ** 2 for key in OUTCOMES)
            for row in scored
        ) / count
        log_loss = sum(
            -math.log(max(1e-15, row["probabilities"][row["actual"]]))
            for row in scored
        ) / count
        accuracy = sum(row["correct"] for row in scored) / count
    else:
        brier = log_loss = accuracy = None

    return {
        "product": report.get("product", "Veltrix Football"),
        "report_date": report.get("as_of_date"),
        "model_status": "PAPER_TRACKING_ONLY",
        "predictions_in_report": len(predictions),
        "completed_forecasts_scored": count,
        "awaiting_result_or_match": awaiting_result,
        "withheld_or_invalid_forecasts": withheld,
        "forecasts_missing_fixture_id": missing_fixture_id,
        "metrics": {
            "result_accuracy": accuracy,
            "brier_score": brier,
            "log_loss": log_loss,
        },
        "matches": scored,
        "notice": "Retrospective paper evaluation only; no betting recommendation or profitability claim.",
    }
