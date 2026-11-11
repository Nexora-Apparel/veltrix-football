"""Bookmaker-only probability normalization for benchmark comparisons.

This module is deliberately isolated from model features and forecast generation.
Quotes are normalized only within an exact timestamp/bookmaker/market/line group.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
            normalized_probability=raw[selection] / book_sum,
            overround=overround,
        )
        for selection, row in sorted(by_selection.items())
    )
