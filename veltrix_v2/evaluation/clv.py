"""Strict closing-line-value calculation for matched bookmaker quotes.

A merely later pre-kickoff snapshot is not automatically a closing quote. The
caller must supply explicit closing-snapshot verification from source evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from veltrix_v2.contracts.odds import OddsSnapshot


@dataclass(frozen=True, slots=True)
class ClosingLineValue:
    fixture_id: str
    source_id: str
    bookmaker_id: str
    market: str
    selection: str
    line: Decimal | None
    taken_snapshot_id: str
    closing_snapshot_id: str
    taken_decimal_odds: Decimal
    closing_decimal_odds: Decimal
    taken_implied_probability: Decimal
    closing_implied_probability: Decimal
    clv_probability_points: Decimal
    clv_odds_ratio: Decimal
    status: str = "VERIFIED_CLOSING_LINE_VALUE"


def calculate_clv(
    taken_quote: OddsSnapshot,
    closing_quote: OddsSnapshot,
    *,
    closing_snapshot_verified: bool,
    verification_reference: str,
) -> ClosingLineValue:
    """Calculate CLV only for an exact quote identity and verified final quote.

    Positive probability-points CLV means the selected outcome's implied
    probability rose between bet capture and the verified close, so the taken
    price was better than the closing price.
    """
    if closing_snapshot_verified is not True:
        raise ValueError("CLV_CLOSING_SNAPSHOT_NOT_VERIFIED")
    if not isinstance(verification_reference, str) or not verification_reference.strip():
        raise ValueError("CLV_VERIFICATION_REFERENCE_REQUIRED")

    identity = ("fixture_id", "source_id", "bookmaker_id", "market", "selection", "line")
    if any(getattr(taken_quote, field) != getattr(closing_quote, field) for field in identity):
        raise ValueError("CLV_QUOTE_IDENTITY_MISMATCH")
    if closing_quote.captured_at <= taken_quote.captured_at:
        raise ValueError("CLV_CLOSE_MUST_BE_LATER_THAN_TAKEN_QUOTE")
    if closing_quote.kickoff_at != taken_quote.kickoff_at:
        raise ValueError("CLV_KICKOFF_MISMATCH")
    if closing_quote.captured_at >= closing_quote.kickoff_at:
        raise ValueError("CLV_CLOSE_MUST_PRECEDE_KICKOFF")

    taken_probability = Decimal("1") / taken_quote.decimal_odds
    closing_probability = Decimal("1") / closing_quote.decimal_odds
    return ClosingLineValue(
        fixture_id=taken_quote.fixture_id,
        source_id=taken_quote.source_id,
        bookmaker_id=taken_quote.bookmaker_id,
        market=taken_quote.market,
        selection=taken_quote.selection,
        line=taken_quote.line,
        taken_snapshot_id=taken_quote.snapshot_id,
        closing_snapshot_id=closing_quote.snapshot_id,
        taken_decimal_odds=taken_quote.decimal_odds,
        closing_decimal_odds=closing_quote.decimal_odds,
        taken_implied_probability=taken_probability,
        closing_implied_probability=closing_probability,
        clv_probability_points=closing_probability - taken_probability,
        clv_odds_ratio=(taken_quote.decimal_odds / closing_quote.decimal_odds) - Decimal("1"),
    )
