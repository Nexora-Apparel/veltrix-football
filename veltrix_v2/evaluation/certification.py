"""Strict, fail-closed V2 release certification gates.

This module validates independently produced evidence. It does not run
backtests, create selections, settle bets, or certify from synthetic fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

REQUIRED_MARKETS = ("1X2", "BTTS", "TOTALS")
MIN_WALK_FORWARD_MATCHES = 1000
MIN_PROSPECTIVE_SETTLED = 300
MIN_DISTINCT_DATES = 90
MIN_ODDS_COVERAGE = Decimal("0.98")
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class MarketCertificationEvidence:
    market: str
    walk_forward_matches: int
    prospective_settled_selections: int
    distinct_dates: int
    timestamped_odds_coverage: Decimal
    net_roi: Decimal
    roi_ci95_lower: Decimal
    roi_ci_method: str
    source_approved: bool
    point_in_time_validated: bool

    def __post_init__(self) -> None:
        if self.market not in REQUIRED_MARKETS:
            raise ValueError("CERTIFICATION_UNSUPPORTED_MARKET")
        for field in (
            "walk_forward_matches", "prospective_settled_selections", "distinct_dates"
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"CERTIFICATION_INVALID_{field.upper()}")
        for field in ("timestamped_odds_coverage", "net_roi", "roi_ci95_lower"):
            value = getattr(self, field)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"CERTIFICATION_INVALID_{field.upper()}")
        if not ZERO <= self.timestamped_odds_coverage <= Decimal("1"):
            raise ValueError("CERTIFICATION_ODDS_COVERAGE_OUT_OF_RANGE")
        if type(self.source_approved) is not bool or type(self.point_in_time_validated) is not bool:
            raise ValueError("CERTIFICATION_SOURCE_AND_POINT_IN_TIME_FLAGS_MUST_BE_BOOLEAN")
        if not isinstance(self.roi_ci_method, str) or not self.roi_ci_method.strip():
            raise ValueError("CERTIFICATION_ROI_CI_METHOD_REQUIRED")


@dataclass(frozen=True, slots=True)
class CertificationResult:
    market: str
    passed: bool
    failed_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.market not in REQUIRED_MARKETS:
            raise ValueError("CERTIFICATION_RESULT_UNSUPPORTED_MARKET")
        if type(self.passed) is not bool:
            raise ValueError("CERTIFICATION_RESULT_PASSED_MUST_BE_BOOLEAN")
        gates = tuple(self.failed_gates)
        if any(not isinstance(gate, str) or not gate.strip() for gate in gates):
            raise ValueError("CERTIFICATION_RESULT_FAILURE_CODES_INVALID")
        object.__setattr__(self, "failed_gates", gates)
        if self.passed != (not gates):
            raise ValueError("CERTIFICATION_RESULT_STATUS_CONFLICTS_WITH_FAILURES")


@dataclass(frozen=True, slots=True)
class ReleaseCertification:
    passed: bool
    markets: tuple[CertificationResult, ...]
    one_x_two_beats_bookmaker_brier: bool
    one_x_two_beats_bookmaker_log_loss: bool
    global_failures: tuple[str, ...]
    evidence: tuple[MarketCertificationEvidence, ...] = ()

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise ValueError("RELEASE_CERTIFICATION_STATUS_MUST_BE_BOOLEAN")
        if type(self.one_x_two_beats_bookmaker_brier) is not bool or type(self.one_x_two_beats_bookmaker_log_loss) is not bool:
            raise ValueError("RELEASE_CERTIFICATION_BENCHMARK_FLAGS_MUST_BE_BOOLEAN")
        markets = tuple(self.markets)
        if any(not isinstance(row, CertificationResult) for row in markets):
            raise ValueError("RELEASE_CERTIFICATION_MARKET_RESULT_TYPE_INVALID")
        if len(markets) != len(REQUIRED_MARKETS) or {row.market for row in markets} != set(REQUIRED_MARKETS):
            raise ValueError("RELEASE_CERTIFICATION_REQUIRES_EXACTLY_1X2_BTTS_TOTALS")
        failures = tuple(self.global_failures)
        if any(not isinstance(item, str) or not item.strip() for item in failures):
            raise ValueError("RELEASE_CERTIFICATION_GLOBAL_FAILURES_INVALID")
        object.__setattr__(self, "markets", markets)
        object.__setattr__(self, "global_failures", failures)
        evidence = tuple(self.evidence)
        if any(not isinstance(row, MarketCertificationEvidence) for row in evidence):
            raise ValueError("RELEASE_CERTIFICATION_EVIDENCE_TYPE_INVALID")
        if len(evidence) != len(REQUIRED_MARKETS) or {row.market for row in evidence} != set(REQUIRED_MARKETS):
            raise ValueError("RELEASE_CERTIFICATION_REQUIRES_COMPLETE_MARKET_EVIDENCE")
        object.__setattr__(self, "evidence", evidence)
        expected_by_market = {}
        for row in evidence:
            failed = []
            if row.walk_forward_matches < MIN_WALK_FORWARD_MATCHES: failed.append("WALK_FORWARD_SAMPLE_BELOW_1000")
            if row.prospective_settled_selections < MIN_PROSPECTIVE_SETTLED: failed.append("PROSPECTIVE_SAMPLE_BELOW_300")
            if row.distinct_dates < MIN_DISTINCT_DATES: failed.append("DISTINCT_DATES_BELOW_90")
            if row.timestamped_odds_coverage < MIN_ODDS_COVERAGE: failed.append("TIMESTAMPED_ODDS_COVERAGE_BELOW_98_PERCENT")
            if row.net_roi <= ZERO: failed.append("NET_ROI_NOT_POSITIVE")
            if row.roi_ci95_lower <= ZERO: failed.append("ROI_LOWER_95_PERCENT_BOUND_NOT_POSITIVE")
            if row.roi_ci_method != "date_block_bootstrap_by_match_date": failed.append("ROI_INTERVAL_NOT_DATE_BLOCK_BOOTSTRAP")
            if not row.source_approved: failed.append("SOURCE_NOT_APPROVED")
            if not row.point_in_time_validated: failed.append("POINT_IN_TIME_VALIDATION_MISSING")
            expected_by_market[row.market] = CertificationResult(row.market, not failed, tuple(failed))
        if {row.market: row for row in markets} != expected_by_market:
            raise ValueError("RELEASE_CERTIFICATION_MARKET_RESULTS_DO_NOT_MATCH_EVIDENCE")
        if not self.one_x_two_beats_bookmaker_brier and "1X2_DOES_NOT_BEAT_BOOKMAKER_BRIER" not in failures:
            raise ValueError("RELEASE_CERTIFICATION_BRIER_FAILURE_NOT_RECORDED")
        if self.one_x_two_beats_bookmaker_brier and "1X2_DOES_NOT_BEAT_BOOKMAKER_BRIER" in failures:
            raise ValueError("RELEASE_CERTIFICATION_BRIER_FAILURE_CONFLICT")
        if not self.one_x_two_beats_bookmaker_log_loss and "1X2_DOES_NOT_BEAT_BOOKMAKER_LOG_LOSS" not in failures:
            raise ValueError("RELEASE_CERTIFICATION_LOG_LOSS_FAILURE_NOT_RECORDED")
        if self.one_x_two_beats_bookmaker_log_loss and "1X2_DOES_NOT_BEAT_BOOKMAKER_LOG_LOSS" in failures:
            raise ValueError("RELEASE_CERTIFICATION_LOG_LOSS_FAILURE_CONFLICT")
        expected_pass = all(row.passed for row in markets) and not failures
        if self.passed != expected_pass:
            raise ValueError("RELEASE_CERTIFICATION_STATUS_CONFLICTS_WITH_EVIDENCE")


def certify_release(
    evidence: Iterable[MarketCertificationEvidence],
    *,
    one_x_two_beats_bookmaker_brier: bool,
    one_x_two_beats_bookmaker_log_loss: bool,
) -> ReleaseCertification:
    if type(one_x_two_beats_bookmaker_brier) is not bool or type(one_x_two_beats_bookmaker_log_loss) is not bool:
        raise ValueError("CERTIFICATION_BENCHMARK_FLAGS_MUST_BE_BOOLEAN")
    rows = tuple(evidence)
    if any(not isinstance(row, MarketCertificationEvidence) for row in rows):
        raise ValueError("CERTIFICATION_EVIDENCE_TYPE_INVALID")
    by_market = {row.market: row for row in rows}
    if len(by_market) != len(rows):
        raise ValueError("CERTIFICATION_DUPLICATE_MARKET_EVIDENCE")
    if set(by_market) != set(REQUIRED_MARKETS):
        raise ValueError("CERTIFICATION_REQUIRES_EXACTLY_1X2_BTTS_TOTALS")

    results: list[CertificationResult] = []
    for market in REQUIRED_MARKETS:
        row = by_market[market]
        failures: list[str] = []
        if row.walk_forward_matches < MIN_WALK_FORWARD_MATCHES:
            failures.append("WALK_FORWARD_SAMPLE_BELOW_1000")
        if row.prospective_settled_selections < MIN_PROSPECTIVE_SETTLED:
            failures.append("PROSPECTIVE_SAMPLE_BELOW_300")
        if row.distinct_dates < MIN_DISTINCT_DATES:
            failures.append("DISTINCT_DATES_BELOW_90")
        if row.timestamped_odds_coverage < MIN_ODDS_COVERAGE:
            failures.append("TIMESTAMPED_ODDS_COVERAGE_BELOW_98_PERCENT")
        if row.net_roi <= ZERO:
            failures.append("NET_ROI_NOT_POSITIVE")
        if row.roi_ci95_lower <= ZERO:
            failures.append("ROI_LOWER_95_PERCENT_BOUND_NOT_POSITIVE")
        if row.roi_ci_method != "date_block_bootstrap_by_match_date":
            failures.append("ROI_INTERVAL_NOT_DATE_BLOCK_BOOTSTRAP")
        if not row.source_approved:
            failures.append("SOURCE_NOT_APPROVED")
        if not row.point_in_time_validated:
            failures.append("POINT_IN_TIME_VALIDATION_MISSING")
        results.append(CertificationResult(
            market=market,
            passed=not failures,
            failed_gates=tuple(failures),
        ))

    global_failures: list[str] = []
    if not one_x_two_beats_bookmaker_brier:
        global_failures.append("1X2_DOES_NOT_BEAT_BOOKMAKER_BRIER")
    if not one_x_two_beats_bookmaker_log_loss:
        global_failures.append("1X2_DOES_NOT_BEAT_BOOKMAKER_LOG_LOSS")
    all_markets_pass = all(result.passed for result in results)
    return ReleaseCertification(
        passed=all_markets_pass and not global_failures,
        markets=tuple(results),
        one_x_two_beats_bookmaker_brier=bool(one_x_two_beats_bookmaker_brier),
        one_x_two_beats_bookmaker_log_loss=bool(one_x_two_beats_bookmaker_log_loss),
        global_failures=tuple(global_failures),
        evidence=rows,
    )



@dataclass(frozen=True, slots=True)
class PredictionMarketEvidence:
    """Evidence required to publish model forecasts without enabling betting."""
    market: str
    walk_forward_matches: int
    source_approved: bool
    point_in_time_validated: bool
    leakage_tests_passed: bool
    calibration_passed: bool

    def __post_init__(self) -> None:
        if self.market not in REQUIRED_MARKETS:
            raise ValueError("PREDICTION_CERTIFICATION_UNSUPPORTED_MARKET")
        if (
            isinstance(self.walk_forward_matches, bool)
            or not isinstance(self.walk_forward_matches, int)
            or self.walk_forward_matches < 0
        ):
            raise ValueError("PREDICTION_CERTIFICATION_INVALID_WALK_FORWARD_MATCHES")
        for field in (
            "source_approved", "point_in_time_validated",
            "leakage_tests_passed", "calibration_passed",
        ):
            if type(getattr(self, field)) is not bool:
                raise ValueError("PREDICTION_CERTIFICATION_FLAGS_MUST_BE_BOOLEAN")


@dataclass(frozen=True, slots=True)
class PredictionReleaseCertification:
    passed: bool
    markets: tuple[CertificationResult, ...]
    evidence: tuple["PredictionMarketEvidence", ...] = ()

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise ValueError("PREDICTION_RELEASE_STATUS_MUST_BE_BOOLEAN")
        markets = tuple(self.markets)
        if any(not isinstance(row, CertificationResult) for row in markets):
            raise ValueError("PREDICTION_RELEASE_MARKET_RESULT_TYPE_INVALID")
        if len(markets) != len(REQUIRED_MARKETS) or {row.market for row in markets} != set(REQUIRED_MARKETS):
            raise ValueError("PREDICTION_RELEASE_REQUIRES_EXACTLY_1X2_BTTS_TOTALS")
        object.__setattr__(self, "markets", markets)
        evidence = tuple(self.evidence)
        if any(not isinstance(row, PredictionMarketEvidence) for row in evidence):
            raise ValueError("PREDICTION_RELEASE_EVIDENCE_TYPE_INVALID")
        if len(evidence) != len(REQUIRED_MARKETS) or {row.market for row in evidence} != set(REQUIRED_MARKETS):
            raise ValueError("PREDICTION_RELEASE_REQUIRES_COMPLETE_MARKET_EVIDENCE")
        object.__setattr__(self, "evidence", evidence)
        expected_by_market = {}
        for row in evidence:
            failed = []
            if row.walk_forward_matches < MIN_WALK_FORWARD_MATCHES: failed.append("PREDICTION_WALK_FORWARD_SAMPLE_BELOW_1000")
            if not row.source_approved: failed.append("PREDICTION_SOURCE_NOT_APPROVED")
            if not row.point_in_time_validated: failed.append("PREDICTION_POINT_IN_TIME_VALIDATION_MISSING")
            if not row.leakage_tests_passed: failed.append("PREDICTION_LEAKAGE_TESTS_FAILED")
            if not row.calibration_passed: failed.append("PREDICTION_CALIBRATION_NOT_PASSED")
            expected_by_market[row.market] = CertificationResult(row.market, not failed, tuple(failed))
        if {row.market: row for row in markets} != expected_by_market:
            raise ValueError("PREDICTION_RELEASE_MARKET_RESULTS_DO_NOT_MATCH_EVIDENCE")
        if self.passed != all(row.passed for row in markets):
            raise ValueError("PREDICTION_RELEASE_STATUS_CONFLICTS_WITH_EVIDENCE")


def certify_prediction_publication(
    evidence: Iterable[PredictionMarketEvidence],
) -> PredictionReleaseCertification:
    """Gate forecast publication independently from value-bet certification.

    This gate requires chronological out-of-sample volume, approved sources,
    point-in-time integrity, leakage checks and calibration. It does not require
    prospective bet volume, positive ROI, odds coverage or bookmaker superiority;
    those remain mandatory in certify_release before value betting is enabled.
    """
    rows = tuple(evidence)
    if any(not isinstance(row, PredictionMarketEvidence) for row in rows):
        raise ValueError("PREDICTION_CERTIFICATION_EVIDENCE_TYPE_INVALID")
    by_market = {row.market: row for row in rows}
    if len(by_market) != len(rows):
        raise ValueError("PREDICTION_CERTIFICATION_DUPLICATE_MARKET")
    if set(by_market) != set(REQUIRED_MARKETS):
        raise ValueError("PREDICTION_CERTIFICATION_REQUIRES_EXACTLY_1X2_BTTS_TOTALS")

    results: list[CertificationResult] = []
    for market in REQUIRED_MARKETS:
        row = by_market[market]
        failures: list[str] = []
        if row.walk_forward_matches < MIN_WALK_FORWARD_MATCHES:
            failures.append("PREDICTION_WALK_FORWARD_SAMPLE_BELOW_1000")
        if not row.source_approved:
            failures.append("PREDICTION_SOURCE_NOT_APPROVED")
        if not row.point_in_time_validated:
            failures.append("PREDICTION_POINT_IN_TIME_VALIDATION_MISSING")
        if not row.leakage_tests_passed:
            failures.append("PREDICTION_LEAKAGE_TESTS_FAILED")
        if not row.calibration_passed:
            failures.append("PREDICTION_CALIBRATION_NOT_PASSED")
        results.append(CertificationResult(
            market=market,
            passed=not failures,
            failed_gates=tuple(failures),
        ))
    return PredictionReleaseCertification(
        passed=all(item.passed for item in results),
        markets=tuple(results),
        evidence=rows,
    )
