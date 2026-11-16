from __future__ import annotations

import math
import pytest

from veltrix_v2.models.dixon_coles import fit_dixon_coles_rho
from veltrix_v2.evaluation.calibration import (
    apply_binary_platt,
    apply_multiclass_temperature,
    fit_binary_platt,
    fit_multiclass_temperature,
)


def test_dixon_coles_fit_uses_training_rows_and_returns_valid_rho():
    rows = []
    for i in range(80):
        # Deterministic, deliberately low-score-heavy sample.
        rows.append((1.25, 1.05, 0 if i % 3 else 1, 0 if i % 4 else 1))
    fitted = fit_dixon_coles_rho(rows, minimum_rows=30)
    assert -0.2 <= fitted.rho <= 0.2
    assert fitted.observations == 80
    assert math.isfinite(fitted.log_likelihood)


def test_dixon_coles_rejects_small_or_invalid_training_samples():
    with pytest.raises(ValueError, match="SAMPLE_TOO_SMALL"):
        fit_dixon_coles_rho([(1.2, 1.1, 0, 0)] * 5)
    with pytest.raises(ValueError, match="ROW_INVALID"):
        fit_dixon_coles_rho([(0.0, 1.1, 0, 0)] * 40)


def test_multiclass_temperature_preserves_simplex():
    probabilities = [(0.8, 0.1, 0.1), (0.1, 0.8, 0.1), (0.1, 0.1, 0.8)] * 20
    labels = [0, 1, 2] * 20
    fitted = fit_multiclass_temperature(probabilities, labels)
    calibrated = apply_multiclass_temperature((0.7, 0.2, 0.1), fitted)
    assert fitted.sample_count == 60
    assert all(0 <= p <= 1 for p in calibrated)
    assert sum(calibrated) == pytest.approx(1.0)


def test_binary_platt_calibration_returns_probability():
    probabilities = [0.8, 0.7, 0.3, 0.2] * 15
    labels = [1, 1, 0, 0] * 15
    fitted = fit_binary_platt(probabilities, labels)
    calibrated = apply_binary_platt(0.65, fitted)
    assert fitted.sample_count == 60
    assert 0 < calibrated < 1


def test_calibrators_reject_too_small_samples():
    with pytest.raises(ValueError, match="SAMPLE_INVALID"):
        fit_multiclass_temperature([(0.5, 0.5)] * 4, [0] * 4)
    with pytest.raises(ValueError, match="SAMPLE_INVALID"):
        fit_binary_platt([0.2, 0.8], [0, 1])
