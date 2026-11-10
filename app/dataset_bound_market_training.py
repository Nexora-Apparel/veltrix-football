"""Dataset-bound trainer for VELTRIX independent market models.

Only the validated chronological train split enters model fitting. Validation
and test rows are sealed into a manifest but never passed to the optimizer.
"""
from __future__ import annotations

import hashlib
import json

from app.chronological_training_dataset import (
    ChronologicalDatasetError,
    validate_chronological_training_dataset,
)
from app.independent_market_models import (
    FEATURES,
    ResultsModelError,
    bind_model_to_dataset,
    fit_independent_market_models,
)


class DatasetTrainingError(ValueError):
    pass


def _digest(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fixture_digest(rows: list[dict]) -> str:
    return _digest(sorted(row["fixture_id"] for row in rows))


def fit_models_from_chronological_dataset(*, dataset: dict, trained_at: str,
                                          epochs: int = 1200,
                                          learning_rate: float = 0.04,
                                          l2: float = 0.02) -> dict:
    """Fit separate 1X2, BTTS and O/U heads from train rows only."""
    try:
        integrity = validate_chronological_training_dataset(dataset)
    except ChronologicalDatasetError as exc:
        raise DatasetTrainingError(f"chronological_dataset_rejected:{exc}") from None
    if integrity.get("valid") is not True:
        raise DatasetTrainingError("chronological_dataset_not_valid")

    rows = dataset["rows"]
    partitions = {
        split: [row for row in rows if row["split"] == split]
        for split in ("train", "validation", "test")
    }
    if any(not partitions[split] for split in partitions):
        raise DatasetTrainingError("all_three_chronological_splits_required")

    train_rows = []
    for row in partitions["train"]:
        if set(row["predictors"]) != set(FEATURES):
            raise DatasetTrainingError(
                f"training_feature_schema_mismatch:{row['fixture_id']}"
            )
        provenance = row["label_provenance"]
        source_digest = _digest({
            "feature_snapshot_sha256": row["feature_snapshot_sha256"],
            "label_payload_sha256": provenance["payload_sha256"],
            "label_source": provenance["source"],
            "label_source_id": provenance["source_id"],
        })
        train_rows.append({
            "fixture_id": row["fixture_id"],
            "kickoff_at": row["kickoff_at"],
            "feature_as_of": row["prediction_as_of"],
            "settled_at": provenance["settled_at"],
            "features": row["predictors"],
            "market_targets": row["targets"],
            "source_record_sha256": source_digest,
        })

    train_end = dataset["split_policy"]["train_end_date"]
    # Africa/Lagos is UTC+01:00. The declared training cutoff is the final
    # second of the train window in local competition-reporting time.
    cutoff = f"{train_end}T23:59:59+01:00"
    try:
        model = fit_independent_market_models(
            training_rows=train_rows,
            training_cutoff_at=cutoff,
            trained_at=trained_at,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
        )
    except ResultsModelError as exc:
        raise DatasetTrainingError(f"market_model_fit_rejected:{exc}") from None

    manifest = {
        split: {
            "row_count": len(partitions[split]),
            "fixture_ids_sha256": _fixture_digest(partitions[split]),
        }
        for split in ("train", "validation", "test")
    }
    try:
        sealed = bind_model_to_dataset(
            model, dataset_sha256=integrity["dataset_sha256"],
            split_manifest=manifest,
        )
    except ResultsModelError as exc:
        raise DatasetTrainingError(f"model_dataset_binding_rejected:{exc}") from None
    return {
        "model": sealed,
        "training_audit": {
            "dataset_sha256": integrity["dataset_sha256"],
            "training_cutoff_at": sealed["training_cutoff_at"],
            "trained_at": sealed["trained_at"],
            "train_rows_used": len(train_rows),
            "validation_rows_held_out": len(partitions["validation"]),
            "test_rows_held_out": len(partitions["test"]),
            "validation_and_test_passed_to_optimizer": False,
            "calibration_performed": False,
            "publication_allowed": False,
            "value_betting_enabled": False,
            "database_writes": 0,
            "prediction_publications": 0,
        },
    }
