from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.clv import calculate_clv


UTC = timezone.utc
KICKOFF = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)


def quote(snapshot_id, odds, captured_at, *, selection="HOME", market="1X2",
          bookmaker="book-a", line=None, fixture="fixture-a", source="source-a"):
    return OddsSnapshot(
        snapshot_id=snapshot_id,
        fixture_id=fixture,
        source_id=source,
        bookmaker_id=bookmaker,
        market=market,
        selection=selection,
        decimal_odds=Decimal(str(odds)),
        captured_at=captured_at,
        kickoff_at=KICKOFF,
        line=None if line is None else Decimal(str(line)),
    )


def test_clv_is_positive_when_taken_price_beats_verified_close():
    taken = quote("taken", "2.00", KICKOFF - timedelta(hours=2))
    closing = quote("close", "1.80", KICKOFF - timedelta(minutes=1))

    result = calculate_clv(
        taken, closing,
        closing_snapshot_verified=True,
        verification_reference="provider-close-marker-123",
    )
    assert result.clv_probability_points == Decimal(1) / Decimal("1.8") - Decimal("0.5")
    assert result.clv_odds_ratio == Decimal("2.0") / Decimal("1.8") - Decimal("1")
    assert result.status == "VERIFIED_CLOSING_LINE_VALUE"


def test_later_quote_is_not_assumed_to_be_closing():
    taken = quote("taken", "2.00", KICKOFF - timedelta(hours=2))
    later = quote("later", "1.80", KICKOFF - timedelta(minutes=1))
    with pytest.raises(ValueError, match="NOT_VERIFIED"):
        calculate_clv(
            taken, later,
            closing_snapshot_verified=False,
            verification_reference="unverified",
        )


def test_verification_reference_is_mandatory():
    taken = quote("taken", "2.00", KICKOFF - timedelta(hours=2))
    closing = quote("close", "1.80", KICKOFF - timedelta(minutes=1))
    with pytest.raises(ValueError, match="REFERENCE_REQUIRED"):
        calculate_clv(
            taken, closing,
            closing_snapshot_verified=True,
            verification_reference=" ",
        )


@pytest.mark.parametrize("field,value", [
    ("fixture", "another-fixture"),
    ("source", "another-source"),
    ("bookmaker", "another-bookmaker"),
    ("selection", "AWAY"),
    ("line", "3.0"),
])
def test_clv_rejects_mismatched_quote_identity(field, value):
    taken = quote("taken", "2.00", KICKOFF - timedelta(hours=2), market="TOTALS",
                  selection="OVER", line="2.5")
    kwargs = {"market": "TOTALS", "selection": "OVER", "line": "2.5"}
    if field == "fixture":
        kwargs["fixture"] = value
    elif field == "source":
        kwargs["source"] = value
    elif field == "bookmaker":
        kwargs["bookmaker"] = value
    elif field == "selection":
        kwargs["selection"] = value
    elif field == "line":
        kwargs["line"] = value
    closing = quote("close", "1.80", KICKOFF - timedelta(minutes=1), **kwargs)
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        calculate_clv(
            taken, closing,
            closing_snapshot_verified=True,
            verification_reference="provider-close-marker",
        )


def test_closing_quote_must_be_later_than_taken_quote():
    taken = quote("taken", "2.00", KICKOFF - timedelta(hours=1))
    earlier = quote("close", "1.80", KICKOFF - timedelta(hours=2))
    with pytest.raises(ValueError, match="MUST_BE_LATER"):
        calculate_clv(
            taken, earlier,
            closing_snapshot_verified=True,
            verification_reference="provider-close-marker",
        )
