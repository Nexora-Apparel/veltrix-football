"""Leakage-safe probability calibration estimators.

Call fit_* only with an earlier chronological calibration partition. Apply the
fitted object unchanged to a later evaluation/holdout partition. This module
does not choose data splits or certify a model.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


_EPS = 1e-12


def _logit(p: float) -> float:
    q = min(max(p, _EPS), 1.0 - _EPS)
    return math.log(q / (1.0 - q))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-min(x, 700.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(x, -700.0))
    return z / (1.0 + z)


@dataclass(frozen=True)
class MulticlassTemperature:
    temperature: float
    sample_count: int
    classes: int
    calibration_log_loss: float


@dataclass(frozen=True)
class BinaryPlattCalibrator:
    slope: float
    intercept: float
    sample_count: int
    calibration_log_loss: float


def _normalise(row: Sequence[float]) -> tuple[float, ...]:
    if len(row) < 2 or any(not math.isfinite(p) or p < 0 for p in row):
        raise ValueError("CALIBRATION_PROBABILITY_VECTOR_INVALID")
    total = sum(row)
    if total <= 0:
        raise ValueError("CALIBRATION_PROBABILITY_MASS_INVALID")
    return tuple(max(p / total, _EPS) for p in row)


def _multiclass_loss(rows: Sequence[tuple[float, ...]], labels: Sequence[int], t: float) -> float:
    total = 0.0
    for probs, y in zip(rows, labels):
        logits = [math.log(p) / t for p in probs]
        maximum = max(logits)
        denom = maximum + math.log(sum(math.exp(v - maximum) for v in logits))
        total += denom - logits[y]
    return total / len(rows)


def fit_multiclass_temperature(
    probabilities: Iterable[Sequence[float]], labels: Iterable[int], *,
    minimum_rows: int = 50, min_temperature: float = 0.25,
    max_temperature: float = 4.0, iterations: int = 80,
) -> MulticlassTemperature:
    """Fit one scalar temperature by bounded golden-section log-loss search."""
    rows = [_normalise(x) for x in probabilities]
    ys = list(labels)
    if len(rows) != len(ys) or len(rows) < minimum_rows:
        raise ValueError("MULTICLASS_CALIBRATION_SAMPLE_INVALID")
    classes = len(rows[0])
    if any(len(row) != classes for row in rows) or any(
        not isinstance(y, int) or isinstance(y, bool) or not 0 <= y < classes for y in ys
    ):
        raise ValueError("MULTICLASS_CALIBRATION_LABEL_INVALID")
    if (not math.isfinite(min_temperature) or not math.isfinite(max_temperature)
            or min_temperature <= 0 or min_temperature >= max_temperature
            or not isinstance(iterations, int) or iterations < 20):
        raise ValueError("TEMPERATURE_SEARCH_INVALID")
    lo, hi = min_temperature, max_temperature
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    x1, x2 = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
    f1, f2 = _multiclass_loss(rows, ys, x1), _multiclass_loss(rows, ys, x2)
    for _ in range(iterations):
        if f1 <= f2:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - ratio * (hi - lo)
            f1 = _multiclass_loss(rows, ys, x1)
        else:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + ratio * (hi - lo)
            f2 = _multiclass_loss(rows, ys, x2)
    temperature = (lo + hi) / 2.0
    return MulticlassTemperature(temperature, len(rows), classes,
                                 _multiclass_loss(rows, ys, temperature))


def apply_multiclass_temperature(
    probabilities: Sequence[float], calibrator: MulticlassTemperature,
) -> tuple[float, ...]:
    row = _normalise(probabilities)
    if len(row) != calibrator.classes or calibrator.temperature <= 0:
        raise ValueError("TEMPERATURE_CALIBRATOR_SHAPE_MISMATCH")
    logits = [math.log(p) / calibrator.temperature for p in row]
    maximum = max(logits)
    exps = [math.exp(x - maximum) for x in logits]
    total = sum(exps)
    return tuple(x / total for x in exps)


def fit_binary_platt(
    probabilities: Iterable[float], labels: Iterable[int], *,
    minimum_rows: int = 50, iterations: int = 100, l2: float = 1e-4,
) -> BinaryPlattCalibrator:
    """Fit logistic calibration on probability logits using Newton updates."""
    ps, ys = list(probabilities), list(labels)
    if len(ps) != len(ys) or len(ps) < minimum_rows:
        raise ValueError("BINARY_CALIBRATION_SAMPLE_INVALID")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in ps):
        raise ValueError("BINARY_CALIBRATION_PROBABILITY_INVALID")
    if any(not isinstance(y, int) or isinstance(y, bool) or y not in (0, 1) for y in ys):
        raise ValueError("BINARY_CALIBRATION_LABEL_INVALID")
    if not isinstance(iterations, int) or iterations < 1 or not math.isfinite(l2) or l2 < 0:
        raise ValueError("PLATT_OPTIMISATION_PARAMETERS_INVALID")
    xs = [_logit(p) for p in ps]
    a, b = 1.0, 0.0
    for _ in range(iterations):
        ga = l2 * a
        gb = 0.0
        haa, hab, hbb = l2, 0.0, 1e-9
        for x, y in zip(xs, ys):
            q = _sigmoid(a * x + b)
            error = q - y
            weight = q * (1.0 - q)
            ga += error * x
            gb += error
            haa += weight * x * x
            hab += weight * x
            hbb += weight
        det = haa * hbb - hab * hab
        if det <= 1e-18:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a -= da
        b -= db
        if max(abs(da), abs(db)) < 1e-8:
            break
    if not math.isfinite(a) or not math.isfinite(b):
        raise ValueError("PLATT_FIT_DIVERGED")
    loss = 0.0
    for x, y in zip(xs, ys):
        q = min(max(_sigmoid(a * x + b), _EPS), 1.0 - _EPS)
        loss -= y * math.log(q) + (1 - y) * math.log(1 - q)
    return BinaryPlattCalibrator(a, b, len(ps), loss / len(ps))


def apply_binary_platt(probability: float, calibrator: BinaryPlattCalibrator) -> float:
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("BINARY_CALIBRATION_PROBABILITY_INVALID")
    return _sigmoid(calibrator.slope * _logit(probability) + calibrator.intercept)
