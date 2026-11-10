"""Untouched chronological test-partition evaluator for calibrated models.

This produces diagnostic metrics only. It is not a full walk-forward run,
bookmaker benchmark, value-bet certification or publication authorization.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.chronological_training_dataset import (
    ChronologicalDatasetError,
    validate_chronological_training_dataset,
)
from app.independent_market_models import (
    MARKETS,
    ResultsModelError,
    predict_independent_markets,
)


class HeldoutEvaluationError(ValueError):
    pass


def _digest_fixture_ids(rows: list[dict]) -> str:
    raw = json.dumps(sorted(row["fixture_id"] for row in rows),
                     separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _time(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise HeldoutEvaluationError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HeldoutEvaluationError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HeldoutEvaluationError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _metrics(predictions: list[dict], labels: list[dict],
             baseline: dict) -> dict:
    output = {}
    for market, classes in MARKETS.items():
        model_brier = model_log_loss = baseline_brier = baseline_log_loss = 0.0
        correct = 0
        for probs, target in zip(predictions, labels):
            actual = target[market]
            model_choice = max(probs[market], key=probs[market].get)
            correct += model_choice == actual
            model_log_loss -= math.log(max(probs[market][actual], 1e-15))
            baseline_log_loss -= math.log(max(baseline[market][actual], 1e-15))
            for outcome in classes:
                observed = 1.0 if outcome == actual else 0.0
                model_brier += (probs[market][outcome] - observed) ** 2
                baseline_brier += (baseline[market][outcome] - observed) ** 2
        count = len(labels)
        output[market] = {
            "model": {
                "brier": model_brier / count,
                "log_loss": model_log_loss / count,
                "accuracy": correct / count,
            },
            "train_frequency_baseline": {
                "brier": baseline_brier / count,
                "log_loss": baseline_log_loss / count,
            },
            "beats_train_frequency_baseline": {
                "brier": model_brier < baseline_brier,
                "log_loss": model_log_loss < baseline_log_loss,
            },
        }
    return output


def evaluate_calibrated_model_on_test_partition(*, model: dict,
                                                dataset: dict,
                                                evaluated_at: str) -> dict:
    if model.get("calibration", {}).get("status") != "calibrated":
        raise HeldoutEvaluationError("calibrated_model_required")
    try:
        integrity = validate_chronological_training_dataset(dataset)
    except ChronologicalDatasetError as exc:
        raise HeldoutEvaluationError(f"dataset_rejected:{exc}") from None
    if model.get("training_dataset_sha256") != integrity["dataset_sha256"]:
        raise HeldoutEvaluationError("model_dataset_binding_mismatch")

    manifest = model.get("training_split_manifest")
    if not isinstance(manifest, dict) or set(manifest) != {"train", "validation", "test"}:
        raise HeldoutEvaluationError("model_split_manifest_invalid")
    partitions = {
        split: [row for row in dataset["rows"] if row["split"] == split]
        for split in ("train", "validation", "test")
    }
    for split, rows in partitions.items():
        expected = manifest[split]
        if (len(rows) != expected["row_count"]
                or _digest_fixture_ids(rows) != expected["fixture_ids_sha256"]):
            raise HeldoutEvaluationError(f"split_manifest_mismatch:{split}")
    test_rows = partitions["test"]
    if not test_rows:
        raise HeldoutEvaluationError("test_partition_empty")

    evaluation_time = _time(evaluated_at, "evaluated_at")
    predictions, labels = [], []
    test_dates = set()
    for row in test_rows:
        provenance = row["label_provenance"]
        if _time(provenance["retrieved_at"], "test_label_retrieved_at") > evaluation_time:
            raise HeldoutEvaluationError(
                f"test_label_retrieved_after_evaluation:{row['fixture_id']}"
            )
        kickoff = _time(row["kickoff_at"], "test_kickoff")
        test_dates.add(kickoff.astimezone(ZoneInfo("Africa/Lagos")).date())
        try:
            result = predict_independent_markets(
                model=model, features=row["predictors"],
                prediction_as_of=row["prediction_as_of"],
            )
        except ResultsModelError as exc:
            raise HeldoutEvaluationError(f"test_prediction_rejected:{exc}") from None
        predictions.append(result["probabilities"])
        labels.append(row["targets"])

    train_labels = [row["targets"] for row in partitions["train"]]
    baseline = {}
    for market, classes in MARKETS.items():
        counts = {outcome: 0 for outcome in classes}
        for row in train_labels:
            counts[row[market]] += 1
        total = len(train_labels)
        if total == 0:
            raise HeldoutEvaluationError("training_partition_empty")
        baseline[market] = {outcome: counts[outcome] / total for outcome in classes}

    metrics = _metrics(predictions, labels, baseline)
    evaluation_records_digest = hashlib.sha256(
        json.dumps([
            {
                "fixture_id": row["fixture_id"],
                "feature_snapshot_sha256": row["feature_snapshot_sha256"],
                "label_payload_sha256": row["label_provenance"]["payload_sha256"],
            }
            for row in test_rows
        ], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "evaluation_type": "single_chronological_heldout_test_partition",
        "model_sha256": model["model_sha256"],
        "dataset_sha256": integrity["dataset_sha256"],
        "test_records_sha256": evaluation_records_digest,
        "evaluated_at": evaluation_time.isoformat(),
        "test_fixture_count": len(test_rows),
        "test_distinct_wat_dates": len(test_dates),
        "metrics": metrics,
        "baseline_definition": "empirical_market_frequencies_from_train_partition",
        "bookmaker_comparison": "unavailable_timestamped_odds_not_supplied",
        "full_walk_forward_certified": False,
        "value_bet_certified": False,
        "publication_allowed": False,
        "side_effects": {
            "database_writes": 0,
            "prediction_publications": 0,
            "telegram_deliveries": 0,
        },
    }
