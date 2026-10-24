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
    evaluation_summary = {
        "report_date": report_date,
        "completed_forecasts_scored": evaluation.get("completed_forecasts_scored", 0),
        "awaiting_result_or_match": evaluation.get("awaiting_result_or_match", 0),
        "withheld_or_invalid_forecasts": evaluation.get("withheld_or_invalid_forecasts", 0),
        "metrics": evaluation.get("metrics", {}),
        "metrics_by_model": evaluation.get("metrics_by_model", {}),
        "model_versions": sorted({str(row.get("model", "unknown")) for row in evaluation.get("matches", [])}),
    }
    existing_index = next(
        (index for index, row in enumerate(current["evaluations"])
         if row.get("report_date") == report_date),
        None,
    )
    if existing_index is None:
        current["evaluations"].append(evaluation_summary)
        should_merge_matches = True
    else:
        previous_pending = int(current["evaluations"][existing_index].get("awaiting_result_or_match", 0))
        should_merge_matches = previous_pending > 0
        if should_merge_matches:
            current["evaluations"][existing_index] = evaluation_summary
    # Pending report dates can be re-evaluated as postponed fixtures finish;
    # match-level deduplication below prevents duplicate scores.
    if should_merge_matches:
        for match in evaluation.get("matches", []):
            current["scored_matches"].append({**match, "report_date": report_date})
    # A report-date + fixture ID pair is the stable identity for ledger rows.
    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in current["scored_matches"]:
        try:
            key = (str(row["report_date"]), int(row["fixture_id"]), str(row.get("model", "unknown")))
        except (KeyError, TypeError, ValueError):
            continue
        unique[key] = row
    current["scored_matches"] = list(unique.values())
    current["product"] = "Veltrix Football"
    current["model_status"] = "PAPER_TRACKING_ONLY"
    model_names = sorted({str(row.get("model", "unknown")) for row in current["scored_matches"]})
    current["cumulative_metrics_by_model"] = {
        model_name: summarize_scored_matches([
            row for row in current["scored_matches"]
            if str(row.get("model", "unknown")) == model_name
        ])
        for model_name in model_names
    }
    # Do not publish one combined score as if it described a single model when
    # the ledger contains forecasts from different model versions.
    current["cumulative_metrics"] = (
        current["cumulative_metrics_by_model"][model_names[0]]
        if len(model_names) == 1
        else summarize_scored_matches(current["scored_matches"]) if not model_names
        else None
    )
    current["model_versions"] = model_names
    current["evaluated_report_dates"] = len(current["evaluations"])
    current["notice"] = "Retrospective paper evaluation only; no betting recommendation or profitability claim."
    return current


def _canonical_probabilities(probabilities: Any) -> dict[str, float] | None:
    if not isinstance(probabilities, dict):
        return None
    try:
        if all(key in probabilities for key in OUTCOMES):
            values = {key: float(probabilities[key]) for key in OUTCOMES}
        else:
            values = {
                "H": float(probabilities["home_win"]),
                "D": float(probabilities["draw"]),
                "A": float(probabilities["away_win"]),
            }
    except (KeyError, TypeError, ValueError):
        return None
    total = sum(values.values())
    if (
        any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values())
        or total <= 0
        or abs(total - 1.0) > 0.02
    ):
        return None
    # Rounded production probabilities may sum to 0.9999 or 1.0001. Normalize
    # small rounding drift so Brier score and log loss use a proper distribution.
    return {key: value / total for key, value in values.items()}


def evaluate_report(report: dict[str, Any], results_payload: dict[str, Any]) -> dict[str, Any]:
    """Score every available model forecast by fixture ID against completed results."""
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
    fixtures_scored: set[int] = set()
    for prediction in predictions:
        if prediction.get("status") != "EXPERIMENTAL_ONLY":
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

        forecast_models: list[tuple[str, Any]] = [
            (str(prediction.get("model", "unknown")), prediction.get("probabilities"))
        ]
        # Support both report layouts: Poisson primary + Elo alternative, or
        # competition Elo primary + Poisson alternative.
        if isinstance(prediction.get("elo_probabilities"), dict):
            forecast_models.append((
                str(prediction.get("elo_model", "experimental_elo_unknown")),
                prediction.get("elo_probabilities"),
            ))
        if isinstance(prediction.get("poisson_probabilities"), dict):
            forecast_models.append((
                str(prediction.get("poisson_model", "experimental_poisson_unknown")),
                prediction.get("poisson_probabilities"),
            ))
        scored_this_fixture = False
        for model_name, raw_probabilities in forecast_models:
            values = _canonical_probabilities(raw_probabilities)
            if values is None:
                withheld += 1
                continue
            actual = result["actual"]
            scored.append({
                "fixture_id": fixture_id,
                "model": model_name,
                "home_team": prediction.get("home_team"),
                "away_team": prediction.get("away_team"),
                "actual": actual,
                "predicted": max(values, key=values.get),
                "probabilities": values,
                "correct": max(values, key=values.get) == actual,
                "home_goals": result["home_goals"],
                "away_goals": result["away_goals"],
            })
            scored_this_fixture = True
        if scored_this_fixture:
            fixtures_scored.add(fixture_id)

    metrics_by_model = {
        model_name: summarize_scored_matches([
            row for row in scored if row["model"] == model_name
        ])
        for model_name in sorted({row["model"] for row in scored})
    }
    metrics = (
        next(iter(metrics_by_model.values())) if len(metrics_by_model) == 1
        else None if len(metrics_by_model) > 1
        else summarize_scored_matches([])
    )

    return {
        "product": report.get("product", "Veltrix Football"),
        "report_date": report.get("as_of_date"),
        "model_status": "PAPER_TRACKING_ONLY",
        "predictions_in_report": len(predictions),
        "fixtures_scored": len(fixtures_scored),
        "unique_fixtures_scored": len(fixtures_scored),
        "completed_forecasts_scored": len(scored),
        "awaiting_result_or_match": awaiting_result,
        "withheld_or_invalid_forecasts": withheld,
        "forecasts_missing_fixture_id": missing_fixture_id,
        "metrics": metrics,
        "metrics_by_model": metrics_by_model,
        "matches": scored,
        "notice": "Retrospective paper evaluation only; no betting recommendation or profitability claim.",
    }
