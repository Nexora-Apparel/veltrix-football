from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.contracts.odds import OddsSnapshot


UTC = timezone.utc
KICKOFF = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)


def make_snapshot(**overrides):
    values = {
        "snapshot_id": "quote-001",
        "fixture_id": "fixture-001",
        "source_id": "odds-provider-a",
        "bookmaker_id": "bookmaker-a",
        "market": "1X2",
        "selection": "HOME",
        "decimal_odds": Decimal("2.15"),
        "captured_at": KICKOFF - timedelta(hours=2),
        "kickoff_at": KICKOFF,
    }
    values.update(overrides)
    return OddsSnapshot(**values)


def test_snapshot_is_immutable_and_normalizes_timestamps_to_utc():
    local = timezone(timedelta(hours=2))
    snapshot = make_snapshot(
        captured_at=datetime(2026, 11, 20, 18, 0, tzinfo=local),
        kickoff_at=datetime(2026, 11, 20, 20, 0, tzinfo=local),
        decimal_odds="2.15",
    )
    assert snapshot.captured_at.tzinfo is UTC
    assert snapshot.kickoff_at.tzinfo is UTC
    assert snapshot.decimal_odds == Decimal("2.15")
    with pytest.raises(FrozenInstanceError):
        snapshot.selection = "AWAY"


@pytest.mark.parametrize("field", ["captured_at", "kickoff_at"])
def test_naive_timestamps_are_rejected(field):
    with pytest.raises(ValueError, match="timezone-aware"):
        make_snapshot(**{field: datetime(2026, 11, 20, 18, 0)})


@pytest.mark.parametrize(
    "captured_at",
    [
        KICKOFF,
        KICKOFF + timedelta(seconds=1),
    ],
)
def test_quotes_at_or_after_kickoff_are_rejected(captured_at):
    with pytest.raises(ValueError, match="strictly before kickoff"):
        make_snapshot(captured_at=captured_at)


@pytest.mark.parametrize("odds", ["1", "0.99", "-2", "NaN", "Infinity", "not-a-price"])
def test_invalid_decimal_odds_are_rejected(odds):
    with pytest.raises(ValueError):
        make_snapshot(decimal_odds=odds)


def test_line_is_preserved_as_decimal_and_may_be_absent():
    assert make_snapshot(line="2.5").line == Decimal("2.5")
    assert make_snapshot().line is None


def test_required_identity_fields_cannot_be_blank():
    with pytest.raises(ValueError, match="bookmaker_id"):
        make_snapshot(bookmaker_id="  ")
