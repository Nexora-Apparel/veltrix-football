from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.evaluation.binary_benchmark import compare_binary_to_bookmaker
from veltrix_v2.evaluation.binary_metrics import BinaryForecast, SettledBinaryOutcome
from veltrix_v2.evaluation.odds_normalization import NormalizedBookProbability


UTC = timezone.utc


def quote(fixture, selection, probability, *, market="BTTS", line=None):
    kickoff = datetime(2026, 11, 1, 18, tzinfo=UTC)
    return NormalizedBookProbability(
        fixture_id=fixture,
        source_id="striker",
        bookmaker_id="book-a",
        market=market,
        selection=selection,
        line=None if line is None else Decimal(line),
        captured_at=kickoff - timedelta(minutes=10),
        kickoff_at=kickoff,
        snapshot_id=f"{fixture}-{selection}",
        decimal_odds=Decimal("2"),
        raw_implied_probability=Decimal("0.5"),
        normalized_probability=Decimal(str(probability)),
        overround=Decimal("0.05"),
    )


def test_binary_benchmark_compares_exact_common_fixture_set():
    models = [
        BinaryForecast("f1", 0.8),
        BinaryForecast("f2", 0.2),
        BinaryForecast("f3", 0.7),
    ]
    books = [
        quote("f1", "YES", 0.55),
        quote("f2", "YES", 0.45),
    ]
    outcomes = [
        SettledBinaryOutcome("f1", "YES"),
        SettledBinaryOutcome("f2", "NO"),
        SettledBinaryOutcome("f3", "YES"),
    ]
    result = compare_binary_to_bookmaker(
        models, books, outcomes,
        eligible_fixture_ids=["f1", "f2", "f3", "f4"],
        affirmative_selection="YES",
    )
    assert result.common_sample_size == 2
    assert result.eligible_fixture_count == 4
    assert result.model_coverage == 0.75
    assert result.bookmaker_coverage == 0.5
    assert result.model_report.sample_size == result.bookmaker_report.sample_size == 2
    assert result.model_beats_brier
    assert result.model_beats_log_loss


def test_mixed_bookmaker_is_rejected():
    rows = [quote("f1", "YES", 0.5), quote("f2", "YES", 0.5)]
    rows[1] = NormalizedBookProbability(
        **{**rows[1].__dict__, "bookmaker_id": "book-b"}
    )
    with pytest.raises(ValueError, match="MIXED_BOOKMAKER"):
        compare_binary_to_bookmaker(
            [BinaryForecast("f1", 0.5), BinaryForecast("f2", 0.5)],
            rows,
            [SettledBinaryOutcome("f1", "YES"), SettledBinaryOutcome("f2", "NO")],
            eligible_fixture_ids=["f1", "f2"],
            affirmative_selection="YES",
        )


def test_no_common_quotes_rejected():
    with pytest.raises(ValueError, match="NO_COMMON"):
        compare_binary_to_bookmaker(
            [BinaryForecast("f1", 0.6)],
            [quote("f2", "YES", 0.5)],
            [SettledBinaryOutcome("f1", "YES"), SettledBinaryOutcome("f2", "NO")],
            eligible_fixture_ids=["f1", "f2"],
            affirmative_selection="YES",
        )


def test_totals_requires_over_selection_and_same_line():
    with pytest.raises(ValueError, match="SELECTION_DOES_NOT_MATCH"):
        compare_binary_to_bookmaker(
            [BinaryForecast("f1", 0.6)],
            [quote("f1", "YES", 0.5, market="TOTALS", line="2.5")],
            [SettledBinaryOutcome("f1", "YES")],
            eligible_fixture_ids=["f1"],
            affirmative_selection="YES",
        )


def test_duplicate_bookmaker_fixture_quote_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_FIXTURE_QUOTE"):
        compare_binary_to_bookmaker(
            [BinaryForecast("f1", 0.6)],
            [quote("f1", "YES", 0.5), quote("f1", "YES", 0.5)],
            [SettledBinaryOutcome("f1", "YES")],
            eligible_fixture_ids=["f1"],
            affirmative_selection="YES",
        )
