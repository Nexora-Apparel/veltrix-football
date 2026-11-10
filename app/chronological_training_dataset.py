"""Leakage-safe chronological dataset assembly for settled football fixtures.

This module joins pre-match point-in-time feature snapshots to separately
sourced settled labels. It performs no model training or prediction.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.point_in_time_feature_contract import (
    FEATURE_CATALOGUE,
    FORBIDDEN_FEATURE_NAMES,
    PointInTimeFeatureError,
    validate_point_in_time_feature_snapshot,
)


class ChronologicalDatasetError(ValueError):
    pass


def _hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ChronologicalDatasetError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ChronologicalDatasetError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChronologicalDatasetError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _split_policy(policy: Any) -> dict:
    if not isinstance(policy, dict):
        raise ChronologicalDatasetError("split_policy_invalid")
    try:
        train_end = date.fromisoformat(policy["train_end_date"])
        val_start = date.fromisoformat(policy["validation_start_date"])
        val_end = date.fromisoformat(policy["validation_end_date"])
        test_start = date.fromisoformat(policy["test_start_date"])
        test_end = date.fromisoformat(policy["test_end_date"])
        embargo = policy.get("embargo_days", 7)
    except (KeyError, TypeError, ValueError):
        raise ChronologicalDatasetError("split_policy_dates_invalid") from None
    if isinstance(embargo, bool) or not isinstance(embargo, int) or not 0 <= embargo <= 90:
        raise ChronologicalDatasetError("embargo_days_invalid")
    if (val_start <= train_end or val_end < val_start or test_start <= val_end
            or test_end < test_start):
        raise ChronologicalDatasetError("split_windows_not_strictly_chronological")
    if (val_start - train_end).days <= embargo or (test_start - val_end).days <= embargo:
        raise ChronologicalDatasetError("split_embargo_not_respected")
    return {
        "timezone": "Africa/Lagos",
        "train_end_date": train_end.isoformat(),
        "validation_start_date": val_start.isoformat(),
        "validation_end_date": val_end.isoformat(),
        "test_start_date": test_start.isoformat(),
        "test_end_date": test_end.isoformat(),
        "embargo_days": embargo,
    }


def assemble_chronological_training_dataset(*, snapshots: list[dict],
                                            settled_labels: list[dict],
                                            split_policy: dict) -> dict:
    if not isinstance(snapshots, list) or not isinstance(settled_labels, list):
        raise ChronologicalDatasetError("snapshots_and_labels_must_be_arrays")
    policy = _split_policy(split_policy)
    zone = ZoneInfo("Africa/Lagos")
    snapshot_by_id = {}
    for index, snapshot in enumerate(snapshots):
        try:
            integrity = validate_point_in_time_feature_snapshot(snapshot)
        except (PointInTimeFeatureError, TypeError, KeyError) as exc:
            raise ChronologicalDatasetError(f"feature_snapshot_invalid:{index}:{str(exc)[:100]}") from None
        fixture_id = snapshot["fixture_id"]
        if fixture_id in snapshot_by_id:
            raise ChronologicalDatasetError(f"duplicate_feature_snapshot:{fixture_id}")
        if integrity["feature_count"] == 0:
            raise ChronologicalDatasetError(f"empty_feature_snapshot:{fixture_id}")
        snapshot_by_id[fixture_id] = snapshot

    label_by_id = {}
    for index, label in enumerate(settled_labels):
        if not isinstance(label, dict):
            raise ChronologicalDatasetError(f"settled_label_invalid:{index}")
        required = {
            "fixture_id", "competition_key", "kickoff_at", "settled_at",
            "home_score", "away_score", "label_source", "label_source_id",
            "label_retrieved_at", "payload_sha256",
        }
        if set(label) != required:
            raise ChronologicalDatasetError(f"settled_label_shape_invalid:{index}")
        fixture_id = label.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ChronologicalDatasetError(f"settled_label_fixture_id_invalid:{index}")
        if fixture_id in label_by_id:
            raise ChronologicalDatasetError(f"duplicate_settled_label:{fixture_id}")
        if not isinstance(label.get("competition_key"), str) or not label["competition_key"].strip():
            raise ChronologicalDatasetError(f"settled_label_competition_invalid:{fixture_id}")
        for field in ("label_source", "label_source_id"):
            if not isinstance(label.get(field), str) or not label[field].strip():
                raise ChronologicalDatasetError(f"settled_label_{field}_invalid:{fixture_id}")
        payload_hash = label.get("payload_sha256")
        if (not isinstance(payload_hash, str) or len(payload_hash) != 64
                or any(char not in "0123456789abcdef" for char in payload_hash)):
            raise ChronologicalDatasetError(f"settled_label_payload_hash_invalid:{fixture_id}")
        kickoff = _time(label.get("kickoff_at"), f"{fixture_id}_kickoff")
        settled = _time(label.get("settled_at"), f"{fixture_id}_settled_at")
        retrieved = _time(label.get("label_retrieved_at"), f"{fixture_id}_label_retrieved_at")
        if settled <= kickoff or retrieved < settled:
            raise ChronologicalDatasetError(f"settled_label_temporal_order_invalid:{fixture_id}")
        home, away = label.get("home_score"), label.get("away_score")
        if (isinstance(home, bool) or not isinstance(home, int) or home < 0
                or isinstance(away, bool) or not isinstance(away, int) or away < 0):
            raise ChronologicalDatasetError(f"settled_label_score_invalid:{fixture_id}")
        label_by_id[fixture_id] = {
            **label,
            "_kickoff_utc": kickoff,
            "_kickoff_local_date": kickoff.astimezone(zone).date(),
            "_settled_at_utc": settled,
            "_retrieved_at_utc": retrieved,
        }

    if set(snapshot_by_id) != set(label_by_id):
        missing_labels = sorted(set(snapshot_by_id) - set(label_by_id))
        missing_snapshots = sorted(set(label_by_id) - set(snapshot_by_id))
        raise ChronologicalDatasetError(
            f"snapshot_label_join_not_one_to_one:missing_labels={len(missing_labels)}:"
            f"missing_snapshots={len(missing_snapshots)}"
        )

    rows = []
    excluded = []
    split_counts = Counter()
    competition_counts = defaultdict(Counter)
    market_counts = defaultdict(lambda: defaultdict(Counter))
    for fixture_id in sorted(snapshot_by_id):
        snapshot = snapshot_by_id[fixture_id]
        label = label_by_id[fixture_id]
        kickoff = label["_kickoff_utc"]
        cutoff = _time(snapshot["prediction_as_of"], f"{fixture_id}_prediction_as_of")
        if cutoff >= kickoff:
            raise ChronologicalDatasetError(f"prediction_cutoff_not_before_kickoff:{fixture_id}")
        if label["competition_key"] == "":
            raise ChronologicalDatasetError(f"competition_key_missing:{fixture_id}")
        local_day = label["_kickoff_local_date"]
        if local_day <= date.fromisoformat(policy["train_end_date"]):
            split = "train"
        elif date.fromisoformat(policy["validation_start_date"]) <= local_day <= date.fromisoformat(policy["validation_end_date"]):
            split = "validation"
        elif date.fromisoformat(policy["test_start_date"]) <= local_day <= date.fromisoformat(policy["test_end_date"]):
            split = "test"
        else:
            split = "embargo_or_out_of_window"
        if split == "embargo_or_out_of_window":
            excluded.append({"fixture_id": fixture_id, "reason": "outside_declared_split_windows"})
            continue

        home, away = label["home_score"], label["away_score"]
        targets = {
            "1x2": "home" if home > away else "away" if away > home else "draw",
            "btts": "yes" if home > 0 and away > 0 else "no",
            "over_2_5": "yes" if home + away > 2 else "no",
        }
        predictors = {feature["name"]: feature["value"] for feature in snapshot["features"]}
        rows.append({
            "fixture_id": fixture_id,
            "competition_key": label["competition_key"],
            "kickoff_at": kickoff.isoformat().replace("+00:00", "Z"),
            "prediction_as_of": cutoff.isoformat().replace("+00:00", "Z"),
            "feature_snapshot_sha256": snapshot["snapshot_sha256"],
            "predictors": predictors,
            "targets": targets,
            "split": split,
            "label_provenance": {
                "source": label["label_source"],
                "source_id": label["label_source_id"],
                "settled_at": label["_settled_at_utc"].isoformat().replace("+00:00", "Z"),
                "retrieved_at": label["_retrieved_at_utc"].isoformat().replace("+00:00", "Z"),
                "payload_sha256": label["payload_sha256"],
            },
        })
        split_counts[split] += 1
        competition_counts[label["competition_key"]][split] += 1
        for market, outcome in targets.items():
            market_counts[market][split][outcome] += 1

    rows.sort(key=lambda row: (row["kickoff_at"], row["fixture_id"]))
    report = {
        "schema_version": 1,
        "dataset_type": "veltrix_chronological_pre_match_training_dataset",
        "split_policy": policy,
        "rows": rows,
        "excluded": excluded,
        "quality": {
            "input_snapshot_count": len(snapshots),
            "input_settled_label_count": len(settled_labels),
            "joined_fixture_count": len(snapshot_by_id),
            "included_fixture_count": len(rows),
            "excluded_fixture_count": len(excluded),
            "counts_by_split": {
                split: split_counts.get(split, 0)
                for split in ("train", "validation", "test")
            },
            "counts_by_competition_and_split": {
                competition: {
                    split: counts.get(split, 0)
                    for split in ("train", "validation", "test")
                }
                for competition, counts in sorted(competition_counts.items())
            },
            "market_outcome_counts": {
                market: {
                    split: dict(counts.get(split, {}))
                    for split in ("train", "validation", "test")
                }
                for market, counts in sorted(market_counts.items())
            },
            "chronological_order": True,
            "fixture_overlap_between_splits": False,
            "target_labels_separate_from_predictors": True,
        },
        "training_readiness": {
            "ready_for_model_training": False,
            "reason": "Dataset assembly does not certify source completeness, market sample thresholds, calibration, or point-in-time feature sufficiency",
        },
        "side_effects": {
            "database_writes": 0,
            "model_training_runs": 0,
            "prediction_publications": 0,
        },
    }
    report["dataset_sha256"] = _hash(report)
    return report


def validate_chronological_training_dataset(dataset: Any) -> dict:
    if not isinstance(dataset, dict) or dataset.get("schema_version") != 1:
        raise ChronologicalDatasetError("dataset_schema_invalid")
    if dataset.get("dataset_type") != "veltrix_chronological_pre_match_training_dataset":
        raise ChronologicalDatasetError("dataset_type_invalid")
    supplied = dataset.get("dataset_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        raise ChronologicalDatasetError("dataset_hash_invalid")
    unhashed = dict(dataset)
    unhashed.pop("dataset_sha256", None)
    if _hash(unhashed) != supplied:
        raise ChronologicalDatasetError("dataset_hash_mismatch")
    policy = _split_policy(dataset.get("split_policy"))
    rows = dataset.get("rows")
    quality = dataset.get("quality")
    if not isinstance(rows, list) or not isinstance(quality, dict):
        raise ChronologicalDatasetError("dataset_content_invalid")
    seen = set()
    previous = None
    actual_counts = Counter()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("split") not in {"train", "validation", "test"}:
            raise ChronologicalDatasetError(f"dataset_row_invalid:{index}")
        fixture_id = row.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id or fixture_id in seen:
            raise ChronologicalDatasetError(f"dataset_fixture_identity_invalid:{index}")
        seen.add(fixture_id)
        kickoff = _time(row.get("kickoff_at"), f"row_{index}_kickoff")
        cutoff = _time(row.get("prediction_as_of"), f"row_{index}_prediction_as_of")
        if cutoff >= kickoff:
            raise ChronologicalDatasetError(f"dataset_temporal_leakage:{index}")
        if previous is not None and kickoff < previous:
            raise ChronologicalDatasetError("dataset_rows_not_chronological")
        previous = kickoff
        local_day = kickoff.astimezone(ZoneInfo("Africa/Lagos")).date()
        split = row["split"]
        if split == "train" and local_day > date.fromisoformat(policy["train_end_date"]):
            raise ChronologicalDatasetError(f"dataset_train_window_violation:{index}")
        if split == "validation" and not (
            date.fromisoformat(policy["validation_start_date"]) <= local_day <= date.fromisoformat(policy["validation_end_date"])
        ):
            raise ChronologicalDatasetError(f"dataset_validation_window_violation:{index}")
        if split == "test" and not (
            date.fromisoformat(policy["test_start_date"]) <= local_day <= date.fromisoformat(policy["test_end_date"])
        ):
            raise ChronologicalDatasetError(f"dataset_test_window_violation:{index}")
        if not isinstance(row.get("competition_key"), str) or not row["competition_key"].strip():
            raise ChronologicalDatasetError(f"dataset_competition_invalid:{index}")
        snapshot_hash = row.get("feature_snapshot_sha256")
        if (not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64
                or any(char not in "0123456789abcdef" for char in snapshot_hash)):
            raise ChronologicalDatasetError(f"dataset_feature_snapshot_hash_invalid:{index}")
        predictors, targets = row.get("predictors"), row.get("targets")
        if not isinstance(predictors, dict) or not predictors or not isinstance(targets, dict):
            raise ChronologicalDatasetError(f"dataset_predictor_target_shape_invalid:{index}")
        if any(name not in FEATURE_CATALOGUE or name in FORBIDDEN_FEATURE_NAMES
               or isinstance(value, bool) or not isinstance(value, (int, float))
               for name, value in predictors.items()):
            raise ChronologicalDatasetError(f"dataset_predictor_allowlist_invalid:{index}")
        if set(targets) != {"1x2", "btts", "over_2_5"}:
            raise ChronologicalDatasetError(f"dataset_market_target_scope_invalid:{index}")
        if (targets["1x2"] not in {"home", "draw", "away"}
                or targets["btts"] not in {"yes", "no"}
                or targets["over_2_5"] not in {"yes", "no"}):
            raise ChronologicalDatasetError(f"dataset_market_target_value_invalid:{index}")
        provenance = row.get("label_provenance")
        provenance_keys = {"source", "source_id", "settled_at", "retrieved_at", "payload_sha256"}
        if not isinstance(provenance, dict) or set(provenance) != provenance_keys:
            raise ChronologicalDatasetError(f"dataset_label_provenance_invalid:{index}")
        if any(not isinstance(provenance.get(key), str) or not provenance[key].strip()
               for key in ("source", "source_id")):
            raise ChronologicalDatasetError(f"dataset_label_source_invalid:{index}")
        label_hash = provenance.get("payload_sha256")
        if (not isinstance(label_hash, str) or len(label_hash) != 64
                or any(char not in "0123456789abcdef" for char in label_hash)):
            raise ChronologicalDatasetError(f"dataset_label_hash_invalid:{index}")
        settled = _time(provenance.get("settled_at"), f"row_{index}_settled_at")
        retrieved = _time(provenance.get("retrieved_at"), f"row_{index}_label_retrieved_at")
        if settled <= kickoff or retrieved < settled:
            raise ChronologicalDatasetError(f"dataset_label_temporal_order_invalid:{index}")
        actual_counts[split] += 1
    if quality.get("included_fixture_count") != len(rows):
        raise ChronologicalDatasetError("dataset_included_count_mismatch")
    if quality.get("counts_by_split") != {
        split: actual_counts.get(split, 0) for split in ("train", "validation", "test")
    }:
        raise ChronologicalDatasetError("dataset_split_count_mismatch")
    if (quality.get("chronological_order") is not True
            or quality.get("fixture_overlap_between_splits") is not False
            or quality.get("target_labels_separate_from_predictors") is not True):
        raise ChronologicalDatasetError("dataset_split_integrity_invalid")
    readiness = dataset.get("training_readiness")
    if not isinstance(readiness, dict) or readiness.get("ready_for_model_training") is not False:
        raise ChronologicalDatasetError("dataset_training_readiness_boundary_invalid")
    side_effects = dataset.get("side_effects")
    if not isinstance(side_effects, dict) or any(side_effects.get(key) != 0 for key in (
        "database_writes", "model_training_runs", "prediction_publications",
    )):
        raise ChronologicalDatasetError("dataset_side_effect_boundary_invalid")
    return {
        "valid": True,
        "dataset_sha256": supplied,
        "included_fixture_count": len(rows),
        "counts_by_split": dict(actual_counts),
        "ready_for_model_training": False,
    }
