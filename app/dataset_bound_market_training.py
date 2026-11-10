"""Dataset-bound trainer entrypoint for independent market models.

Only the validated chronological train split is passed to the optimizer.
Validation and test partitions are represented in a sealed manifest and are
never passed to fitting. This module does not calibrate, publish or persist.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

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


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fixture_digest(rows: list[dict]) -> str:
    return _digest(sorted(row["fixture_id"] for row in rows))


def fit_models_from_chronological_dataset(*, dataset: dict, trained_at: str,
                                          epochs: int = 1200,
                                          learning_rate: float = 0.04,
                                          l2: float = 0.02) -> dict:
    """Fit three heads from the dataset's train partition only."""
    try:
        integrity = validate_chronological_training_dataset(dataset)
    except ChronologicalDatasetError as exc:
        raise DatasetTrainingError(f"chronological_dataset_rejected:{exc}") from None
    if integrity["valid"] is not True:
        raise DatasetTrainingError("chronological_dataset_not_valid")

    rows = dataset["rows"]
    train = [row for row in rows if row["split"] == "train"]
    validation = [row for row in rows if row["split"] == "validation"]
    test = [row for row in rows if row["split"] == "test"]
    if not train:
        raise DatasetTrainingError("training_split_empty")
    if not validation:
        raise DatasetTrainingError("validation_split_empty")
    if not test:
        raise DatasetTrainingError("test_split_empty")

    training_rows = []
    for index, row in enumerate(train):
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
        training_rows.append({
            "fixture_id": row["fixture_id"],
            "kickoff_at": row["kickoff_at"],
            "feature_as_of": row["prediction_as_of"],
            "settled_at": provenance["settled_at"],
            "features": row["predictors"],
            "home_score": _score_from_target_placeholder(row, "home"),
            "away_score": _score_from_target_placeholder(row, "away"),
            "source_record_sha256": source_digest,
        })

    # The chronological dataset deliberately stores market labels, not raw
    # scores. Recovering scorelines from those labels is impossible, so the
    # dataset contract must retain a separate, provenance-bound score label.
    # Refuse training until that explicit label extension is present.
    raise DatasetTrainingError(
        "dataset_scoreline_labels_required:chronological_dataset_v2"
    )


def _score_from_target_placeholder(row: dict, side: str) -> int:
    raise DatasetTrainingError("raw_scoreline_not_present_in_training_dataset")
