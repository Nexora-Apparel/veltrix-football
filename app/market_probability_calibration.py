"""Validation-only calibration for independent football market models.

The calibration routine consumes only the validation partition of the exact
dataset bound to a fitted model. The test partition is never read for fitting.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from app.chronological_training_dataset import (
    ChronologicalDatasetError,
    validate_chronological_training_dataset,
)
from app.independent_market_models import (
    MARKETS,
    ResultsModelError,
    bind_model_to_dataset,
    predict_independent_markets,
)


class MarketCalibrationError(ValueError):
    pass


MIN_CALIBRATION_ROWS = 100
MIN_CALIBRATION_DATES = 30


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise MarketCalibrationError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise MarketCalibrationError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketCalibrationError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _softmax(logits: list[float]) -> list[float]:
    peak = max(logits)
    values = [math.exp(max(-700.0, item - peak)) for item in logits]
    total = sum(values)
    return [item / total for item in values]


def _binary_fit(logits: list[float], labels: list[int]) -> dict:
    slope, intercept = 1.0, 0.0
    for _ in range(4000):
        grad_a = grad_b = 0.0
        for logit, label in zip(logits, labels):
            z = max(-40.0, min(40.0, slope * logit + intercept))
            p = 1.0 / (1.0 + math.exp(-z))
            error = p - label
            grad_a += error * logit
            grad_b += error
        rate = 0.02 / len(logits)
        next_slope = max(0.0, slope - rate * grad_a)
        next_intercept = intercept - rate * grad_b
        if abs(next_slope - slope) + abs(next_intercept - intercept) < 1e-10:
            slope, intercept = next_slope, next_intercept
            break
        slope, intercept = next_slope, next_intercept
    if not math.isfinite(slope) or not math.isfinite(intercept):
        raise MarketCalibrationError("binary_calibration_non_finite")
    return {"slope": slope, "intercept": intercept}


def _temperature_fit(probabilities: list[dict], labels: list[str]) -> float:
    classes = MARKETS["1x2"]

    def loss(log_temperature: float) -> float:
        temperature = math.exp(log_temperature)
        total = 0.0
        for row, label in zip(probabilities, labels):
            calibrated = _softmax([
                math.log(max(row[name], 1e-15)) / temperature
                for name in classes
            ])
            total -= math.log(max(calibrated[classes.index(label)], 1e-15))
        return total / len(labels)

    # Golden-section search in log-temperature space [0.05, 20].
    left, right = math.log(0.05), math.log(20.0)
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = right - ratio * (right - left)
    x2 = left + ratio * (right - left)
    f1, f2 = loss(x1), loss(x2)
    for _ in range(120):
        if f1 > f2:
            left, x1, f1 = x1, x2, f2
            x2 = left + ratio * (right - left)
            f2 = loss(x2)
        else:
            right, x2, f2 = x2, x1, f1
            x1 = right - ratio * (right - left)
            f1 = loss(x1)
    return math.exp((left + right) / 2.0)


def _binary_probability(p: float, params: dict) -> float:
    p = min(max(p, 1e-15), 1.0 - 1e-15)
    logit = math.log(p / (1.0 - p))
    z = params["slope"] * logit + params["intercept"]
    z = max(-40.0, min(40.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _metrics(probabilities: list[dict], labels: list[dict]) -> dict:
    output = {}
    for market in MARKETS:
        nll = brier = 0.0
        for probs, target in zip(probabilities, labels):
            actual = target[market]
            for outcome, probability in probs[market].items():
                observed = 1.0 if outcome == actual else 0.0
                brier += (probability - observed) ** 2
            nll -= math.log(max(probs[market][actual], 1e-15))
        output[market] = {
            "log_loss": nll / len(labels),
            "brier": brier / len(labels),
        }
    return output


def calibrate_model_on_validation_split(*, model: dict, dataset: dict,
                                         calibrated_at: str) -> dict:
    """Fit temperature/Platt calibration using validation rows only."""
    if not isinstance(model, dict) or model.get("calibration", {}).get("status") == "calibrated":
        raise MarketCalibrationError("model_missing_or_already_calibrated")
    try:
        integrity = validate_chronological_training_dataset(dataset)
    except ChronologicalDatasetError as exc:
        raise MarketCalibrationError(f"dataset_rejected:{exc}") from None
    if model.get("training_dataset_sha256") != integrity["dataset_sha256"]:
        raise MarketCalibrationError("model_dataset_binding_mismatch")
    manifest = model.get("training_split_manifest")
    if not isinstance(manifest, dict) or set(manifest) != {"train", "validation", "test"}:
        raise MarketCalibrationError("model_split_manifest_invalid")

    validation = [row for row in dataset["rows"] if row["split"] == "validation"]
    expected = manifest["validation"]
    fixture_digest = __import__("hashlib").sha256(
        __import__("json").dumps(
            sorted(row["fixture_id"] for row in validation),
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if len(validation) != expected["row_count"] or fixture_digest != expected["fixture_ids_sha256"]:
        raise MarketCalibrationError("validation_partition_manifest_mismatch")
    if len(validation) < MIN_CALIBRATION_ROWS:
        raise MarketCalibrationError("validation_sample_below_minimum_100")

    calibrated_time = _time(calibrated_at, "calibrated_at")
    dates = set()
    raw_predictions, labels = [], []
    for row in validation:
        kickoff = _time(row["kickoff_at"], "validation_kickoff")
        dates.add(kickoff.astimezone(
            __import__("zoneinfo").ZoneInfo("Africa/Lagos")
        ).date())
        if _time(row["label_provenance"]["retrieved_at"], "label_retrieved_at") > calibrated_time:
            raise MarketCalibrationError(
                f"validation_label_retrieved_after_calibration:{row['fixture_id']}"
            )
        try:
            prediction = predict_independent_markets(
                model=model, features=row["predictors"],
                prediction_as_of=row["prediction_as_of"],
            )
        except ResultsModelError as exc:
            raise MarketCalibrationError(f"validation_prediction_rejected:{exc}") from None
        raw_predictions.append(prediction["probabilities"])
        labels.append(row["targets"])

    if len(dates) < MIN_CALIBRATION_DATES:
        raise MarketCalibrationError("validation_dates_below_minimum_30")
    for market, classes in MARKETS.items():
        observed = {row[market] for row in labels}
        if observed != set(classes):
            raise MarketCalibrationError(f"validation_market_class_missing:{market}")

    temperature = _temperature_fit(
        [row["1x2"] for row in raw_predictions],
        [row["1x2"] for row in labels],
    )
    market_params = {"1x2": {"temperature": temperature}}
    for market in ("btts", "over_2_5"):
        logits, binary_labels = [], []
        for prediction, target in zip(raw_predictions, labels):
            p = min(max(prediction[market]["yes"], 1e-15), 1 - 1e-15)
            logits.append(math.log(p / (1 - p)))
            binary_labels.append(1 if target[market] == "yes" else 0)
        market_params[market] = _binary_fit(logits, binary_labels)

    calibrated_predictions = []
    for prediction in raw_predictions:
        transformed = {}
        transformed["1x2"] = dict(zip(
            MARKETS["1x2"],
            _softmax([
                math.log(max(prediction["1x2"][name], 1e-15)) / temperature
                for name in MARKETS["1x2"]
            ]),
        ))
        for market in ("btts", "over_2_5"):
            yes = _binary_probability(prediction[market]["yes"], market_params[market])
            transformed[market] = {"no": 1 - yes, "yes": yes}
        calibrated_predictions.append(transformed)

    candidate = dict(model)
    candidate["calibration"] = {
        "status": "calibrated",
        "method": {
            "1x2": "temperature_scaling",
            "btts": "platt_scaling",
            "over_2_5": "platt_scaling",
        },
        "markets": market_params,
        "calibration_dataset_sha256": integrity["dataset_sha256"],
        "calibrated_at": calibrated_time.isoformat(),
        "validation_rows": len(validation),
        "validation_dates": len(dates),
        "metrics_before": _metrics(raw_predictions, labels),
        "metrics_after": _metrics(calibrated_predictions, labels),
    }
    try:
        sealed = bind_model_to_dataset(
            candidate,
            dataset_sha256=integrity["dataset_sha256"],
            split_manifest=manifest,
        )
    except ResultsModelError as exc:
        raise MarketCalibrationError(f"calibrated_model_seal_failed:{exc}") from None
    return {
        "model": sealed,
        "calibration_audit": {
            "validation_rows_used": len(validation),
            "validation_dates_used": len(dates),
            "training_rows_used_for_calibration": 0,
            "test_rows_used_for_calibration": 0,
            "test_partition_opened": False,
            "dataset_sha256": integrity["dataset_sha256"],
            "calibration_status": "calibrated",
            "publication_allowed": False,
            "value_betting_enabled": False,
        },
    }
