"""Timestamped pre-kickoff odds completeness and coverage evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Sequence

from veltrix_v2.odds.contracts import ProviderOddsQuote
from veltrix_v2.odds.market_mapping import CanonicalMarket, CanonicalSelection, NormalizedOddsQuote


class OddsCoverageState(StrEnum):
    COVERED = "COVERED"
    MISSING = "MISSING"
    INCOMPLETE = "INCOMPLETE"
    STALE = "STALE"
    INVALID_TARGET = "INVALID_TARGET"


@dataclass(frozen=True, slots=True)
class OddsCoverageTarget:
    canonical_fixture_id: str
    market: CanonicalMarket
    kickoff_at_utc: datetime
    cutoff_at_utc: datetime
    required_selections: tuple[CanonicalSelection, ...]
    required_line: Decimal | None = None
    max_quote_age_seconds: int | None = None

    def __post_init__(self) -> None:
        if not self.canonical_fixture_id or not self.canonical_fixture_id.strip():
            raise ValueError("canonical_fixture_id is required")
        for value, field in (
            (self.kickoff_at_utc, "kickoff_at_utc"),
            (self.cutoff_at_utc, "cutoff_at_utc"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")
        if self.cutoff_at_utc >= self.kickoff_at_utc:
            raise ValueError("odds cutoff must be strictly before kickoff")
        if not self.required_selections:
            raise ValueError("required_selections cannot be empty")
        if len(set(self.required_selections)) != len(self.required_selections):
            raise ValueError("required_selections must be unique")
        allowed = {
            CanonicalMarket.ONE_X_TWO: {
                CanonicalSelection.HOME, CanonicalSelection.DRAW, CanonicalSelection.AWAY,
            },
            CanonicalMarket.BTTS: {CanonicalSelection.YES, CanonicalSelection.NO},
            CanonicalMarket.TOTALS: {CanonicalSelection.OVER, CanonicalSelection.UNDER},
        }[self.market]
        if not set(self.required_selections).issubset(allowed):
            raise ValueError("required selections do not belong to the target market")
        if self.market is CanonicalMarket.TOTALS:
            if self.required_line is None or not self.required_line.is_finite() or self.required_line <= 0:
                raise ValueError("totals coverage requires a positive finite line")
        elif self.required_line is not None:
            raise ValueError("required_line is only valid for totals coverage")
        if self.max_quote_age_seconds is not None and self.max_quote_age_seconds < 0:
            raise ValueError("max_quote_age_seconds cannot be negative")


@dataclass(frozen=True, slots=True)
class OddsCoverageResult:
    target: OddsCoverageTarget
    state: OddsCoverageState
    qualifying_bookmakers: tuple[str, ...]
    eligible_quote_count: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class OddsCoverageSummary:
    total_targets: int
    covered_targets: int
    coverage_ratio: Decimal
    required_ratio: Decimal
    meets_threshold: bool
    results: tuple[OddsCoverageResult, ...]


def evaluate_odds_coverage(
    targets: Sequence[OddsCoverageTarget],
    quotes: Sequence[NormalizedOddsQuote],
    *,
    required_ratio: Decimal = Decimal("0.98"),
) -> OddsCoverageSummary:
    """Require a complete same-bookmaker/same-timestamp selection set before cutoff."""
    if not required_ratio.is_finite() or not Decimal("0") <= required_ratio <= Decimal("1"):
        raise ValueError("required_ratio must be between 0 and 1")

    results: list[OddsCoverageResult] = []
    for target in targets:
        matching = [
            quote for quote in quotes
            if quote.canonical_fixture_id == target.canonical_fixture_id
            and quote.canonical_market is target.market
            and (
                target.market is not CanonicalMarket.TOTALS
                or quote.line == target.required_line
            )
        ]
        if not matching:
            results.append(OddsCoverageResult(
                target, OddsCoverageState.MISSING, (), 0, "NO_QUOTES_FOR_FIXTURE_MARKET"
            ))
            continue

        cutoff = target.cutoff_at_utc.astimezone(timezone.utc)
        kickoff = target.kickoff_at_utc.astimezone(timezone.utc)
        temporal = [
            quote for quote in matching
            if quote.quote_updated_at_utc.astimezone(timezone.utc) <= cutoff
            and quote.quote_updated_at_utc.astimezone(timezone.utc) < kickoff
        ]
        if not temporal:
            results.append(OddsCoverageResult(
                target, OddsCoverageState.MISSING, (), 0, "NO_PRE_CUTOFF_QUOTES"
            ))
            continue

        fresh = []
        for quote in temporal:
            age = (cutoff - quote.quote_updated_at_utc.astimezone(timezone.utc)).total_seconds()
            if target.max_quote_age_seconds is None or age <= target.max_quote_age_seconds:
                fresh.append(quote)
        if not fresh:
            results.append(OddsCoverageResult(
                target, OddsCoverageState.STALE, (), len(temporal), "ALL_PRE_CUTOFF_QUOTES_STALE"
            ))
            continue

        groups: dict[tuple[str, datetime, Decimal | None], set[CanonicalSelection]] = {}
        for quote in fresh:
            key = (
                quote.bookmaker_key,
                quote.quote_updated_at_utc.astimezone(timezone.utc),
                quote.line,
            )
            groups.setdefault(key, set()).add(quote.selection)
        qualifying = tuple(sorted({
            bookmaker for (bookmaker, _, _), selections in groups.items()
            if set(target.required_selections).issubset(selections)
        }))
        if qualifying:
            results.append(OddsCoverageResult(
                target, OddsCoverageState.COVERED, qualifying, len(fresh),
                "COMPLETE_PRE_KICKOFF_MARKET_SNAPSHOT",
            ))
        else:
            results.append(OddsCoverageResult(
                target, OddsCoverageState.INCOMPLETE, (), len(fresh),
                "REQUIRED_SELECTIONS_NOT_COMPLETE_AT_ONE_BOOKMAKER_TIMESTAMP",
            ))

    total = len(results)
    covered = sum(item.state is OddsCoverageState.COVERED for item in results)
    ratio = Decimal(covered) / Decimal(total) if total else Decimal("0")
    return OddsCoverageSummary(
        total_targets=total,
        covered_targets=covered,
        coverage_ratio=ratio,
        required_ratio=required_ratio,
        meets_threshold=bool(total) and ratio >= required_ratio,
        results=tuple(results),
    )
