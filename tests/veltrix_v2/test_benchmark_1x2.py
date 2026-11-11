from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.evaluation.benchmark_1x2 import compare_1x2_to_bookmaker
from veltrix_v2.evaluation.metrics import Forecast1X2, SettledOutcome1X2
from veltrix_v2.evaluation.odds_normalization import NormalizedBookProbability


UTC = timezone.utc


def quote(fixture, selection, probability):
    kickoff = datetime(2026, 11, 1, 18, tzinfo=UTC)
    return NormalizedBookProbability(
        fixture_id=fixture,
        source_id="odds-source",
        bookmaker_id="book-a",
        market="1X2",
        selection=selection,
        line=None,
        captured_at=kickoff - timedelta(minutes=10),
        kickoff_at=kickoff,
        snapshot_id=f"{fixture}-{selection}",
        decimal_odds=Decimal("2"),
        raw_implied_probability=Decimal("0.5"),
        normalized_probability=Decimal(str(probability)),
        overround=Decimal("0.05"),
    )


def test_1x2_benchmark_uses_exact_common_fixture_set():
    models = [
        Forecast1X2("f1", 0.70, 0.20, 0.10),
        Forecast1X2("f2", 0.10, 0.20, 0.70),
        Forecast1X2("f3", 0.20, 0.60, 0.20),
    ]
    books = [
        quote("f1", "HOME", 0.55), quote("f1", "DRAW", 0.25), quote("f1", "AWAY", 0.20),
        quote("f2", "HOME", 0.20), quote("f2", "DRAW", 0.25), quote("f2", "AWAY", 0.55),
    ]
    outcomes = [
        SettledOutcome1X2("f1", "HOME"),
        SettledOutcome1X2("f2", "AWAY"),
        SettledOutcome1X2("f3", "DRAW"),
    ]
    result = compare_1x2_to_bookmaker(
        models, books, outcomes, eligible_fixture_ids=["f1", "f2", "f3", "f4"]
    )
    assert result.common_sample_size == 2
    assert result.model_coverage == 0.75
    assert result.bookmaker_coverage == 0.5
    assert result.comparison.sample_size == 2
    assert result.comparison.model_beats_brier
    assert result.comparison.model_beats_log_loss


def test_incomplete_market_is_rejected():
    with pytest.raises(ValueError, match="INCOMPLETE_MARKET"):
        compare_1x2_to_bookmaker(
            [Forecast1X2("f1", 0.4, 0.3, 0.3)],
            [quote("f1", "HOME", 0.4), quote("f1", "DRAW", 0.3)],
            [SettledOutcome1X2("f1", "HOME")],
            eligible_fixture_ids=["f1"],
        )


def test_mixed_bookmaker_is_rejected():
    rows = [
        quote("f1", "HOME", 0.4), quote("f1", "DRAW", 0.3), quote("f1", "AWAY", 0.3)
    ]
    from dataclasses import replace
    rows[2] = replace(rows[2], bookmaker_id="book-b")
    with pytest.raises(ValueError, match="MIXED_BOOKMAKER"):
        compare_1x2_to_bookmaker(
            [Forecast1X2("f1", 0.4, 0.3, 0.3)],
            rows,
            [SettledOutcome1X2("f1", "HOME")],
            eligible_fixture_ids=["f1"],
        )


def test_no_common_sample_is_rejected():
    with pytest.raises(ValueError, match="NO_COMMON"):
        compare_1x2_to_bookmaker(
            [Forecast1X2("f1", 0.4, 0.3, 0.3)],
            [quote("f2", "HOME", 0.4), quote("f2", "DRAW", 0.3), quote("f2", "AWAY", 0.3)],
            [SettledOutcome1X2("f1", "HOME"), SettledOutcome1X2("f2", "AWAY")],
            eligible_fixture_ids=["f1", "f2"],
        )
