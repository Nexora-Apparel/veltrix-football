from math import isclose

import pytest

from veltrix_v2.evaluation.binary_metrics import (
    BinaryForecast,
    SettledBinaryOutcome,
    score_binary_market,
)


def test_binary_market_scores_brier_logloss_hit_rate_and_coverage():
    report = score_binary_market(
        [
            BinaryForecast("f1", 0.8),
            BinaryForecast("f2", 0.2),
            BinaryForecast("f3", 0.7),
        ],
        [
            SettledBinaryOutcome("f1", "YES"),
            SettledBinaryOutcome("f2", "NO"),
            SettledBinaryOutcome("f3", "NO"),
        ],
        eligible_fixture_ids=("f1", "f2", "f3", "f4"),
    )
    assert report.sample_size == 3
    assert report.eligible_fixture_count == 4
    assert report.abstention_count == 1
    assert isclose(report.coverage, 0.75)
    assert isclose(report.hit_rate, 2 / 3)
    assert isclose(report.brier_score, (0.04 + 0.04 + 0.49) / 3)
    assert report.hit_rate_ci95_lower < report.hit_rate < report.hit_rate_ci95_upper


def test_binary_metrics_require_exact_forecast_outcome_identity_match():
    with pytest.raises(ValueError, match="IDS_MUST_MATCH"):
        score_binary_market(
            [BinaryForecast("f1", 0.8)],
            [SettledBinaryOutcome("f2", "YES")],
            eligible_fixture_ids=("f1", "f2"),
        )


def test_binary_metrics_reject_duplicates_and_out_of_scope_fixtures():
    with pytest.raises(ValueError, match="DUPLICATE"):
        score_binary_market(
            [BinaryForecast("f1", 0.8), BinaryForecast("f1", 0.7)],
            [SettledBinaryOutcome("f1", "YES")],
            eligible_fixture_ids=("f1",),
        )
    with pytest.raises(ValueError, match="OUTSIDE_ELIGIBLE"):
        score_binary_market(
            [BinaryForecast("f2", 0.8)],
            [SettledBinaryOutcome("f2", "YES")],
            eligible_fixture_ids=("f1",),
        )


def test_binary_forecast_rejects_invalid_probabilities():
    for value in (0.0, 1.0, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            BinaryForecast("f1", value)


def test_wilson_interval_and_report_fail_on_empty_forecast_cohort():
    with pytest.raises(ValueError, match="NO_FORECASTS"):
        score_binary_market(
            [],
            [],
            eligible_fixture_ids=("f1",),
        )
