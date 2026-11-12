import pytest

from veltrix_v2.evaluation.binary_calibration import (
    BinaryCalibrationReport,
    BinaryClassCalibration,
)
from veltrix_v2.evaluation.calibration import (
    CalibrationReport1X2,
    ClassCalibration,
)
from veltrix_v2.evaluation.calibration_gate import (
    evaluate_calibration_gate,
)


def _class(outcome, *, ece=0.04, maximum=0.12, sample=1000):
    return ClassCalibration(
        outcome_class=outcome,
        sample_size=sample,
        brier_score=0.18,
        expected_calibration_error=ece,
        maximum_calibration_error=maximum,
        bins=(),
    )


def _one_x_two(*, ece=0.04, maximum=0.12, sample=1000):
    return CalibrationReport1X2(
        fold_count=5,
        test_fixture_count=sample,
        forecast_count=sample,
        abstentions=0,
        coverage=1.0,
        classes=tuple(
            _class(label, ece=ece, maximum=maximum, sample=sample)
            for label in ("AWAY", "DRAW", "HOME")
        ),
        folds=(),
    )


def _binary(market, *, ece=0.04, maximum=0.12, sample=1000):
    return BinaryCalibrationReport(
        market=market,
        fold_count=5,
        test_fixture_count=sample,
        forecast_count=sample,
        abstentions=0,
        coverage=1.0,
        calibration=BinaryClassCalibration(
            outcome="YES",
            sample_size=sample,
            brier_score=0.18,
            expected_calibration_error=ece,
            maximum_calibration_error=maximum,
            bins=(),
        ),
        folds=(),
    )


def test_1x2_calibration_passes_only_when_all_three_classes_meet_policy():
    results = evaluate_calibration_gate(_one_x_two())
    assert len(results) == 3
    assert all(row.passed for row in results)


@pytest.mark.parametrize(
    ("kwargs", "failure"),
    [
        ({"sample": 999}, "CALIBRATION_SAMPLE_BELOW_1000"),
        ({"ece": 0.05001}, "EXPECTED_CALIBRATION_ERROR_ABOVE_5_PERCENT"),
        ({"maximum": 0.15001}, "MAX_RELIABILITY_BIN_GAP_ABOVE_15_PERCENT"),
    ],
)
def test_1x2_calibration_rejects_each_policy_breach(kwargs, failure):
    results = evaluate_calibration_gate(_one_x_two(**kwargs))
    assert all(not row.passed for row in results)
    assert all(failure in row.failed_gates for row in results)


@pytest.mark.parametrize("market", ["BTTS", "TOTALS"])
def test_binary_calibration_uses_same_fixed_policy(market):
    result, = evaluate_calibration_gate(_binary(market))
    assert result.market == market
    assert result.passed


def test_binary_calibration_rejects_missing_metrics_and_low_sample():
    result, = evaluate_calibration_gate(
        _binary("BTTS", ece=None, maximum=None, sample=999)
    )
    assert not result.passed
    assert "CALIBRATION_SAMPLE_BELOW_1000" in result.failed_gates
    assert "EXPECTED_CALIBRATION_ERROR_ABOVE_5_PERCENT" in result.failed_gates
    assert "MAX_RELIABILITY_BIN_GAP_ABOVE_15_PERCENT" in result.failed_gates


def test_calibration_gate_rejects_non_evaluator_objects():
    with pytest.raises(ValueError, match="EVALUATOR_REPORT_REQUIRED"):
        evaluate_calibration_gate({"passed": True})
