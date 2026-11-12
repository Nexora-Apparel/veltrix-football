import pytest

from veltrix_v2.evaluation.calibration import (
    HeldOutFold1X2,
    diagnose_1x2_calibration,
)
from veltrix_v2.evaluation.metrics import Forecast1X2, SettledOutcome1X2


def fold(number, forecasts, outcomes, test_count=None):
    forecasts = tuple(forecasts)
    outcomes = tuple(outcomes)
    return HeldOutFold1X2(
        fold_number=number,
        test_fixture_count=len(forecasts) if test_count is None else test_count,
        forecasts=forecasts,
        outcomes=outcomes,
    )


def test_classwise_calibration_reports_bins_brier_and_coverage():
    f1 = Forecast1X2("a", 0.10, 0.20, 0.70)
    f2 = Forecast1X2("b", 0.20, 0.30, 0.50)
    f3 = Forecast1X2("c", 0.60, 0.20, 0.20)
    outcomes = (
        SettledOutcome1X2("a", "AWAY"),
        SettledOutcome1X2("b", "DRAW"),
        SettledOutcome1X2("c", "HOME"),
    )
    report = diagnose_1x2_calibration(
        [fold(1, [f1, f2], outcomes[:2], test_count=3),
         fold(2, [f3], outcomes[2:], test_count=2)],
        bin_count=5,
    )
    assert report.fold_count == 2
    assert report.test_fixture_count == 5
    assert report.forecast_count == 3
    assert report.abstentions == 2
    assert report.coverage == 0.6
    by_class = {row.outcome_class: row for row in report.classes}
    assert by_class["AWAY"].sample_size == 3
    assert by_class["AWAY"].brier_score is not None
    assert by_class["AWAY"].expected_calibration_error is not None
    assert len(report.folds) == 2
    assert report.folds[0].abstentions == 1


def test_empty_forecast_fold_is_retained_as_full_abstention():
    forecasts = [Forecast1X2("f1", 0.3, 0.4, 0.3)]
    outcomes = [SettledOutcome1X2("f1", "DRAW")]
    report = diagnose_1x2_calibration(
        [fold(1, forecasts, outcomes), fold(2, [], [], test_count=4)]
    )
    assert report.folds[1].forecast_count == 0
    assert report.folds[1].coverage == 0.0
    assert all(c.sample_size == 0 and c.brier_score is None for c in report.folds[1].classes)


def test_duplicate_fold_numbers_are_rejected():
    f = Forecast1X2("f1", 0.3, 0.4, 0.3)
    o = SettledOutcome1X2("f1", "DRAW")
    with pytest.raises(ValueError, match="duplicate fold numbers"):
        diagnose_1x2_calibration([fold(1, [f], [o]), fold(1, [], [], 0)])


def test_fixture_cannot_appear_in_two_held_out_folds():
    f = Forecast1X2("f1", 0.3, 0.4, 0.3)
    o = SettledOutcome1X2("f1", "DRAW")
    with pytest.raises(ValueError, match="more than one held-out fold"):
        diagnose_1x2_calibration([fold(1, [f], [o]), fold(2, [f], [o])])


def test_forecast_outcome_mismatch_is_rejected():
    f = Forecast1X2("f1", 0.3, 0.4, 0.3)
    o = SettledOutcome1X2("f2", "DRAW")
    with pytest.raises(ValueError, match="must match"):
        fold(1, [f], [o])


def test_invalid_bin_count_is_rejected():
    f = Forecast1X2("f1", 0.3, 0.4, 0.3)
    o = SettledOutcome1X2("f1", "DRAW")
    with pytest.raises(ValueError, match="bin_count"):
        diagnose_1x2_calibration([fold(1, [f], [o])], bin_count=1)


def test_empty_overall_forecast_set_is_rejected():
    with pytest.raises(ValueError, match="no held-out forecasts"):
        diagnose_1x2_calibration([fold(1, [], [], test_count=5)])
