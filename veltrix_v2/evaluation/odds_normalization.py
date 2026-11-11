"""Bookmaker-only probability normalization for benchmark comparisons.

This module is deliberately isolated from model features and forecast generation.
Quotes are normalized only within an exact timestamp/bookmaker/market/line group.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from veltrix_v2.contracts.odds import OddsSnapshot


_EXPECTED_SELECTIONS = {
    "1X2": frozenset({"HOME", "DRAW", "AWAY"}),
    "BTTS": frozenset({"YES", "NO"}),
    "TOTALS": frozenset({"OVER", "UNDER"}),
    "OVER_UNDER": frozenset({"OVER", "UNDER"}),
}


@dataclass(frozen=True, slots=True)
class NormalizedBookProbability:
    fixture_id: str
    source_id: str
    bookmaker_id: str
    market: str
    selection: str
    line: Decimal | None
    captured_at: datetime
    kickoff_at: datetime
    snapshot_id: str
    decimal_odds: Decimal
    raw_implied_probability: Decimal
    normalized_probability: Decimal
    overround: Decimal

    def __post_init__(self) -> None:
        for field in ("fixture_id", "source_id", "bookmaker_id", "market", "selection", "snapshot_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"NORMALIZED_ODDS_{field.upper()}_REQUIRED")
        for field in ("captured_at", "kickoff_at"):
            value = getattr(self, field)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"NORMALIZED_ODDS_{field.upper()}_MUST_BE_AWARE")
            object.__setattr__(self, field, value.astimezone(timezone.utc))
        if self.captured_at >= self.kickoff_at:
            raise ValueError("NORMALIZED_ODDS_CAPTURE_MUST_PRECEDE_KICKOFF")
        for field in ("decimal_odds", "raw_implied_probability", "normalized_probability", "overround"):
            value = getattr(self, field)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"NORMALIZED_ODDS_{field.upper()}_MUST_BE_FINITE_DECIMAL")
        if self.decimal_odds <= Decimal("1"):
            raise ValueError("NORMALIZED_ODDS_DECIMAL_ODDS_MUST_EXCEED_ONE")
        if not Decimal("0") < self.raw_implied_probability < Decimal("1"):
            raise ValueError("NORMALIZED_ODDS_RAW_PROBABILITY_OUT_OF_RANGE")
        if not Decimal("0") < self.normalized_probability < Decimal("1"):
            raise ValueError("NORMALIZED_ODDS_PROBABILITY_OUT_OF_RANGE")
        if abs(self.raw_implied_probability - Decimal("1") / self.decimal_odds) > Decimal("0.000000001"):
            raise ValueError("NORMALIZED_ODDS_RAW_PROBABILITY_DOES_NOT_MATCH_PRICE")
        if self.line is not None and (not isinstance(self.line, Decimal) or not self.line.is_finite()):
            raise ValueError("NORMALIZED_ODDS_LINE_INVALID")


def normalize_bookmaker_market(
    snapshots: Iterable[OddsSnapshot],
) -> tuple[NormalizedBookProbability, ...]:
    """Remove proportional overround from one complete, same-time market quote set.

    Partial markets, mixed bookmakers/timestamps/lines, duplicate selections and
    duplicate snapshot IDs fail closed. No odds are returned as model features.
    """
    rows = tuple(snapshots)
    if not rows:
        raise ValueError("ODDS_MARKET_EMPTY")

    first = rows[0]
    group_key = (
        first.fixture_id, first.source_id, first.bookmaker_id, first.market.upper(),
        first.line, first.captured_at, first.kickoff_at,
    )
    seen_ids: set[str] = set()
    by_selection: dict[str, OddsSnapshot] = {}
    for row in rows:
        key = (
            row.fixture_id, row.source_id, row.bookmaker_id, row.market.upper(),
            row.line, row.captured_at, row.kickoff_at,
        )
        if key != group_key:
            raise ValueError("ODDS_MARKET_GROUP_MISMATCH")
        if row.snapshot_id in seen_ids:
            raise ValueError("ODDS_MARKET_DUPLICATE_SNAPSHOT_ID")
        seen_ids.add(row.snapshot_id)
        selection = row.selection.upper()
        if selection in by_selection:
            raise ValueError("ODDS_MARKET_DUPLICATE_SELECTION")
        by_selection[selection] = row

    market = first.market.upper()
    expected = _EXPECTED_SELECTIONS.get(market)
    if expected is None:
        raise ValueError("ODDS_MARKET_UNSUPPORTED_MARKET")
    if frozenset(by_selection) != expected:
        raise ValueError("ODDS_MARKET_INCOMPLETE_SELECTION_SET")

    raw = {
        selection: Decimal("1") / row.decimal_odds
        for selection, row in by_selection.items()
    }
    book_sum = sum(raw.values(), Decimal("0"))
    if book_sum <= Decimal("0"):
        raise ValueError("ODDS_MARKET_INVALID_IMPLIED_SUM")
    overround = book_sum - Decimal("1")
    ordered = list(by_selection.items())
    normalized: dict[str, Decimal] = {}
    running_total = Decimal("0")
    for index, (selection, _) in enumerate(ordered):
        if index == len(ordered) - 1:
            normalized[selection] = Decimal("1") - running_total
        else:
            normalized[selection] = raw[selection] / book_sum
            running_total += normalized[selection]

    return tuple(
        NormalizedBookProbability(
            fixture_id=row.fixture_id,
            source_id=row.source_id,
            bookmaker_id=row.bookmaker_id,
            market=market,
            selection=selection,
            line=row.line,
            captured_at=row.captured_at,
            kickoff_at=row.kickoff_at,
            snapshot_id=row.snapshot_id,
            decimal_odds=row.decimal_odds,
            raw_implied_probability=raw[selection],
            normalized_probability=normalized[selection],
            overround=overround,
        )
        for selection, row in sorted(by_selection.items())
    )
