from decimal import Decimal

import pytest

from veltrix_v2.evaluation.certification import (
    MarketCertificationEvidence,
    PredictionMarketEvidence,
    certify_prediction_publication,
    certify_release,
)


def evidence(market, **overrides):
    values = dict(
        market=market,
        walk_forward_matches=1000,
        prospective_settled_selections=300,
        distinct_dates=90,
        timestamped_odds_coverage=Decimal("0.98"),
        net_roi=Decimal("0.04"),
        roi_ci95_lower=Decimal("0.01"),
        roi_ci_method="date_block_bootstrap_by_match_date",
        source_approved=True,
        point_in_time_validated=True,
    )
    values.update(overrides)
    return MarketCertificationEvidence(**values)


def test_all_gates_pass_only_with_complete_evidence():
    result = certify_release(
        [evidence("1X2"), evidence("BTTS"), evidence("TOTALS")],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )
    assert result.passed
    assert all(row.passed for row in result.markets)
    assert result.global_failures == ()


def test_each_market_has_independent_failure_reasons():
    result = certify_release(
        [
            evidence("1X2"),
            evidence("BTTS", walk_forward_matches=999),
            evidence("TOTALS", timestamped_odds_coverage=Decimal("0.9799")),
        ],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )
    assert not result.passed
    failures = {row.market: row.failed_gates for row in result.markets}
    assert "WALK_FORWARD_SAMPLE_BELOW_1000" in failures["BTTS"]
    assert "TIMESTAMPED_ODDS_COVERAGE_BELOW_98_PERCENT" in failures["TOTALS"]


def test_nonpositive_roi_lower_bound_blocks_certification():
    result = certify_release(
        [evidence("1X2", roi_ci95_lower=Decimal("-0.001")),
         evidence("BTTS"), evidence("TOTALS")],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )
    assert not result.passed
    assert "ROI_LOWER_95_PERCENT_BOUND_NOT_POSITIVE" in result.markets[0].failed_gates


def test_iid_bootstrap_is_not_accepted_for_release():
    result = certify_release(
        [evidence("1X2", roi_ci_method="iid_bet_row_bootstrap"),
         evidence("BTTS"), evidence("TOTALS")],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )
    assert not result.passed
    assert "ROI_INTERVAL_NOT_DATE_BLOCK_BOOTSTRAP" in result.markets[0].failed_gates


def test_bookmaker_brier_and_logloss_are_both_mandatory():
    result = certify_release(
        [evidence("1X2"), evidence("BTTS"), evidence("TOTALS")],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=False,
    )
    assert not result.passed
    assert result.global_failures == ("1X2_DOES_NOT_BEAT_BOOKMAKER_LOG_LOSS",)


def test_duplicate_or_missing_market_evidence_is_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_MARKET"):
        certify_release(
            [evidence("1X2"), evidence("1X2"), evidence("TOTALS")],
            one_x_two_beats_bookmaker_brier=True,
            one_x_two_beats_bookmaker_log_loss=True,
        )
    with pytest.raises(ValueError, match="EXACTLY"):
        certify_release(
            [evidence("1X2"), evidence("BTTS")],
            one_x_two_beats_bookmaker_brier=True,
            one_x_two_beats_bookmaker_log_loss=True,
        )


def test_unapproved_source_and_missing_point_in_time_validation_block():
    result = certify_release(
        [evidence("1X2", source_approved=False, point_in_time_validated=False),
         evidence("BTTS"), evidence("TOTALS")],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )
    assert not result.passed
    assert "SOURCE_NOT_APPROVED" in result.markets[0].failed_gates
    assert "POINT_IN_TIME_VALIDATION_MISSING" in result.markets[0].failed_gates


def test_invalid_coverage_and_sample_types_are_rejected():
    with pytest.raises(ValueError, match="ODDS_COVERAGE_OUT_OF_RANGE"):
        evidence("1X2", timestamped_odds_coverage=Decimal("1.01"))
    with pytest.raises(ValueError, match="INVALID_WALK_FORWARD_MATCHES"):
        evidence("1X2", walk_forward_matches=True)


def test_source_approval_flags_must_be_boolean():
    with pytest.raises(ValueError, match="MUST_BE_BOOLEAN"):
        evidence("1X2", source_approved="yes")



def test_prediction_publication_gate_does_not_require_value_bet_evidence():
    result = certify_prediction_publication([
        PredictionMarketEvidence(
            market=market, walk_forward_matches=1000,
            source_approved=True, point_in_time_validated=True,
            leakage_tests_passed=True, calibration_passed=True,
        )
        for market in ("1X2", "BTTS", "TOTALS")
    ])
    assert result.passed
    assert all(item.passed for item in result.markets)


def test_prediction_publication_gate_rejects_missing_model_quality_evidence():
    result = certify_prediction_publication([
        PredictionMarketEvidence(
            market="1X2", walk_forward_matches=1000,
            source_approved=True, point_in_time_validated=True,
            leakage_tests_passed=True, calibration_passed=True,
        ),
        PredictionMarketEvidence(
            market="BTTS", walk_forward_matches=999,
            source_approved=True, point_in_time_validated=False,
            leakage_tests_passed=False, calibration_passed=False,
        ),
        PredictionMarketEvidence(
            market="TOTALS", walk_forward_matches=1000,
            source_approved=True, point_in_time_validated=True,
            leakage_tests_passed=True, calibration_passed=True,
        ),
    ])
    assert not result.passed
    btts = next(item for item in result.markets if item.market == "BTTS")
    assert "PREDICTION_WALK_FORWARD_SAMPLE_BELOW_1000" in btts.failed_gates
    assert "PREDICTION_POINT_IN_TIME_VALIDATION_MISSING" in btts.failed_gates
    assert "PREDICTION_LEAKAGE_TESTS_FAILED" in btts.failed_gates
    assert "PREDICTION_CALIBRATION_NOT_PASSED" in btts.failed_gates



def test_certification_objects_reject_internally_conflicting_pass_flags():
    from veltrix_v2.evaluation.certification import (
        CertificationResult, PredictionReleaseCertification, ReleaseCertification,
    )

    good = tuple(CertificationResult(market, True, ()) for market in ("1X2", "BTTS", "TOTALS"))
    with pytest.raises(ValueError, match="BRIER_FAILURE_NOT_RECORDED"):
        ReleaseCertification(
            passed=True, markets=good,
            one_x_two_beats_bookmaker_brier=False,
            one_x_two_beats_bookmaker_log_loss=True,
            global_failures=(),
            evidence=tuple(evidence(market) for market in ("1X2", "BTTS", "TOTALS")),
        )
    bad_market = CertificationResult("BTTS", False, ("PREDICTION_CALIBRATION_NOT_PASSED",))
    with pytest.raises(ValueError, match="STATUS_CONFLICTS_WITH_EVIDENCE"):
        PredictionReleaseCertification(
            passed=True,
            markets=(
                CertificationResult("1X2", True, ()),
                bad_market,
                CertificationResult("TOTALS", True, ()),
            ),
            evidence=(
                PredictionMarketEvidence("1X2", 1000, True, True, True, True),
                PredictionMarketEvidence("BTTS", 999, True, True, True, False),
                PredictionMarketEvidence("TOTALS", 1000, True, True, True, True),
            ),
        )
