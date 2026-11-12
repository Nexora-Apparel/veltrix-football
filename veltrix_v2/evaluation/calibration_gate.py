"""Explicit, reproducible calibration quality gates for VELTRIX V2.

The diagnostic modules report reliability; this module applies the release
policy. A market passes only with at least 1,000 held-out forecasts, ECE <= 0.05
and maximum reliability-bin gap <= 0.15. These thresholds are deliberately
fixed here rather than accepted from callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from veltrix_v2.evaluation.binary_calibration import BinaryCalibrationReport
from veltrix_v2.evaluation.calibration import CalibrationReport1X2

MIN_CALIBRATION_SAMPLE = 1000
MAX_EXPECTED_CALIBRATION_ERROR = 0.05
MAX_RELIABILITY_BIN_GAP = 0.15


@dataclass(frozen=True, slots=True)
class CalibrationGateResult:
    market: str
    sample_size: int
    expected_calibration_error: float | None
    maximum_calibration_error: float | None
    passed: bool
    failed_gates: tuple[str, ...]


def _valid_metric(value: float | None) -> bool:
    return value is not None and isfinite(float(value)) and 0.0 <= value <= 1.0


def evaluate_calibration_gate(
    report: CalibrationReport1X2 | BinaryCalibrationReport,
) -> tuple[CalibrationGateResult, ...]:
    """Apply the fixed V2 calibration policy to evaluator-generated reports."""
    if isinstance(report, CalibrationReport1X2):
        if len(report.classes) != 3 or {row.outcome_class for row in report.classes} != {"HOME", "DRAW", "AWAY"}:
            raise ValueError("CALIBRATION_GATE_REQUIRES_ALL_1X2_CLASSES")
        results = []
        for row in report.classes:
            ece = row.expected_calibration_error
            maximum = row.maximum_calibration_error
            failures = []
            if row.sample_size < MIN_CALIBRATION_SAMPLE:
                failures.append("CALIBRATION_SAMPLE_BELOW_1000")
            if not _valid_metric(ece) or ece > MAX_EXPECTED_CALIBRATION_ERROR:
                failures.append("EXPECTED_CALIBRATION_ERROR_ABOVE_5_PERCENT")
            if not _valid_metric(maximum) or maximum > MAX_RELIABILITY_BIN_GAP:
                failures.append("MAX_RELIABILITY_BIN_GAP_ABOVE_15_PERCENT")
            results.append(CalibrationGateResult(
                market=f"1X2:{row.outcome_class}",
                sample_size=row.sample_size,
                expected_calibration_error=ece,
                maximum_calibration_error=maximum,
                passed=not failures,
                failed_gates=tuple(failures),
            ))
        return tuple(results)

    if isinstance(report, BinaryCalibrationReport):
        if report.market not in {"BTTS", "TOTALS", "OVER_UNDER"}:
            raise ValueError("CALIBRATION_GATE_UNSUPPORTED_BINARY_MARKET")
        row = report.calibration
        failures = []
        if row.sample_size < MIN_CALIBRATION_SAMPLE:
            failures.append("CALIBRATION_SAMPLE_BELOW_1000")
        if not _valid_metric(row.expected_calibration_error) or row.expected_calibration_error > MAX_EXPECTED_CALIBRATION_ERROR:
            failures.append("EXPECTED_CALIBRATION_ERROR_ABOVE_5_PERCENT")
        if not _valid_metric(row.maximum_calibration_error) or row.maximum_calibration_error > MAX_RELIABILITY_BIN_GAP:
            failures.append("MAX_RELIABILITY_BIN_GAP_ABOVE_15_PERCENT")
        market = "TOTALS" if report.market == "OVER_UNDER" else report.market
        return (CalibrationGateResult(
            market=market,
            sample_size=row.sample_size,
            expected_calibration_error=row.expected_calibration_error,
            maximum_calibration_error=row.maximum_calibration_error,
            passed=not failures,
            failed_gates=tuple(failures),
        ),)

    raise ValueError("CALIBRATION_GATE_EVALUATOR_REPORT_REQUIRED")
