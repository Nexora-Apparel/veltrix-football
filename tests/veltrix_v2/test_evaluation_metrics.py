import math

import pytest

from veltrix_v2.evaluation.metrics import (
    Forecast1X2,
    SettledOutcome1X2,
    compare_1x2_forecasts,
    score_1x2,
)


def forecast(fid="f1", home=0.5, draw=0.3, away=0.2):
    return Forecast1X2(fid, home, draw, away)


def outcome(fid="f1", result="HOME"):
    return SettledOutcome1X2(fid, result)


def test_near_perfect_forecast_scores_have_expected_values():
    report = score_1x2(
        [forecast(home=0.999, draw=0.0005, away=0.0005)],
        [outcome(result="HOME")],
    )
    assert report.sample_size == 1
    assert report.multiclass_brier == pytest.approx(0.0000015)
    assert report.log_loss == pytest.approx(-math.log(0.999))
    assert report.ranked_probability_score == pytest.approx(0.000000625)


def test_uniform_forecast_has_known_proper_scores():
    report = score_1x2(
        [forecast(home=1/3, draw=1/3, away=1/3)],
        [outcome(result="DRAW")],
    )
    assert report.multiclass_brier == pytest.approx(2/3)
    assert report.log_loss == pytest.approx(math.log(3))
    assert report.ranked_probability_score == pytest.approx(1/9)


def test_fixture_order_does_not_change_score():
    forecasts = [forecast("a", 0.6, 0.25, 0.15), forecast("b", 0.2, 0.3, 0.5)]
    outcomes = [outcome("a", "HOME"), outcome("b", "AWAY")]
    assert score_1x2(forecasts, outcomes) == score_1x2(
        list(reversed(forecasts)), list(reversed(outcomes))
    )


@pytest.mark.parametrize("values", [
    (0.5, 0.3, 0.3),
    (0.0, 0.5, 0.5),
    (float("nan"), 0.5, 0.5),
    (0.5, -0.1, 0.6),
    (True, 0.0, 0.0),
    ("0.5", 0.3, 0.2),
])
def test_invalid_probability_vectors_are_rejected(values):
    with pytest.raises(ValueError):
        forecast(home=values[0], draw=values[1], away=values[2])


def test_duplicate_forecast_ids_fail_closed():
    with pytest.raises(ValueError, match="duplicate forecast"):
        score_1x2([forecast("same"), forecast("same")],
                  [outcome("same")])


def test_duplicate_outcome_ids_fail_closed():
    with pytest.raises(ValueError, match="duplicate outcome"):
        score_1x2([forecast("same")],
                  [outcome("same"), outcome("same")])


def test_unmatched_fixture_sets_fail_closed():
    with pytest.raises(ValueError, match="must match exactly"):
        score_1x2([forecast("forecast")], [outcome("other")])


def test_empty_evaluation_fails_closed():
    with pytest.raises(ValueError, match="at least one"):
        score_1x2([], [])


def test_model_benchmark_comparison_uses_same_fixtures_and_reports_deltas():
    comparison = compare_1x2_forecasts(
        model_forecasts=[forecast("same", 0.8, 0.1, 0.1)],
        benchmark_forecasts=[forecast("same", 0.6, 0.2, 0.2)],
        outcomes=[outcome("same", "HOME")],
    )
    assert comparison.sample_size == 1
    assert comparison.model_beats_brier is True
    assert comparison.model_beats_log_loss is True
    assert comparison.brier_delta < 0
    assert comparison.log_loss_delta < 0


def test_benchmark_comparison_rejects_different_fixture_sets():
    with pytest.raises(ValueError, match="must match exactly"):
        compare_1x2_forecasts(
            model_forecasts=[forecast("model")],
            benchmark_forecasts=[forecast("market")],
            outcomes=[outcome("model")],
        )
