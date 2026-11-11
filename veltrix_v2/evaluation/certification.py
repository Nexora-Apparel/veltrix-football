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
        if not isinstance(self.roi_ci_method, str) or not self.roi_ci_method.strip():
            raise ValueError("CERTIFICATION_ROI_CI_METHOD_REQUIRED")


@dataclass(frozen=True, slots=True)
class CertificationResult:
    market: str
    passed: bool
    failed_gates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReleaseCertification:
    passed: bool
    markets: tuple[CertificationResult, ...]
    one_x_two_beats_bookmaker_brier: bool
    one_x_two_beats_bookmaker_log_loss: bool
    global_failures: tuple[str, ...]


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
        if row.roi_ci_method != "chronological_block_bootstrap_by_match_date":
            failures.append("ROI_INTERVAL_NOT_MATCH_DATE_BLOCK_BOOTSTRAP")
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
    )
