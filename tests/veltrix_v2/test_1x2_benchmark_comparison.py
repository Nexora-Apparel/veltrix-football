import pytest

from veltrix_v2.evaluation.metrics import (
    Forecast1X2,
    SettledOutcome1X2,
    compare_1x2_forecasts,
)


def test_model_is_compared_with_bookmaker_on_identical_settled_fixtures():
    outcomes = [
        SettledOutcome1X2("f1", "HOME"),
        SettledOutcome1X2("f2", "DRAW"),
        SettledOutcome1X2("f3", "AWAY"),
    ]
    model = [
        Forecast1X2("f1", 0.70, 0.20, 0.10),
        Forecast1X2("f2", 0.20, 0.60, 0.20),
        Forecast1X2("f3", 0.10, 0.20, 0.70),
    ]
    bookmaker = [
        Forecast1X2("f1", 0.30, 0.30, 0.40),
        Forecast1X2("f2", 0.30, 0.40, 0.30),
        Forecast1X2("f3", 0.40, 0.30, 0.30),
    ]

    result = compare_1x2_forecasts(model, bookmaker, outcomes)
    assert result.sample_size == 3
    assert result.model_beats_brier is True
    assert result.model_beats_log_loss is True
    assert result.brier_delta < 0
    assert result.log_loss_delta < 0


def test_comparison_rejects_different_fixture_universes():
    outcomes = [SettledOutcome1X2("f1", "HOME")]
    model = [Forecast1X2("f1", 0.7, 0.2, 0.1)]
    bookmaker = [Forecast1X2("f2", 0.5, 0.3, 0.2)]

    with pytest.raises(ValueError, match="identities must match exactly"):
        compare_1x2_forecasts(model, bookmaker, outcomes)


def test_comparison_reports_model_minus_benchmark_delta():
    outcomes = [SettledOutcome1X2("f1", "HOME")]
    model = [Forecast1X2("f1", 0.6, 0.2, 0.2)]
    bookmaker = [Forecast1X2("f1", 0.3, 0.4, 0.3)]

    result = compare_1x2_forecasts(model, bookmaker, outcomes)
    assert result.brier_delta < 0
    assert result.log_loss_delta < 0
    assert result.ranked_probability_score_delta < 0
