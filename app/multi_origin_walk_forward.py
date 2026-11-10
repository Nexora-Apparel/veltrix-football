"""Multi-origin chronological walk-forward evaluation for VELTRIX.

Each origin receives a newly sealed chronological dataset. Training sees only
the origin's train window; calibration sees only its validation window; final
metrics see only its untouched future test window. This module is diagnostic:
it never authorizes publication or value betting.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.chronological_training_dataset import (
    ChronologicalDatasetError,
    validate_chronological_training_dataset,
)
from app.dataset_bound_market_training import (
    DatasetTrainingError,
    fit_models_from_chronological_dataset,
)
from app.heldout_market_evaluation import _metrics
from app.independent_market_models import MARKETS
from app.market_probability_calibration import (
    MarketCalibrationError,
    calibrate_model_on_validation_split,
)


class WalkForwardEvaluationError(ValueError):
    pass


ZONE = ZoneInfo("Africa/Lagos")
MIN_ORIGINS = 2
BOOTSTRAP_REPLICATES = 1000


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_time(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise WalkForwardEvaluationError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise WalkForwardEvaluationError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WalkForwardEvaluationError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _local_day(row: dict) -> date:
    return _parse_time(row["kickoff_at"], "kickoff_at").astimezone(ZONE).date()


def _validate_origin(origin: dict, index: int, embargo_days: int) -> dict:
    required = {"origin_id", "train_end_date", "validation_start_date",
                "validation_end_date", "test_start_date", "test_end_date"}
    if not isinstance(origin, dict) or set(origin) != required:
        raise WalkForwardEvaluationError(f"origin_shape_invalid:{index}")
    if not isinstance(origin["origin_id"], str) or not origin["origin_id"].strip():
        raise WalkForwardEvaluationError(f"origin_id_invalid:{index}")
    try:
        dates = {key: date.fromisoformat(origin[key]) for key in required
                 if key != "origin_id"}
    except (TypeError, ValueError):
        raise WalkForwardEvaluationError(f"origin_dates_invalid:{index}") from None
    train_end = dates["train_end_date"]
    val_start, val_end = dates["validation_start_date"], dates["validation_end_date"]
    test_start, test_end = dates["test_start_date"], dates["test_end_date"]
    if (val_start <= train_end or val_end < val_start or test_start <= val_end
            or test_end < test_start):
        raise WalkForwardEvaluationError(f"origin_windows_not_chronological:{index}")
    if ((val_start - train_end).days <= embargo_days
            or (test_start - val_end).days <= embargo_days):
        raise WalkForwardEvaluationError(f"origin_embargo_violation:{index}")
    return {"origin_id": origin["origin_id"], **{
        key: value.isoformat() for key, value in dates.items()
    }}


def _sealed_origin_dataset(dataset: dict, origin: dict, embargo_days: int) -> dict:
    selected = []
    counts = {"train": 0, "validation": 0, "test": 0}
    for original in dataset["rows"]:
        day = _local_day(original)
        split = None
        if day <= date.fromisoformat(origin["train_end_date"]):
            split = "train"
        elif date.fromisoformat(origin["validation_start_date"]) <= day <= date.fromisoformat(origin["validation_end_date"]):
            split = "validation"
        elif date.fromisoformat(origin["test_start_date"]) <= day <= date.fromisoformat(origin["test_end_date"]):
            split = "test"
        if split:
            row = dict(original)
            row["split"] = split
            selected.append(row)
            counts[split] += 1
    if any(counts[name] == 0 for name in counts):
        raise WalkForwardEvaluationError(
            f"origin_partition_empty:{origin['origin_id']}:{counts}"
        )
    policy = {
        "timezone": "Africa/Lagos",
        "train_end_date": origin["train_end_date"],
        "validation_start_date": origin["validation_start_date"],
        "validation_end_date": origin["validation_end_date"],
        "test_start_date": origin["test_start_date"],
        "test_end_date": origin["test_end_date"],
        "embargo_days": embargo_days,
    }
    quality = copy.deepcopy(dataset["quality"])
    quality["included_fixture_count"] = len(selected)
    quality["counts_by_split"] = counts
    quality["chronological_order"] = True
    quality["fixture_overlap_between_splits"] = False
    quality["target_labels_separate_from_predictors"] = True
    quality["counts_by_competition_and_split"] = {}
    for row in selected:
        comp = row["competition_key"]
        quality["counts_by_competition_and_split"].setdefault(
            comp, {"train": 0, "validation": 0, "test": 0}
        )[row["split"]] += 1
    origin_dataset = {
        "schema_version": dataset["schema_version"],
        "dataset_type": dataset["dataset_type"],
        "split_policy": policy,
        "rows": sorted(selected, key=lambda row: (row["kickoff_at"], row["fixture_id"])),
        "excluded": [],
        "quality": quality,
        "training_readiness": {
            "ready_for_model_training": False,
            "reason": "Walk-forward origin slice; source completeness and release gates remain independently unverified",
        },
        "side_effects": {
            "database_writes": 0,
            "model_training_runs": 0,
            "prediction_publications": 0,
        },
    }
    origin_dataset["dataset_sha256"] = _canonical_hash(origin_dataset)
    try:
        validate_chronological_training_dataset(origin_dataset)
    except ChronologicalDatasetError as exc:
        raise WalkForwardEvaluationError(
            f"origin_dataset_rejected:{origin['origin_id']}:{exc}"
        ) from None
    return origin_dataset


def _post_retrieval_timestamp(rows: list[dict], field: str) -> datetime:
    latest = max(_parse_time(row["label_provenance"]["retrieved_at"], field)
                 for row in rows)
    return latest + timedelta(microseconds=1)


def _metric_values(rows: list[dict], model: dict) -> list[dict]:
    from app.independent_market_models import predict_independent_markets, ResultsModelError
    output = []
    for row in rows:
        try:
            result = predict_independent_markets(
                model=model, features=row["predictors"],
                prediction_as_of=row["prediction_as_of"],
            )
        except ResultsModelError as exc:
            raise WalkForwardEvaluationError(
                f"test_prediction_rejected:{row['fixture_id']}:{exc}"
            ) from None
        output.append({
            "fixture_id": row["fixture_id"],
            "competition_key": row["competition_key"],
            "wat_date": _local_day(row).isoformat(),
            "probabilities": result["probabilities"],
            "targets": row["targets"],
        })
    return output


def _cluster_bootstrap(rows: list[dict], market: str, metric: str,
                       seed: int) -> dict:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["wat_date"]].append(row)
    dates = sorted(grouped)
    if len(dates) < 2:
        return {"lower_95": None, "upper_95": None,
                "distinct_dates": len(dates), "method": "date_cluster_bootstrap",
                "replicates": 0, "status": "insufficient_dates"}
    rng = random.Random(seed)
    estimates = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled_dates = [rng.choice(dates) for _ in dates]
        sample = [row for day in sampled_dates for row in grouped[day]]
        total = 0.0
        for row in sample:
            probs, actual = row["probabilities"][market], row["targets"][market]
            if metric == "log_loss":
                total -= math.log(max(probs[actual], 1e-15))
            else:
                total += sum(
                    (probability - (1.0 if outcome == actual else 0.0)) ** 2
                    for outcome, probability in probs.items()
                )
        estimates.append(total / len(sample))
    estimates.sort()
    return {
        "lower_95": estimates[int(0.025 * (len(estimates) - 1))],
        "upper_95": estimates[int(0.975 * (len(estimates) - 1))],
        "distinct_dates": len(dates),
        "method": "date_cluster_percentile_bootstrap",
        "replicates": BOOTSTRAP_REPLICATES,
        "status": "diagnostic_only",
    }


def _group_metrics(rows: list[dict], group_key: str, digest: str) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[row[group_key]].append(row)
    result = {}
    for group, members in sorted(groups.items()):
        predictions = [row["probabilities"] for row in members]
        labels = [row["targets"] for row in members]
        # A training-frequency baseline is calculated outside this helper and
        # attached by the caller; this helper reports model-only metrics.
        metrics = {}
        for market, classes in MARKETS.items():
            brier = log_loss = correct = 0.0
            for probs, target in zip(predictions, labels):
                actual = target[market]
                log_loss -= math.log(max(probs[market][actual], 1e-15))
                correct += max(probs[market], key=probs[market].get) == actual
                brier += sum(
                    (probs[market][outcome] - (1.0 if outcome == actual else 0.0)) ** 2
                    for outcome in classes
                )
            metrics[market] = {
                "fixture_count": len(members),
                "distinct_wat_dates": len({row["wat_date"] for row in members}),
                "brier": brier / len(members),
                "log_loss": log_loss / len(members),
                "accuracy": correct / len(members),
                "brier_ci_95": _cluster_bootstrap(
                    members, market, "brier", int(hashlib.sha256((digest + ":" + group + ":" + market + ":brier").encode()).hexdigest()[:8], 16)
                ),
                "log_loss_ci_95": _cluster_bootstrap(
                    members, market, "log_loss", int(hashlib.sha256((digest + ":" + group + ":" + market + ":logloss").encode()).hexdigest()[:8], 16)
                ),
            }
        result[group] = metrics
    return result


def evaluate_multi_origin_walk_forward(*, dataset: dict, origins: list[dict],
                                       embargo_days: int = 7,
                                       epochs: int = 1200,
                                       learning_rate: float = 0.04,
                                       l2: float = 0.02) -> dict:
    """Run independent train/calibrate/test cycles over chronological origins."""
    try:
        source_integrity = validate_chronological_training_dataset(dataset)
    except ChronologicalDatasetError as exc:
        raise WalkForwardEvaluationError(f"source_dataset_rejected:{exc}") from None
    if not isinstance(origins, list) or len(origins) < MIN_ORIGINS:
        raise WalkForwardEvaluationError("at_least_two_walk_forward_origins_required")
    if (isinstance(embargo_days, bool) or not isinstance(embargo_days, int)
            or not 0 <= embargo_days <= 90):
        raise WalkForwardEvaluationError("embargo_days_invalid")
    normalized = [_validate_origin(item, i, embargo_days)
                  for i, item in enumerate(origins)]
    if len({item["origin_id"] for item in normalized}) != len(normalized):
        raise WalkForwardEvaluationError("duplicate_origin_id")
    normalized.sort(key=lambda item: item["test_start_date"])
    for previous, current in zip(normalized, normalized[1:]):
        if current["test_start_date"] <= previous["test_end_date"]:
            raise WalkForwardEvaluationError("walk_forward_test_windows_overlap")

    origin_reports, all_test_records = [], []
    for origin in normalized:
        origin_dataset = _sealed_origin_dataset(dataset, origin, embargo_days)
        train = [row for row in origin_dataset["rows"] if row["split"] == "train"]
        validation = [row for row in origin_dataset["rows"] if row["split"] == "validation"]
        test = [row for row in origin_dataset["rows"] if row["split"] == "test"]
        latest_train_retrieval = _post_retrieval_timestamp(train, "train_label_retrieved_at")
        train_cutoff = datetime.fromisoformat(origin["train_end_date"] + "T23:59:59+01:00").astimezone(timezone.utc) + timedelta(microseconds=1)
        trained_at = max(latest_train_retrieval, train_cutoff)
        validation_start = datetime.fromisoformat(
            origin["validation_start_date"] + "T00:00:00+01:00"
        ).astimezone(timezone.utc)
        if trained_at >= validation_start:
            raise WalkForwardEvaluationError(
                f"training_data_not_available_before_validation:{origin['origin_id']}"
            )
        fitted = fit_models_from_chronological_dataset(
            dataset=origin_dataset, trained_at=trained_at.isoformat(),
            epochs=epochs, learning_rate=learning_rate, l2=l2,
        )
        calibrated_at = _post_retrieval_timestamp(validation, "validation_label_retrieved_at")
        test_start = datetime.fromisoformat(
            origin["test_start_date"] + "T00:00:00+01:00"
        ).astimezone(timezone.utc)
        if calibrated_at >= test_start:
            raise WalkForwardEvaluationError(
                f"validation_calibration_not_available_before_test:{origin['origin_id']}"
            )
        try:
            calibrated = calibrate_model_on_validation_split(
                model=fitted["model"], dataset=origin_dataset,
                calibrated_at=calibrated_at.isoformat(),
            )
        except MarketCalibrationError as exc:
            raise WalkForwardEvaluationError(
                f"origin_calibration_failed:{origin['origin_id']}:{exc}"
            ) from None
        test_retrieval = _post_retrieval_timestamp(test, "test_label_retrieved_at")
        records = _metric_values(test, calibrated["model"])
        all_test_records.extend(records)
        train_labels = [row["targets"] for row in train]
        baseline = {}
        for market, classes in MARKETS.items():
            counts = {outcome: 0 for outcome in classes}
            for row in train_labels:
                counts[row[market]] += 1
            baseline[market] = {outcome: counts[outcome] / len(train_labels)
                                for outcome in classes}
        origin_report = _metrics(
            [row["probabilities"] for row in records],
            [row["targets"] for row in records], baseline,
        )
        origin_reports.append({
            "origin_id": origin["origin_id"],
            "origin_dataset_sha256": origin_dataset["dataset_sha256"],
            "model_sha256": calibrated["model"]["model_sha256"],
            "training_cutoff_at": fitted["model"]["training_cutoff_at"],
            "trained_at": trained_at.isoformat(),
            "calibrated_at": calibrated_at.isoformat(),
            "evaluated_at": test_retrieval.isoformat(),
            "counts": {"train": len(train), "validation": len(validation),
                       "test": len(test)},
            "validation_rows_used_for_calibration": len(validation),
            "training_rows_used_for_calibration": 0,
            "test_rows_used_for_calibration": 0,
            "metrics": origin_report,
            "test_records_sha256": _canonical_hash([
                {"fixture_id": row["fixture_id"],
                 "targets": row["targets"], "probabilities": row["probabilities"]}
                for row in records
            ]),
        })

    report_digest = _canonical_hash({
        "source_dataset_sha256": source_integrity["dataset_sha256"],
        "origins": [item["origin_id"] for item in normalized],
        "records": [{"fixture_id": row["fixture_id"],
                     "origin": row.get("origin_id"),
                     "wat_date": row["wat_date"]} for row in all_test_records],
    })
    # Include origin identity in pooled records to prevent accidental ambiguity
    # when a fixture is tested in more than one expanding-window origin.
    pooled = []
    for report, origin in zip(origin_reports, normalized):
        for row in all_test_records:
            # Per-origin metrics remain authoritative; pooled rows are added
            # below from the source test window, scoped by origin dates.
            day = date.fromisoformat(row["wat_date"])
            if (date.fromisoformat(origin["test_start_date"]) <= day
                    <= date.fromisoformat(origin["test_end_date"])):
                copy_row = dict(row)
                copy_row["origin_id"] = origin["origin_id"]
                pooled.append(copy_row)
    pooled_digest = _canonical_hash([
        {"origin_id": row["origin_id"], "fixture_id": row["fixture_id"],
         "probabilities": row["probabilities"], "targets": row["targets"]}
        for row in pooled
    ])
    return {
        "schema_version": 1,
        "evaluation_type": "multi_origin_chronological_walk_forward",
        "source_dataset_sha256": source_integrity["dataset_sha256"],
        "origin_count": len(origin_reports),
        "origins": origin_reports,
        "pooled_test_fixture_count": len(pooled),
        "per_competition": _group_metrics(pooled, "competition_key", pooled_digest),
        "per_origin": _group_metrics(pooled, "origin_id", pooled_digest),
        "test_records_sha256": pooled_digest,
        "full_walk_forward_certified": False,
        "value_bet_certified": False,
        "publication_allowed": False,
        "side_effects": {
            "database_writes": 0,
            "prediction_publications": 0,
            "telegram_deliveries": 0,
        },
    }
