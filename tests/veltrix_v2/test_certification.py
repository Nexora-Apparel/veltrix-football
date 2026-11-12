from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from veltrix_v2.evaluation.roi import evaluate_roi
from veltrix_v2.evaluation.settlement import MarketBet, MatchResult, settle_market_bet

from veltrix_v2.evaluation.certification import (
    MarketCertificationEvidence,
    PredictionMarketEvidence,
    certify_prediction_publication,
    _certify_release_from_derived_evidence,
)


def roi_performance(market):
    rows = []
    for index in range(300):
        fixture_id = f"{market.lower()}-{index}"
        match_day = date(2026, 1, 1) + timedelta(days=index % 90)
        if market == "1X2":
            selection, line, home, away = "HOME", None, 2, 0
        elif market == "BTTS":
            selection, line, home, away = "YES", None, 2, 1
        else:
            selection, line, home, away = "OVER", Decimal("2.5"), 2, 1
        bet = MarketBet(
            fixture_id=fixture_id, market=market, selection=selection,
            decimal_odds=Decimal("2.0"), stake=Decimal("1"),
            line=line,
        )
        result = MatchResult(
            fixture_id=fixture_id, status="COMPLETED",
            home_goals_regulation=home, away_goals_regulation=away,
            match_date=match_day,
            match_date_source_observation_id=f"obs-{fixture_id}",
        )
        rows.append(settle_market_bet(bet, result))
    report = evaluate_roi(rows, bootstrap_draws=100)
    return next(item for item in report.markets if item.market == market)


def evidence(market, **overrides):
    values = dict(
        market=market,
        walk_forward_matches=1000,
        prospective_settled_selections=300,
        distinct_dates=90,
        timestamped_odds_coverage=Decimal("0.98"),
        roi_performance=roi_performance(market),
        source_approved=True,
        point_in_time_validated=True,
    )
    values.update(overrides)
    return MarketCertificationEvidence(**values)


def test_all_gates_pass_only_with_complete_evidence():
    result = _certify_release_from_derived_evidence(
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
        [evidence("1X2", roi_performance=replace(roi_performance("1X2"), roi_ci_95=(Decimal("-0.001"), Decimal("0.05")))),
         evidence("BTTS"), evidence("TOTALS")],
        one_x_two_beats_bookmaker_brier=True,
        one_x_two_beats_bookmaker_log_loss=True,
    )
    assert not result.passed
    assert "ROI_LOWER_95_PERCENT_BOUND_NOT_POSITIVE" in result.markets[0].failed_gates


def test_iid_bootstrap_is_not_accepted_for_release():
    result = certify_release(
        [evidence("1X2", roi_performance=replace(roi_performance("1X2"), roi_ci_method="iid_bet_row_bootstrap")),
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



def test_prediction_publication_rejects_caller_supplied_market_flags():
    forged = [
        PredictionMarketEvidence(
            market=market, walk_forward_matches=1000,
            source_approved=True, point_in_time_validated=True,
            leakage_tests_passed=True, calibration_passed=True,
        )
        for market in ("1X2", "BTTS", "TOTALS")
    ]
    with pytest.raises(ValueError, match="WALK_FORWARD_REPORT_REQUIRED"):
        certify_prediction_publication(forged, (), ())


def test_prediction_publication_requires_typed_walk_forward_and_source_records():
    with pytest.raises(ValueError, match="WALK_FORWARD_REPORT_REQUIRED"):
        certify_prediction_publication(
            {"aggregate_1x2": {"sample_size": 1000}},
            (),
            (),
        )


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
    with pytest.raises(ValueError, match="MARKET_RESULTS_DO_NOT_MATCH_EVIDENCE"):
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



def test_certification_objects_cannot_be_forged_without_gate_evidence():
    from veltrix_v2.evaluation.certification import (
        CertificationResult, PredictionReleaseCertification, ReleaseCertification,
    )

    claimed_pass = tuple(
        CertificationResult(market, True, ())
        for market in ("1X2", "BTTS", "TOTALS")
    )
    with pytest.raises(ValueError, match="REQUIRES_COMPLETE_MARKET_EVIDENCE"):
        PredictionReleaseCertification(passed=True, markets=claimed_pass)
    with pytest.raises(ValueError, match="REQUIRES_COMPLETE_MARKET_EVIDENCE"):
        ReleaseCertification(
            passed=True,
            markets=claimed_pass,
            one_x_two_beats_bookmaker_brier=True,
            one_x_two_beats_bookmaker_log_loss=True,
            global_failures=(),
        )


def test_roi_certification_requires_market_matched_computed_performance():
    with pytest.raises(ValueError, match="PERFORMANCE_MARKET_MISMATCH"):
        evidence("1X2", roi_performance=roi_performance("BTTS"))
    with pytest.raises(ValueError, match="SETTLED_COUNT_MISMATCH"):
        evidence("1X2", prospective_settled_selections=299)
