"""Evaluate archived experimental forecasts against completed fixture results.

This is paper tracking only. It does not place bets or certify model quality.
"""
from __future__ import annotations

import math
from typing import Any

COMPLETED_STATUSES = {"FT", "AET", "PEN"}
OUTCOMES = ("H", "D", "A")


def summarize_scored_matches(matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate proper scoring metrics over already validated forecast/result pairs."""
    count = len(matches)
    if not count:
        return {"matches": 0, "result_accuracy": None, "brier_score": None, "log_loss": None}
    brier = 0.0
    log_loss = 0.0
    correct = 0
    for row in matches:
        probabilities = row["probabilities"]
        actual = row["actual"]
        brier += sum(
            (float(probabilities[key]) - float(actual == key)) ** 2
            for key in OUTCOMES
        )
        log_loss += -math.log(max(1e-15, float(probabilities[actual])))
        correct += int(row.get("correct", max(probabilities, key=probabilities.get) == actual))
    return {
        "matches": count,
        "result_accuracy": correct / count,
        "brier_score": brier / count,
        "log_loss": log_loss / count,
    }


def merge_paper_ledger(ledger: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    """Add one report-date evaluation idempotently and recompute cumulative metrics."""
    current = dict(ledger)
    current.setdefault("evaluations", [])
    current.setdefault("scored_matches", [])
    report_date = evaluation.get("report_date")
    if not report_date:
        raise ValueError("Evaluation must include a report_date.")
    already_recorded = any(row.get("report_date") == report_date for row in current["evaluations"])
    if not already_recorded:
        current["evaluations"].append({
            "report_date": report_date,
            "completed_forecasts_scored": evaluation.get("completed_forecasts_scored", 0),
            "awaiting_result_or_match": evaluation.get("awaiting_result_or_match", 0),
            "withheld_or_invalid_forecasts": evaluation.get("withheld_or_invalid_forecasts", 0),
            "metrics": evaluation.get("metrics", {}),
        })
        for match in evaluation.get("matches", []):
            current["scored_matches"].append({**match, "report_date": report_date})
    # A report-date + fixture ID pair is the stable identity for ledger rows.
    unique: dict[tuple[str, int], dict[str, Any]] = {}
    for row in current["scored_matches"]:
        try:
            key = (str(row["report_date"]), int(row["fixture_id"]))
        except (KeyError, TypeError, ValueError):
            continue
        unique[key] = row
    current["scored_matches"] = list(unique.values())
    current["product"] = "Veltrix Football"
    current["model_status"] = "PAPER_TRACKING_ONLY"
    current["cumulative_metrics"] = summarize_scored_matches(current["scored_matches"])
    current["evaluated_report_dates"] = len(current["evaluations"])
    current["notice"] = "Retrospective paper evaluation only; no betting recommendation or profitability claim."
    return current


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

    metrics = summarize_scored_matches(scored)
    count = metrics["matches"]

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
            "result_accuracy": metrics["result_accuracy"],
            "brier_score": metrics["brier_score"],
            "log_loss": metrics["log_loss"],
        },
        "matches": scored,
        "notice": "Retrospective paper evaluation only; no betting recommendation or profitability claim.",
    }
