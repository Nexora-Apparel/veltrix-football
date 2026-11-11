from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.evaluation.binary_calibration import (
    HeldOutBinaryFold,
    diagnose_binary_calibration,
)
from veltrix_v2.evaluation.binary_metrics import BinaryForecast, SettledBinaryOutcome


def make_fold(number, forecasts, outcomes, *, market="BTTS", test_count=None):
    forecasts, outcomes = tuple(forecasts), tuple(outcomes)
    return HeldOutBinaryFold(
        fold_number=number,
        market=market,
        test_fixture_count=len(forecasts) if test_count is None else test_count,
        forecasts=forecasts,
        outcomes=outcomes,
    )


def test_binary_calibration_reports_reliability_and_abstentions():
    forecasts = (BinaryForecast("a", 0.8), BinaryForecast("b", 0.2))
    outcomes = (SettledBinaryOutcome("a", "YES"), SettledBinaryOutcome("b", "NO"))
    report = diagnose_binary_calibration([
        make_fold(1, forecasts[:1], outcomes[:1], test_count=2),
        make_fold(2, forecasts[1:], outcomes[1:], test_count=3),
    ], bin_count=5)
    assert report.market == "BTTS"
    assert report.test_fixture_count == 5
    assert report.forecast_count == 2
    assert report.abstentions == 3
    assert report.coverage == 0.4
    assert report.calibration.brier_score is not None
    assert report.calibration.expected_calibration_error is not None
    assert report.folds[0].abstentions == 1


def test_binary_calibration_rejects_mixed_markets():
    f = BinaryForecast("a", 0.8)
    o = SettledBinaryOutcome("a", "YES")
    with pytest.raises(ValueError, match="cannot mix markets"):
        diagnose_binary_calibration([
            make_fold(1, [f], [o], market="BTTS"),
            make_fold(2, [BinaryForecast("b", 0.4)], [SettledBinaryOutcome("b", "NO")], market="TOTALS"),
        ])


def test_binary_calibration_rejects_cross_fold_duplicate_fixture():
    f = BinaryForecast("a", 0.8)
    o = SettledBinaryOutcome("a", "YES")
    with pytest.raises(ValueError, match="more than one"):
        diagnose_binary_calibration([make_fold(1, [f], [o]), make_fold(2, [f], [o])])


def test_binary_calibration_retains_empty_abstention_fold():
    report = diagnose_binary_calibration([
        make_fold(1, [BinaryForecast("a", 0.7)], [SettledBinaryOutcome("a", "YES")]),
        make_fold(2, [], [], test_count=4),
    ])
    assert report.folds[1].coverage == 0.0
    assert report.folds[1].calibration.sample_size == 0
    assert report.folds[1].calibration.brier_score is None


def test_binary_calibration_requires_forecast_sample():
    with pytest.raises(ValueError, match="no held-out forecasts"):
        diagnose_binary_calibration([make_fold(1, [], [], test_count=3)])


def test_binary_calibration_validates_bin_count():
    with pytest.raises(ValueError, match="bin_count"):
        diagnose_binary_calibration([
            make_fold(1, [BinaryForecast("a", 0.7)], [SettledBinaryOutcome("a", "YES")])
        ], bin_count=1)
