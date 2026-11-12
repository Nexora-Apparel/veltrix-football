from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.certification_evidence import (
    derive_timestamped_odds_coverage,
)

UTC = timezone.utc


def quote(fixture_id, selection, *, market="1X2", snapshot_id=None, quote_at=True):
    kickoff = datetime(2026, 11, 12, 18, tzinfo=UTC)
    captured = kickoff - timedelta(minutes=5)
    return OddsSnapshot(
        snapshot_id=snapshot_id or f"{fixture_id}-{selection}",
        fixture_id=fixture_id,
        source_id="odds-provider",
        bookmaker_id="bookmaker-a",
        market=market,
        selection=selection,
        decimal_odds=Decimal("2.5"),
        captured_at=captured,
        kickoff_at=kickoff,
        line=Decimal("2.5") if market == "TOTALS" else None,
        provider_quote_at=captured - timedelta(seconds=1) if quote_at else None,
        source_observation_id=f"obs-{fixture_id}",
    )


def test_timestamped_coverage_counts_only_complete_provider_timestamped_groups():
    rows = [
        quote("f1", "HOME"), quote("f1", "DRAW"), quote("f1", "AWAY"),
        quote("f2", "HOME"), quote("f2", "DRAW"),
        quote("f3", "HOME", quote_at=False),
        quote("f3", "DRAW", quote_at=False),
        quote("f3", "AWAY", quote_at=False),
    ]

    report = derive_timestamped_odds_coverage(
        ("f1", "f2", "f3", "f4"), rows, market="1X2"
    )

    assert report.eligible_fixture_count == 4
    assert report.covered_fixture_count == 1
    assert report.covered_fixture_ids == ("f1",)
    assert report.coverage == Decimal("0.25")


def test_timestamped_coverage_rejects_duplicate_snapshot_ids():
    rows = [
        quote("f1", "HOME", snapshot_id="duplicate"),
        quote("f1", "DRAW", snapshot_id="duplicate"),
        quote("f1", "AWAY"),
    ]
    with pytest.raises(ValueError, match="DUPLICATE_SNAPSHOT_ID"):
        derive_timestamped_odds_coverage(("f1",), rows, market="1X2")


@pytest.mark.parametrize(
    ("market", "selections"),
    [
        ("BTTS", ("YES", "NO")),
        ("TOTALS", ("OVER", "UNDER")),
    ],
)
def test_binary_market_coverage_requires_complete_selection_set(market, selections):
    rows = [quote("f1", selection, market=market) for selection in selections]
    report = derive_timestamped_odds_coverage(("f1", "f2"), rows, market=market)
    assert report.covered_fixture_ids == ("f1",)
    assert report.coverage == Decimal("0.5")


def test_timestamped_coverage_rejects_duplicate_eligible_fixture_ids():
    with pytest.raises(ValueError, match="ELIGIBLE_FIXTURES_INVALID"):
        derive_timestamped_odds_coverage(("f1", "f1"), (), market="1X2")



def test_timestamped_coverage_does_not_combine_quotes_from_different_provider_updates():
    home = quote("f1", "HOME")
    draw = quote("f1", "DRAW")
    away = quote("f1", "AWAY")
    from dataclasses import replace
    draw = replace(draw, provider_quote_at=draw.provider_quote_at - timedelta(seconds=1))
    report = derive_timestamped_odds_coverage(
        ("f1",), (home, draw, away), market="1X2"
    )
    assert report.covered_fixture_ids == ()
    assert report.coverage == Decimal("0")


def test_timestamped_coverage_does_not_combine_distinct_source_observations():
    rows = [
        quote("f1", "HOME"),
        quote("f1", "DRAW"),
        quote("f1", "AWAY"),
    ]
    from dataclasses import replace
    rows[2] = replace(rows[2], source_observation_id="obs-another-response")
    report = derive_timestamped_odds_coverage(("f1",), rows, market="1X2")
    assert report.covered_fixture_ids == ()
    assert report.coverage == Decimal("0")
