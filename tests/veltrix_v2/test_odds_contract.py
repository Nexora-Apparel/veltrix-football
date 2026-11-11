from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.contracts.odds import OddsSnapshot

UTC = timezone.utc
CAPTURE = datetime(2026, 11, 12, 5, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)


def snapshot(**overrides):
    values = dict(
        snapshot_id="snapshot-1",
        fixture_id="fixture-1",
        source_id="source-1",
        bookmaker_id="bookmaker-1",
        market="1X2",
        selection="HOME",
        decimal_odds=Decimal("2.1"),
        captured_at=CAPTURE,
        kickoff_at=KICKOFF,
    )
    values.update(overrides)
    return OddsSnapshot(**values)


def test_provider_quote_timestamp_is_preserved_separately():
    quote_at = CAPTURE - timedelta(hours=1)
    row = snapshot(provider_quote_at=quote_at)
    assert row.provider_quote_at == quote_at


def test_provider_quote_timestamp_must_be_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot(provider_quote_at=datetime(2026, 11, 12, 4, 0))


def test_provider_quote_timestamp_must_precede_kickoff():
    with pytest.raises(ValueError, match="strictly before kickoff"):
        snapshot(provider_quote_at=KICKOFF)


def test_provider_quote_timestamp_cannot_be_after_capture():
    with pytest.raises(ValueError, match="cannot be after captured_at"):
        snapshot(provider_quote_at=CAPTURE + timedelta(seconds=1))


def test_provider_quote_timestamp_is_optional():
    assert snapshot().provider_quote_at is None
