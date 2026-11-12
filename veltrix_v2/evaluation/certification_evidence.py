"""Evidence derivation primitives for VELTRIX V2 certification.

All counts and financial metrics in this module are derived from evaluator
outputs, the immutable prospective ledger, and raw OddsSnapshot records.
This module intentionally does not accept caller-supplied counts or pass flags.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.multi_competition_walk_forward import (
    MultiCompetitionWalkForwardEvaluation,
)
from veltrix_v2.evaluation.paper_ledger import PaperLedger
from veltrix_v2.evaluation.roi import MarketPerformance, evaluate_roi

_EXPECTED_SELECTIONS = {
    "1X2": frozenset({"HOME", "DRAW", "AWAY"}),
    "BTTS": frozenset({"YES", "NO"}),
    "TOTALS": frozenset({"OVER", "UNDER"}),
}


@dataclass(frozen=True, slots=True)
class TimestampedOddsCoverage:
    market: str
    eligible_fixture_ids: tuple[str, ...]
    covered_fixture_ids: tuple[str, ...]
    eligible_fixture_count: int
    covered_fixture_count: int
    coverage: Decimal | None


@dataclass(frozen=True, slots=True)
class DerivedMarketEvidence:
    """Computed evidence; no caller-provided metric or pass/fail fields."""

    market: str
    walk_forward_matches: int
    prospective_settled_selections: int
    distinct_dates: int
    timestamped_odds: TimestampedOddsCoverage
    roi_performance: MarketPerformance


def _eligible_ids(report: MultiCompetitionWalkForwardEvaluation) -> tuple[str, ...]:
    ids = tuple(
        fixture_id
        for scope in report.scope_reports
        for fold in scope.folds
        for fixture_id in fold.eligible_fixture_ids
    )
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("CERTIFICATION_WALK_FORWARD_ELIGIBLE_FIXTURES_INVALID")
    return ids


def _walk_forward_sample_size(
    report: MultiCompetitionWalkForwardEvaluation, market: str
) -> int:
    aggregate = {
        "1X2": report.aggregate_1x2,
        "BTTS": report.aggregate_btts,
        "TOTALS": report.aggregate_totals,
    }[market]
    if aggregate is None:
        return 0
    size = aggregate.sample_size
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError("CERTIFICATION_WALK_FORWARD_SAMPLE_SIZE_INVALID")
    return size


def derive_timestamped_odds_coverage(
    eligible_fixture_ids: Iterable[str],
    snapshots: Iterable[OddsSnapshot],
    *,
    market: str,
) -> TimestampedOddsCoverage:
    """Count fixtures with at least one complete, point-in-time quote group.

    A group is complete only when every market selection is present for the
    same fixture, source, bookmaker, line, capture time and kickoff, and every
    quote has a provider quote timestamp strictly before kickoff and no later
    than local capture. Partial groups never count toward coverage.
    """
    canonical = "TOTALS" if market == "OVER_UNDER" else market
    expected = _EXPECTED_SELECTIONS.get(canonical)
    if expected is None:
        raise ValueError("CERTIFICATION_ODDS_MARKET_UNSUPPORTED")

    eligible = tuple(eligible_fixture_ids)
    if not eligible or len(eligible) != len(set(eligible)):
        raise ValueError("CERTIFICATION_ODDS_ELIGIBLE_FIXTURES_INVALID")
    eligible_set = set(eligible)

    groups: dict[tuple[object, ...], dict[str, OddsSnapshot]] = {}
    seen_snapshot_ids: set[str] = set()
    for row in snapshots:
        if not isinstance(row, OddsSnapshot):
            raise ValueError("CERTIFICATION_ODDS_SNAPSHOT_TYPE_INVALID")
        row_market = "TOTALS" if row.market.upper() == "OVER_UNDER" else row.market.upper()
        if row_market != canonical or row.fixture_id not in eligible_set:
            continue
        if row.snapshot_id in seen_snapshot_ids:
            raise ValueError("CERTIFICATION_ODDS_DUPLICATE_SNAPSHOT_ID")
        seen_snapshot_ids.add(row.snapshot_id)
        if row.provider_quote_at is None:
            continue
        if not (row.provider_quote_at < row.kickoff_at and row.provider_quote_at <= row.captured_at < row.kickoff_at):
            continue
        key = (
            row.fixture_id, row.source_id, row.bookmaker_id, row_market,
            row.line, row.captured_at, row.kickoff_at,
        )
        group = groups.setdefault(key, {})
        selection = row.selection.upper()
        if selection in group:
            raise ValueError("CERTIFICATION_ODDS_DUPLICATE_SELECTION")
        group[selection] = row

    covered: set[str] = set()
    for key, group in groups.items():
        fixture_id = key[0]
        if frozenset(group) == expected:
            covered.add(str(fixture_id))

    covered_ids = tuple(sorted(covered))
    return TimestampedOddsCoverage(
        market=canonical,
        eligible_fixture_ids=eligible,
        covered_fixture_ids=covered_ids,
        eligible_fixture_count=len(eligible),
        covered_fixture_count=len(covered_ids),
        coverage=Decimal(len(covered_ids)) / Decimal(len(eligible)) if eligible else None,
    )


def derive_market_evidence(
    walk_forward: MultiCompetitionWalkForwardEvaluation,
    paper_ledger: PaperLedger,
    odds_snapshots: Iterable[OddsSnapshot],
    *,
    market: str,
    bootstrap_draws: int = 2000,
    bootstrap_seed: int = 20261112,
) -> DerivedMarketEvidence:
    """Derive every market-level certification metric from source records."""
    canonical = "TOTALS" if market == "OVER_UNDER" else market
    if canonical not in _EXPECTED_SELECTIONS:
        raise ValueError("CERTIFICATION_MARKET_UNSUPPORTED")
    if not isinstance(walk_forward, MultiCompetitionWalkForwardEvaluation):
        raise ValueError("CERTIFICATION_WALK_FORWARD_REPORT_REQUIRED")
    if not isinstance(paper_ledger, PaperLedger):
        raise ValueError("CERTIFICATION_PAPER_LEDGER_REQUIRED")

    eligible_ids = _eligible_ids(walk_forward)
    counts = paper_ledger.counts_for_market(canonical)
    settlements = paper_ledger.settlements_for_market(canonical)
    # ROI is recomputed from the authoritative ledger settlements. No supplied
    # MarketPerformance object is accepted as certification input.
    roi_report = evaluate_roi(
        settlements,
        bootstrap_draws=bootstrap_draws,
        bootstrap_seed=bootstrap_seed,
    )
    performance = next(
        (row for row in roi_report.markets if row.market in {canonical, "OVER_UNDER" if canonical == "TOTALS" else canonical}),
        None,
    )
    if performance is None:
        # An empty ledger is explicit zero evidence, not a missing report.
        performance = MarketPerformance(
            market=canonical,
            total_bets=0, wins=0, losses=0, pushes=0, voids=0,
            decisive_bets=0, settled_bets=0,
            win_rate=None, win_rate_ci_95=None,
            settled_turnover=Decimal("0"), gross_return=Decimal("0"),
            net_profit=Decimal("0"), roi=None, roi_ci_95=None,
            roi_ci_method="unavailable_insufficient_match_dates",
        )
    odds = derive_timestamped_odds_coverage(
        eligible_ids, odds_snapshots, market=canonical
    )
    return DerivedMarketEvidence(
        market=canonical,
        walk_forward_matches=_walk_forward_sample_size(walk_forward, canonical),
        prospective_settled_selections=counts.settled_count,
        distinct_dates=counts.distinct_settled_dates,
        timestamped_odds=odds,
        roi_performance=performance,
    )

