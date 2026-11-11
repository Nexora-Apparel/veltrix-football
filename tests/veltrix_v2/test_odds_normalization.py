from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.odds_normalization import normalize_bookmaker_market


UTC = timezone.utc
KICKOFF = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)
CAPTURED = KICKOFF - timedelta(hours=1)


def quote(selection, odds, *, market="1X2", line=None, bookmaker="book-a",
          captured=CAPTURED, source="source-a", fixture="fixture-a", snapshot_id=None):
    return OddsSnapshot(
        snapshot_id=snapshot_id or f"{market}-{selection}-{odds}",
        fixture_id=fixture,
        source_id=source,
        bookmaker_id=bookmaker,
        market=market,
        selection=selection,
        decimal_odds=Decimal(str(odds)),
        captured_at=captured,
        kickoff_at=KICKOFF,
        line=None if line is None else Decimal(str(line)),
    )


def test_normalizes_complete_1x2_market_after_proportional_overround():
    rows = [
        quote("HOME", "2.00"),
        quote("DRAW", "3.50"),
        quote("AWAY", "4.00"),
    ]
    normalized = normalize_bookmaker_market(rows)
    by_selection = {row.selection: row for row in normalized}

    raw_sum = Decimal("0.5") + Decimal(1) / Decimal("3.5") + Decimal("0.25")
    assert by_selection["HOME"].raw_implied_probability == Decimal("0.5")
    assert by_selection["HOME"].overround == raw_sum - Decimal("1")
    assert sum((row.normalized_probability for row in normalized), Decimal("0")) == Decimal("1")
    assert by_selection["HOME"].normalized_probability == Decimal("0.5") / raw_sum


def test_normalizes_btts_market():
    rows = [
        quote("YES", "1.80", market="BTTS"),
        quote("NO", "2.10", market="BTTS"),
    ]
    normalized = normalize_bookmaker_market(rows)
    assert len(normalized) == 2
    assert sum((row.normalized_probability for row in normalized), Decimal("0")) == Decimal("1")


def test_totals_market_requires_and_preserves_exact_line():
    rows = [
        quote("OVER", "1.91", market="TOTALS", line="2.5"),
        quote("UNDER", "1.91", market="TOTALS", line="2.5"),
    ]
    normalized = normalize_bookmaker_market(rows)
    assert {row.line for row in normalized} == {Decimal("2.5")}


def test_partial_market_is_rejected_not_guessed():
    with pytest.raises(ValueError, match="INCOMPLETE_SELECTION_SET"):
        normalize_bookmaker_market([quote("HOME", "2.0"), quote("DRAW", "3.0")])


def test_mixed_bookmakers_are_rejected():
    with pytest.raises(ValueError, match="GROUP_MISMATCH"):
        normalize_bookmaker_market([
            quote("YES", "1.8", market="BTTS", bookmaker="book-a"),
            quote("NO", "2.0", market="BTTS", bookmaker="book-b"),
        ])


def test_mixed_capture_times_are_rejected():
    with pytest.raises(ValueError, match="GROUP_MISMATCH"):
        normalize_bookmaker_market([
            quote("YES", "1.8", market="BTTS"),
            quote("NO", "2.0", market="BTTS", captured=CAPTURED + timedelta(seconds=1)),
        ])


def test_mixed_total_lines_are_rejected():
    with pytest.raises(ValueError, match="GROUP_MISMATCH"):
        normalize_bookmaker_market([
            quote("OVER", "1.8", market="TOTALS", line="2.5"),
            quote("UNDER", "2.0", market="TOTALS", line="3.5"),
        ])


def test_duplicate_selection_is_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_SELECTION"):
        normalize_bookmaker_market([
            quote("YES", "1.8", market="BTTS", snapshot_id="one"),
            quote("YES", "1.9", market="BTTS", snapshot_id="two"),
        ])


def test_duplicate_snapshot_id_is_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_SNAPSHOT_ID"):
        normalize_bookmaker_market([
            quote("YES", "1.8", market="BTTS", snapshot_id="same"),
            quote("NO", "2.0", market="BTTS", snapshot_id="same"),
        ])


def test_unknown_market_and_empty_input_fail_closed():
    with pytest.raises(ValueError, match="EMPTY"):
        normalize_bookmaker_market([])
    with pytest.raises(ValueError, match="UNSUPPORTED_MARKET"):
        normalize_bookmaker_market([
            quote("YES", "1.8", market="MATCH_WINNER"),
            quote("NO", "2.0", market="MATCH_WINNER"),
        ])



def test_normalized_quote_contract_rejects_probability_price_mismatch():
    from dataclasses import replace

    row = normalize_bookmaker_market([
        snapshot("HOME", "2.0"),
        snapshot("DRAW", "3.5"),
        snapshot("AWAY", "4.0"),
    ])[0]
    with pytest.raises(ValueError, match="RAW_PROBABILITY_DOES_NOT_MATCH_PRICE"):
        replace(row, raw_implied_probability=Decimal("0.9"))
