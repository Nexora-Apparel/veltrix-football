from decimal import Decimal

import pytest

from veltrix_v2.evaluation.binary_benchmark import compare_binary_to_bookmaker
from veltrix_v2.evaluation.binary_metrics import BinaryForecast, SettledBinaryOutcome
from veltrix_v2.evaluation.odds_normalization import NormalizedBookProbability


def book(selection, probability, fixture="f1"):
    return NormalizedBookProbability(
        fixture_id=fixture, source_id="the-odds-api", bookmaker_id="bet365",
        market="BTTS", selection=selection, line=None,
        captured_at=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        kickoff_at=__import__("datetime").datetime(2026, 1, 2, tzinfo=__import__("datetime").timezone.utc),
        snapshot_id=f"{fixture}-{selection}", decimal_odds=Decimal("2"),
        raw_implied_probability=Decimal("0.5"),
        normalized_probability=Decimal(str(probability)), overround=Decimal("0"),
    )


def test_binary_benchmark_rejects_non_normalized_selection_pair():
    with pytest.raises(ValueError, match="MUST_SUM_TO_ONE"):
        compare_binary_to_bookmaker(
            [BinaryForecast("f1", 0.6)],
            [book("YES", 0.8), book("NO", 0.8)],
            [SettledBinaryOutcome("f1", "YES")],
            eligible_fixture_ids=["f1"],
            affirmative_selection="YES",
        )
