"""Strict, fail-closed V2 release certification gates.

This module validates independently produced evidence. It does not run
backtests, create selections, settle bets, or certify from synthetic fixtures.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from veltrix_v2.evaluation.roi import MarketPerformance

REQUIRED_MARKETS = ("1X2", "BTTS", "TOTALS")
MIN_WALK_FORWARD_MATCHES = 1000
MIN_PROSPECTIVE_SETTLED = 300
MIN_DISTINCT_DATES = 90
MIN_ODDS_COVERAGE = Decimal("0.98")
ZERO = Decimal("0")
_CERTIFICATION_SEAL = object()


@dataclass(frozen=True, slots=True)
class MarketCertificationEvidence:
    market: str
    walk_forward_matches: int
    prospective_settled_selections: int
    distinct_dates: int
    timestamped_odds_coverage: Decimal
    roi_performance: MarketPerformance
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
        if not isinstance(self.timestamped_odds_coverage, Decimal) or not self.timestamped_odds_coverage.is_finite():
            raise ValueError("CERTIFICATION_INVALID_TIMESTAMPED_ODDS_COVERAGE")
        if not ZERO <= self.timestamped_odds_coverage <= Decimal("1"):
            raise ValueError("CERTIFICATION_ODDS_COVERAGE_OUT_OF_RANGE")
        if type(self.source_approved) is not bool or type(self.point_in_time_validated) is not bool:
            raise ValueError("CERTIFICATION_SOURCE_AND_POINT_IN_TIME_FLAGS_MUST_BE_BOOLEAN")
        if not isinstance(self.roi_performance, MarketPerformance):
            raise ValueError("CERTIFICATION_ROI_PERFORMANCE_EVIDENCE_REQUIRED")
        if self.roi_performance.market != self.market:
            raise ValueError("CERTIFICATION_ROI_PERFORMANCE_MARKET_MISMATCH")
        if self.roi_performance.settled_bets != self.prospective_settled_selections:
            raise ValueError("CERTIFICATION_ROI_SETTLED_COUNT_MISMATCH")


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


@dataclass(frozen=True, slots=True, init=False)
class ReleaseCertification:
    passed: bool
    markets: tuple[CertificationResult, ...]
    one_x_two_beats_bookmaker_brier: bool
    one_x_two_beats_bookmaker_log_loss: bool
    global_failures: tuple[str, ...]
    evidence: tuple[MarketCertificationEvidence, ...] = ()

    def __init__(
        self,
        passed: bool,
        markets: tuple[CertificationResult, ...],
        one_x_two_beats_bookmaker_brier: bool,
        one_x_two_beats_bookmaker_log_loss: bool,
        global_failures: tuple[str, ...],
        evidence: tuple[MarketCertificationEvidence, ...] = (),
        *,
        _seal: object | None = None,
    ) -> None:
        if _seal is not _CERTIFICATION_SEAL:
            raise ValueError("RELEASE_CERTIFICATION_INTERNAL_FACTORY_ONLY")
        for name, value in (
            ("passed", passed),
            ("markets", markets),
            ("one_x_two_beats_bookmaker_brier", one_x_two_beats_bookmaker_brier),
            ("one_x_two_beats_bookmaker_log_loss", one_x_two_beats_bookmaker_log_loss),
            ("global_failures", global_failures),
            ("evidence", evidence),
        ):
            object.__setattr__(self, name, value)
        self.__post_init__()

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
            if row.roi_performance.roi is None or row.roi_performance.roi <= ZERO: failed.append("NET_ROI_NOT_POSITIVE")
            if row.roi_performance.roi_ci_95 is None or row.roi_performance.roi_ci_95[0] <= ZERO: failed.append("ROI_LOWER_95_PERCENT_BOUND_NOT_POSITIVE")
            if row.roi_performance.roi_ci_method != "date_block_bootstrap_by_match_date": failed.append("ROI_INTERVAL_NOT_DATE_BLOCK_BOOTSTRAP")
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


def _certify_release_from_derived_evidence(
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
        if row.roi_performance.roi is None or row.roi_performance.roi <= ZERO:
            failures.append("NET_ROI_NOT_POSITIVE")
        if row.roi_performance.roi_ci_95 is None or row.roi_performance.roi_ci_95[0] <= ZERO:
            failures.append("ROI_LOWER_95_PERCENT_BOUND_NOT_POSITIVE")
        if row.roi_performance.roi_ci_method != "date_block_bootstrap_by_match_date":
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
        _seal=_CERTIFICATION_SEAL,
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


@dataclass(frozen=True, slots=True, init=False)
class PredictionReleaseCertification:
    passed: bool
    markets: tuple[CertificationResult, ...]
    evidence: tuple["PredictionMarketEvidence", ...] = ()

    def __init__(
        self,
        passed: bool,
        markets: tuple[CertificationResult, ...],
        evidence: tuple["PredictionMarketEvidence", ...] = (),
        *,
        _seal: object | None = None,
    ) -> None:
        if _seal is not _CERTIFICATION_SEAL:
            raise ValueError("PREDICTION_RELEASE_INTERNAL_FACTORY_ONLY")
        for name, value in (
            ("passed", passed),
            ("markets", markets),
            ("evidence", evidence),
        ):
            object.__setattr__(self, name, value)
        self.__post_init__()

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


def _certify_prediction_publication_from_derived_evidence(
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
        _seal=_CERTIFICATION_SEAL,
    )


def certify_prediction_publication(
    walk_forward: "MultiCompetitionWalkForwardEvaluation",
    observations: Iterable["TrainingObservationEvidence"],
    approvals: Iterable["SourceApproval"],
) -> PredictionReleaseCertification:
    """Certify prediction publication only from evaluator and source records.

    Sample sizes are read from the walk-forward aggregates. Source rights and
    availability are rechecked against every fold cutoff. Leakage is audited
    from fold identities and time windows. Calibration diagnostics are
    recomputed directly from each fold's held-out forecasts and outcomes.
    No caller-supplied metric counts or pass/fail flags are accepted.
    """
    from veltrix_v2.evaluation.binary_calibration import (
        HeldOutBinaryFold, diagnose_binary_calibration,
    )
    from veltrix_v2.evaluation.calibration import (
        HeldOutFold1X2, diagnose_1x2_calibration,
    )
    from veltrix_v2.evaluation.calibration_gate import evaluate_calibration_gate
    from veltrix_v2.evaluation.certification_evidence import (
        TrainingObservationEvidence,
        audit_walk_forward_integrity,
        audit_walk_forward_training_sources,
    )
    from veltrix_v2.evaluation.multi_competition_walk_forward import (
        MultiCompetitionWalkForwardEvaluation,
    )
    from veltrix_v2.quality.eligibility import SourceApproval

    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("PREDICTION_CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    observation_rows = tuple(observations)
    approval_rows = tuple(approvals)
    if any(not isinstance(row, TrainingObservationEvidence) for row in observation_rows):
        raise ValueError("PREDICTION_CERTIFICATION_SOURCE_RECORDS_REQUIRED")
    if any(not isinstance(row, SourceApproval) for row in approval_rows):
        raise ValueError("PREDICTION_CERTIFICATION_APPROVAL_RECORDS_REQUIRED")

    source_audit = audit_walk_forward_training_sources(
        walk_forward, observation_rows, approval_rows
    )
    integrity_audit = audit_walk_forward_integrity(walk_forward)

    folds_1x2 = []
    folds_btts = []
    folds_totals = []
    fold_number = 0
    for scope_report in walk_forward.scope_reports:
        for fold in scope_report.folds:
            fold_number += 1
            folds_1x2.append(HeldOutFold1X2(
                fold_number=fold_number,
                test_fixture_count=fold.test_fixture_count,
                forecasts=fold.forecasts_1x2,
                outcomes=fold.outcomes_1x2,
            ))
            folds_btts.append(HeldOutBinaryFold(
                fold_number=fold_number,
                market="BTTS",
                test_fixture_count=fold.test_fixture_count,
                forecasts=fold.btts_forecasts,
                outcomes=fold.btts_outcomes,
            ))
            folds_totals.append(HeldOutBinaryFold(
                fold_number=fold_number,
                market="TOTALS",
                test_fixture_count=fold.test_fixture_count,
                forecasts=fold.totals_forecasts,
                outcomes=fold.totals_outcomes,
            ))

    calibration_pass = {"1X2": False, "BTTS": False, "TOTALS": False}
    try:
        one_x_two_report = diagnose_1x2_calibration(folds_1x2)
        one_x_two_gates = evaluate_calibration_gate(one_x_two_report)
        calibration_pass["1X2"] = bool(one_x_two_gates) and all(row.passed for row in one_x_two_gates)
    except ValueError:
        pass
    for market, folds in (("BTTS", folds_btts), ("TOTALS", folds_totals)):
        try:
            report = diagnose_binary_calibration(folds)
            gates = evaluate_calibration_gate(report)
            calibration_pass[market] = len(gates) == 1 and gates[0].passed
        except ValueError:
            pass

    aggregate_samples = {
        "1X2": walk_forward.aggregate_1x2.sample_size if walk_forward.aggregate_1x2 else 0,
        "BTTS": walk_forward.aggregate_btts.sample_size if walk_forward.aggregate_btts else 0,
        "TOTALS": walk_forward.aggregate_totals.sample_size if walk_forward.aggregate_totals else 0,
    }
    derived = tuple(
        PredictionMarketEvidence(
            market=market,
            walk_forward_matches=aggregate_samples[market],
            source_approved=source_audit.passed,
            point_in_time_validated=source_audit.passed,
            leakage_tests_passed=integrity_audit.passed and source_audit.passed,
            calibration_passed=calibration_pass[market],
        )
        for market in REQUIRED_MARKETS
    )
    return _certify_prediction_publication_from_derived_evidence(derived)


def certify_release(
    walk_forward: "MultiCompetitionWalkForwardEvaluation",
    paper_ledger: "PaperLedger",
    odds_snapshots: Iterable["OddsSnapshot"],
    observations: Iterable["TrainingObservationEvidence"],
    approvals: Iterable["SourceApproval"],
    *,
    benchmark_source_id: str,
    benchmark_bookmaker_id: str,
) -> ReleaseCertification:
    """Certify value betting exclusively from evaluator, odds and ledger records.

    Market counts, ROI, odds coverage and source/point-in-time decisions are
    recomputed from the supplied immutable records. The bookmaker comparison is
    regenerated from raw 1X2 OddsSnapshot rows and must cover exactly the same
    fixture IDs as the model's 1X2 walk-forward sample.
    """
    from collections import defaultdict
    from decimal import Decimal

    from veltrix_v2.contracts.odds import OddsSnapshot
    from veltrix_v2.evaluation.benchmark_1x2 import compare_1x2_to_bookmaker
    from veltrix_v2.evaluation.certification_evidence import (
        TrainingObservationEvidence,
        audit_odds_snapshot_sources,
        audit_paper_ledger_sources,
        audit_walk_forward_integrity,
        audit_walk_forward_training_sources,
        derive_market_evidence,
    )
    from veltrix_v2.evaluation.multi_competition_walk_forward import (
        MultiCompetitionWalkForwardEvaluation,
    )
    from veltrix_v2.evaluation.odds_normalization import normalize_bookmaker_market
    from veltrix_v2.evaluation.paper_ledger import PaperLedger
    from veltrix_v2.quality.eligibility import SourceApproval

    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    if not isinstance(paper_ledger, PaperLedger):
        raise ValueError("CERTIFICATION_PAPER_LEDGER_REQUIRED")
    if not isinstance(benchmark_source_id, str) or not benchmark_source_id.strip():
        raise ValueError("CERTIFICATION_BENCHMARK_SOURCE_REQUIRED")
    if not isinstance(benchmark_bookmaker_id, str) or not benchmark_bookmaker_id.strip():
        raise ValueError("CERTIFICATION_BENCHMARK_BOOKMAKER_REQUIRED")
    snapshot_rows = tuple(odds_snapshots)
    observation_rows = tuple(observations)
    approval_rows = tuple(approvals)
    if any(not isinstance(row, OddsSnapshot) for row in snapshot_rows):
        raise ValueError("CERTIFICATION_ODDS_SNAPSHOT_TYPE_INVALID")
    if any(not isinstance(row, TrainingObservationEvidence) for row in observation_rows):
        raise ValueError("CERTIFICATION_SOURCE_OBSERVATION_RECORDS_REQUIRED")
    if any(not isinstance(row, SourceApproval) for row in approval_rows):
        raise ValueError("CERTIFICATION_SOURCE_APPROVAL_RECORDS_REQUIRED")

    training_audit = audit_walk_forward_training_sources(
        walk_forward, observation_rows, approval_rows
    )
    integrity_audit = audit_walk_forward_integrity(walk_forward)
    odds_audit = audit_odds_snapshot_sources(
        walk_forward, snapshot_rows, observation_rows, approval_rows
    )
    ledger_audit = audit_paper_ledger_sources(
        walk_forward, paper_ledger, observation_rows, approval_rows
    )
    sources_pass = (
        training_audit.passed and odds_audit.passed and ledger_audit.passed
    )
    point_in_time_pass = integrity_audit.passed and sources_pass

    eligible_ids = tuple(
        fixture_id
        for scope_report in walk_forward.scope_reports
        for fold in scope_report.folds
        for fixture_id in fold.eligible_fixture_ids
    )
    model_forecasts = tuple(
        forecast
        for scope_report in walk_forward.scope_reports
        for fold in scope_report.folds
        for forecast in fold.forecasts_1x2
    )
    model_outcomes = tuple(
        outcome
        for scope_report in walk_forward.scope_reports
        for fold in scope_report.folds
        for outcome in fold.outcomes_1x2
    )
    if not model_forecasts or not model_outcomes:
        raise ValueError("CERTIFICATION_1X2_WALK_FORWARD_FORECASTS_REQUIRED")
    model_fixture_ids = tuple(sorted(row.fixture_id for row in model_forecasts))

    bookmaker_groups = defaultdict(list)
    for snapshot in snapshot_rows:
        if (
            snapshot.source_id == benchmark_source_id
            and snapshot.bookmaker_id == benchmark_bookmaker_id
            and snapshot.market.upper() == "1X2"
        ):
            key = (
                snapshot.fixture_id, snapshot.source_id, snapshot.bookmaker_id,
                snapshot.market.upper(), snapshot.line, snapshot.captured_at,
                snapshot.kickoff_at,
            )
            bookmaker_groups[key].append(snapshot)
    normalized_bookmaker_rows = []
    for group in bookmaker_groups.values():
        try:
            normalized_bookmaker_rows.extend(normalize_bookmaker_market(group))
        except ValueError as exc:
            if "INCOMPLETE_SELECTION_SET" in str(exc):
                continue
            raise
    comparison = compare_1x2_to_bookmaker(
        model_forecasts,
        normalized_bookmaker_rows,
        model_outcomes,
        eligible_fixture_ids=eligible_ids,
    )
    if comparison.common_fixture_ids != model_fixture_ids:
        raise ValueError("CERTIFICATION_BOOKMAKER_SAMPLE_MUST_MATCH_MODEL_FIXTURES_EXACTLY")
    if comparison.common_sample_size != walk_forward.aggregate_1x2.sample_size:
        raise ValueError("CERTIFICATION_BOOKMAKER_SAMPLE_SIZE_MISMATCH")

    derived_rows = tuple(
        derive_market_evidence(
            walk_forward,
            paper_ledger,
            snapshot_rows,
            market=market,
        )
        for market in REQUIRED_MARKETS
    )
    market_evidence = tuple(
        MarketCertificationEvidence(
            market=row.market,
            walk_forward_matches=row.walk_forward_matches,
            prospective_settled_selections=row.prospective_settled_selections,
            distinct_dates=row.distinct_dates,
            timestamped_odds_coverage=row.timestamped_odds.coverage or Decimal("0"),
            roi_performance=row.roi_performance,
            source_approved=sources_pass,
            point_in_time_validated=point_in_time_pass,
        )
        for row in derived_rows
    )
    return _certify_release_from_derived_evidence(
        market_evidence,
        one_x_two_beats_bookmaker_brier=comparison.comparison.model_beats_brier,
        one_x_two_beats_bookmaker_log_loss=comparison.comparison.model_beats_log_loss,
    )
