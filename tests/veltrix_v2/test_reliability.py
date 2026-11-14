from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.evaluation.reliability import assess_reliability
from veltrix_v2.evaluation.walk_forward import WalkForwardReport, FixtureEvaluation

UTC = timezone.utc
AS_OF = datetime(2026, 11, 14, 23, tzinfo=UTC)


def fixture(i, day, *, actual="HOME"):
    kickoff = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=day)
    return FixtureEvaluation(
        fixture_id=f"f{i}", competition_id="league", kickoff_at=kickoff,
        cutoff_at=kickoff - timedelta(seconds=1), actual_home_goals=2 if actual == "HOME" else 0,
        actual_away_goals=0 if actual == "HOME" else 2, actual_1x2=actual,
        model_home_win=0.62, model_draw=0.22, model_away_win=0.16,
        baseline_home_win=0.50, baseline_draw=0.27, baseline_away_win=0.23,
        model_btts_yes=0.35, baseline_btts_yes=0.48,
        model_over_2_5=0.42, baseline_over_2_5=0.51,
    )


def report(rows):
    return WalkForwardReport(
        evaluation_as_of=AS_OF, total_input_fixtures=len(rows),
        eligible_scored_fixtures=len(rows), skipped_no_history=0,
        skipped_invalid_target=0, skipped_duplicate_ids=0,
        skipped_after_evaluation_as_of=0, one_x_two=None, btts=None,
        over_2_5=None, fixtures=tuple(rows),
    )


def test_reliability_assessment_has_date_clustered_intervals_and_calibration():
    rows = [fixture(i, i // 2, actual="HOME" if i % 3 else "AWAY") for i in range(60)]
    result = assess_reliability(report(rows), bootstrap_replicates=200, bootstrap_seed=7)
    assert result.one_x_two is not None and result.btts is not None and result.over_2_5 is not None
    assert result.one_x_two.distinct_dates == 30
    assert result.one_x_two.brier_improvement_ci is not None
    assert result.one_x_two.brier_improvement_ci.replicates == 200
    assert len(result.one_x_two.calibration) == 3
    assert result.btts.calibration[0].outcome_class == "BTTS"
    assert result.over_2_5.calibration[0].outcome_class == "OVER_2_5"


def test_one_date_does_not_claim_a_clustered_confidence_interval():
    rows = [fixture(i, 0) for i in range(20)]
    result = assess_reliability(report(rows), bootstrap_replicates=100)
    assert result.btts is not None
    assert result.btts.distinct_dates == 1
    assert result.btts.brier_improvement_ci is None
    assert result.btts.log_loss_improvement_ci is None


def test_bootstrap_is_deterministic_for_same_seed():
    rows = [fixture(i, i // 2, actual="HOME" if i % 3 else "AWAY") for i in range(40)]
    first = assess_reliability(report(rows), bootstrap_replicates=150, bootstrap_seed=42)
    second = assess_reliability(report(rows), bootstrap_replicates=150, bootstrap_seed=42)
    assert first == second


def test_bootstrap_and_calibration_configuration_are_validated():
    with pytest.raises(ValueError, match="BOOTSTRAP_REPLICATES_MUST_BE_AT_LEAST_100"):
        assess_reliability(report([fixture(1, 1)]), bootstrap_replicates=99)
    with pytest.raises(ValueError, match="CALIBRATION_BIN_COUNT_INVALID"):
        assess_reliability(report([fixture(1, 1)]), calibration_bins=1)
