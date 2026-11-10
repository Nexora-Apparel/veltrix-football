"""Independent, results-history-only market models for VELTRIX FOOTBALL 2.0.

This module is deliberately isolated from the legacy predictor and from the
xG-based Dixon-Coles experiment. It fits three separate regularized logistic
models: multinomial 1X2, binary BTTS and binary Over/Under 2.5.

Inputs must already be reconstructed from verified pre-kickoff history.
Training is chronological, deterministic and non-publishable by construction.
No fallback priors, favourite filters, synthetic labels or xG substitutions.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

MODEL_FAMILY = "veltrix-independent-results-history-logistic-v1"
FEATURES = (
    "home_attack_goals_rate",
    "home_defence_conceded_rate",
    "away_attack_goals_rate",
    "away_defence_conceded_rate",
    "elo_difference_home",
    "home_form_points_rate",
    "away_form_points_rate",
    "home_rest_days",
    "away_rest_days",
    "competition_home_goals_rate",
    "competition_away_goals_rate",
)
MARKETS = {
    "1x2": ("home", "draw", "away"),
    "btts": ("no", "yes"),
    "over_2_5": ("no", "yes"),
}
DEFAULT_EPOCHS = 1200
DEFAULT_LEARNING_RATE = 0.04
DEFAULT_L2 = 0.02


class ResultsModelError(ValueError):
    pass


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ResultsModelError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ResultsModelError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResultsModelError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 700.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -700.0))
    return z / (1.0 + z)


def _softmax(values: list[float]) -> list[float]:
    peak = max(values)
    exps = [math.exp(max(-700.0, value - peak)) for value in values]
    total = sum(exps)
    if not math.isfinite(total) or total <= 0:
        raise ResultsModelError("softmax_normalization_failed")
    return [value / total for value in exps]


def _validate_row(row: Any, index: int, training_cutoff: datetime) -> dict:
    score_shape = {
        "fixture_id", "kickoff_at", "feature_as_of", "settled_at",
        "features", "home_score", "away_score", "source_record_sha256",
    }
    market_shape = {
        "fixture_id", "kickoff_at", "feature_as_of", "settled_at",
        "features", "market_targets", "source_record_sha256",
    }
    if not isinstance(row, dict) or set(row) not in (score_shape, market_shape):
        raise ResultsModelError(f"training_row_shape_invalid:{index}")
    fixture_id = row.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ResultsModelError(f"fixture_id_invalid:{index}")
    kickoff = _time(row["kickoff_at"], f"row_{index}_kickoff")
    feature_as_of = _time(row["feature_as_of"], f"row_{index}_feature_as_of")
    settled = _time(row["settled_at"], f"row_{index}_settled_at")
    if feature_as_of >= kickoff or settled <= kickoff:
        raise ResultsModelError(f"row_temporal_order_invalid:{fixture_id}")
    if kickoff > training_cutoff:
        raise ResultsModelError(f"row_after_training_cutoff:{fixture_id}")
    digest = row.get("source_record_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)):
        raise ResultsModelError(f"source_record_hash_invalid:{fixture_id}")
    features = row.get("features")
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise ResultsModelError(f"feature_schema_invalid:{fixture_id}")
    clean = {}
    for name in FEATURES:
        value = features[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise ResultsModelError(f"feature_value_invalid:{fixture_id}:{name}")
        clean[name] = float(value)
    if any(clean[name] < 0 or clean[name] > 5 for name in (
        "home_attack_goals_rate", "home_defence_conceded_rate",
        "away_attack_goals_rate", "away_defence_conceded_rate",
        "competition_home_goals_rate", "competition_away_goals_rate",
    )):
        raise ResultsModelError(f"goal_rate_out_of_range:{fixture_id}")
    if not -1200 <= clean["elo_difference_home"] <= 1200:
        raise ResultsModelError(f"elo_difference_out_of_range:{fixture_id}")
    if any(not 0 <= clean[name] <= 1 for name in (
        "home_form_points_rate", "away_form_points_rate",
    )):
        raise ResultsModelError(f"form_rate_out_of_range:{fixture_id}")
    if any(not 0 <= clean[name] <= 30 for name in ("home_rest_days", "away_rest_days")):
        raise ResultsModelError(f"rest_days_out_of_range:{fixture_id}")
    if "market_targets" in row:
        labels = row["market_targets"]
        if (not isinstance(labels, dict)
                or set(labels) != {"1x2", "btts", "over_2_5"}
                or labels["1x2"] not in MARKETS["1x2"]
                or labels["btts"] not in MARKETS["btts"]
                or labels["over_2_5"] not in MARKETS["over_2_5"]):
            raise ResultsModelError(f"market_targets_invalid:{fixture_id}")
        clean_labels = dict(labels)
    else:
        home, away = row["home_score"], row["away_score"]
        if (isinstance(home, bool) or not isinstance(home, int) or home < 0
                or isinstance(away, bool) or not isinstance(away, int) or away < 0):
            raise ResultsModelError(f"settled_score_invalid:{fixture_id}")
        clean_labels = {
            "1x2": "home" if home > away else "away" if home < away else "draw",
            "btts": "yes" if home > 0 and away > 0 else "no",
            "over_2_5": "yes" if home + away >= 3 else "no",
        }
    return {
        "fixture_id": fixture_id,
        "kickoff_at": kickoff,
        "features": clean,
        "labels": clean_labels,
        "source_record_sha256": digest,
    }


def _fit_scaler(rows: list[dict]) -> tuple[list[float], list[float]]:
    means, scales = [], []
    for name in FEATURES:
        values = [row["features"][name] for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance)
        means.append(mean)
        scales.append(scale if scale > 1e-9 else 1.0)
    return means, scales


def _vector(features: dict, means: list[float], scales: list[float]) -> list[float]:
    return [1.0] + [
        (features[name] - means[index]) / scales[index]
        for index, name in enumerate(FEATURES)
    ]


def _fit_binary(rows: list[dict], market: str, means: list[float],
                scales: list[float], epochs: int, learning_rate: float,
                l2: float) -> list[float]:
    weights = [0.0] * (len(FEATURES) + 1)
    vectors = [_vector(row["features"], means, scales) for row in rows]
    labels = [1.0 if row["labels"][market] == "yes" else 0.0 for row in rows]
    for _ in range(epochs):
        gradients = [0.0] * len(weights)
        for vector, label in zip(vectors, labels):
            probability = _sigmoid(sum(w * x for w, x in zip(weights, vector)))
            error = probability - label
            for j, x in enumerate(vector):
                gradients[j] += error * x
        rate = learning_rate / len(rows)
        for j in range(len(weights)):
            penalty = 0.0 if j == 0 else l2 * weights[j]
            weights[j] -= rate * (gradients[j] + penalty)
    return weights


def _fit_multiclass(rows: list[dict], means: list[float], scales: list[float],
                    epochs: int, learning_rate: float, l2: float) -> list[list[float]]:
    classes = MARKETS["1x2"]
    vectors = [_vector(row["features"], means, scales) for row in rows]
    labels = [classes.index(row["labels"]["1x2"]) for row in rows]
    weights = [[0.0] * (len(FEATURES) + 1) for _ in classes]
    for _ in range(epochs):
        gradients = [[0.0] * len(FEATURES + (0,)) for _ in classes]
        for vector, label in zip(vectors, labels):
            probabilities = _softmax([
                sum(w * x for w, x in zip(class_weights, vector))
                for class_weights in weights
            ])
            for class_index, probability in enumerate(probabilities):
                error = probability - (1.0 if class_index == label else 0.0)
                for j, x in enumerate(vector):
                    gradients[class_index][j] += error * x
        rate = learning_rate / len(rows)
        for class_index in range(len(classes)):
            for j in range(len(weights[class_index])):
                penalty = 0.0 if j == 0 else l2 * weights[class_index][j]
                weights[class_index][j] -= rate * (
                    gradients[class_index][j] + penalty
                )
    return weights


def fit_independent_market_models(*, training_rows: list[dict],
                                  training_cutoff_at: str,
                                  trained_at: str,
                                  epochs: int = DEFAULT_EPOCHS,
                                  learning_rate: float = DEFAULT_LEARNING_RATE,
                                  l2: float = DEFAULT_L2) -> dict:
    """Fit separate market heads from real, pre-cutoff settled score records.

    This is a candidate fitting routine, not a certification or release action.
    Callers must supply only training-split rows; validation/test rows are never
    accepted as part of the fit.
    """
    if not isinstance(training_rows, list) or len(training_rows) < 100:
        raise ResultsModelError("training_sample_below_minimum_100")
    if (isinstance(epochs, bool) or not isinstance(epochs, int)
            or not 100 <= epochs <= 10000):
        raise ResultsModelError("epochs_out_of_range")
    for name, value in (("learning_rate", learning_rate), ("l2", l2)):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise ResultsModelError(f"{name}_invalid")
    if not 0.0001 <= learning_rate <= 0.2 or not 0 <= l2 <= 10:
        raise ResultsModelError("optimizer_parameters_out_of_range")
    cutoff = _time(training_cutoff_at, "training_cutoff_at")
    trained = _time(trained_at, "trained_at")
    if trained <= cutoff:
        raise ResultsModelError("model_training_timestamp_must_follow_data_cutoff")
    rows = [_validate_row(row, i, cutoff) for i, row in enumerate(training_rows)]
    if len({row["fixture_id"] for row in rows}) != len(rows):
        raise ResultsModelError("duplicate_training_fixture")
    if len({row["kickoff_at"] for row in rows}) < 30:
        raise ResultsModelError("training_dates_below_minimum_30")
    if any(len({row["labels"][market] for row in rows}) < len(MARKETS[market])
           for market in MARKETS):
        raise ResultsModelError("training_market_class_missing")
    rows.sort(key=lambda row: (row["kickoff_at"], row["fixture_id"]))
    means, scales = _fit_scaler(rows)
    source_digest = _canonical_hash([
        {"fixture_id": row["fixture_id"],
         "source_record_sha256": row["source_record_sha256"]}
        for row in rows
    ])
    model = {
        "schema_version": 1,
        "model_family": MODEL_FAMILY,
        "training_cutoff_at": cutoff.isoformat(),
        "trained_at": trained.isoformat(),
        "training_rows": len(rows),
        "training_fixture_ids_sha256": _canonical_hash(
            [row["fixture_id"] for row in rows]
        ),
        "training_source_records_sha256": source_digest,
        "feature_names": list(FEATURES),
        "scaler": {"means": means, "scales": scales},
        "market_models": {
            "1x2": {
                "classes": list(MARKETS["1x2"]),
                "weights": _fit_multiclass(
                    rows, means, scales, epochs, learning_rate, l2
                ),
            },
            "btts": {
                "classes": ["no", "yes"],
                "weights": _fit_binary(
                    rows, "btts", means, scales, epochs, learning_rate, l2
                ),
            },
            "over_2_5": {
                "classes": ["no", "yes"],
                "weights": _fit_binary(
                    rows, "over_2_5", means, scales, epochs, learning_rate, l2
                ),
            },
        },
        "training_config": {
            "epochs": epochs, "learning_rate": learning_rate, "l2": l2,
            "optimizer": "deterministic_full_batch_gradient_descent",
        },
        "calibration": {
            "status": "not_calibrated",
            "method": None,
            "calibration_dataset_sha256": None,
        },
        "publication_allowed": False,
        "value_betting_enabled": False,
    }
    model["model_sha256"] = _canonical_hash(model)
    return model


def bind_model_to_dataset(model: dict, *, dataset_sha256: str,
                            split_manifest: dict) -> dict:
    """Seal a fitted model to its exact chronological dataset and split manifest."""
    if not isinstance(model, dict) or model.get("model_family") != MODEL_FAMILY:
        raise ResultsModelError("model_family_invalid")
    if not isinstance(dataset_sha256, str) or len(dataset_sha256) != 64:
        raise ResultsModelError("training_dataset_digest_invalid")
    if any(char not in "0123456789abcdef" for char in dataset_sha256):
        raise ResultsModelError("training_dataset_digest_invalid")
    if not isinstance(split_manifest, dict) or set(split_manifest) != {
        "train", "validation", "test"
    }:
        raise ResultsModelError("training_split_manifest_invalid")
    for split, value in split_manifest.items():
        if (not isinstance(value, dict)
                or set(value) != {"row_count", "fixture_ids_sha256"}
                or isinstance(value["row_count"], bool)
                or not isinstance(value["row_count"], int)
                or value["row_count"] < 0
                or not isinstance(value["fixture_ids_sha256"], str)
                or len(value["fixture_ids_sha256"]) != 64
                or any(char not in "0123456789abcdef"
                       for char in value["fixture_ids_sha256"])):
            raise ResultsModelError(f"training_split_manifest_invalid:{split}")
    sealed = dict(model)
    sealed["training_dataset_sha256"] = dataset_sha256
    sealed["training_split_manifest"] = split_manifest
    sealed["model_sha256"] = _canonical_hash({
        key: value for key, value in sealed.items() if key != "model_sha256"
    })
    return sealed


def _apply_calibration(probabilities: dict, calibration: dict) -> dict:
    if calibration.get("status") != "calibrated":
        return probabilities
    methods = calibration.get("markets")
    if not isinstance(methods, dict) or set(methods) != set(MARKETS):
        raise ResultsModelError("calibration_manifest_invalid")
    calibrated = {}
    temperature = methods["1x2"].get("temperature")
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature) or temperature <= 0):
        raise ResultsModelError("calibration_temperature_invalid")
    calibrated["1x2"] = dict(zip(
        MARKETS["1x2"],
        _softmax([
            math.log(max(probabilities["1x2"][name], 1e-15)) / temperature
            for name in MARKETS["1x2"]
        ]),
    ))
    for market in ("btts", "over_2_5"):
        params = methods[market]
        slope, intercept = params.get("slope"), params.get("intercept")
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in (slope, intercept)):
            raise ResultsModelError(f"calibration_parameters_invalid:{market}")
        p = min(max(probabilities[market]["yes"], 1e-15), 1 - 1e-15)
        logit = math.log(p / (1 - p))
        calibrated_yes = _sigmoid(slope * logit + intercept)
        calibrated[market] = {
            "no": 1.0 - calibrated_yes,
            "yes": calibrated_yes,
        }
    return calibrated


def predict_independent_markets(*, model: dict, features: dict,
                                prediction_as_of: str) -> dict:
    """Infer three independently fitted markets; output remains non-publishable."""
    if not isinstance(model, dict) or model.get("model_family") != MODEL_FAMILY:
        raise ResultsModelError("model_family_invalid")
    supplied = model.get("model_sha256")
    unhashed = dict(model)
    unhashed.pop("model_sha256", None)
    if not isinstance(supplied, str) or _canonical_hash(unhashed) != supplied:
        raise ResultsModelError("model_digest_mismatch")
    cutoff = _time(prediction_as_of, "prediction_as_of")
    if _time(model["training_cutoff_at"], "model_training_cutoff_at") > cutoff:
        raise ResultsModelError("model_contains_future_training_data")
    if _time(model["trained_at"], "model_trained_at") > cutoff:
        raise ResultsModelError("model_trained_after_prediction_cutoff")
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise ResultsModelError("inference_feature_schema_invalid")
    clean = {}
    for name in FEATURES:
        value = features[name]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise ResultsModelError(f"inference_feature_invalid:{name}")
        clean[name] = float(value)
    vector = _vector(clean, model["scaler"]["means"], model["scaler"]["scales"])
    heads = model["market_models"]
    p_1x2 = _softmax([
        sum(w * x for w, x in zip(weights, vector))
        for weights in heads["1x2"]["weights"]
    ])
    output = {
        "1x2": dict(zip(MARKETS["1x2"], p_1x2)),
    }
    for market in ("btts", "over_2_5"):
        weights = heads[market]["weights"]
        p_yes = _sigmoid(sum(w * x for w, x in zip(weights, vector)))
        output[market] = {"no": 1.0 - p_yes, "yes": p_yes}
    if any(not 0 <= p <= 1 or not math.isfinite(p)
           for outcomes in output.values() for p in outcomes.values()):
        raise ResultsModelError("inference_probability_invalid")
    calibration = model.get("calibration", {"status": "not_calibrated"})
    output = _apply_calibration(output, calibration)
    return {
        "schema_version": 1,
        "model_family": MODEL_FAMILY,
        "model_sha256": supplied,
        "prediction_as_of": cutoff.isoformat(),
        "probabilities": output,
        "calibration_status": calibration.get("status", "not_calibrated"),
        "publication_allowed": False,
        "value_betting_enabled": False,
        "legacy_model_dependency": False,
        "fallback_prior_used": False,
        "favourite_filter_used": False,
    }
