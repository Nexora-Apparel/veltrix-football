"""Exact-sample bookmaker benchmark comparison for binary markets.

Benchmark inputs must already be normalized no-vig probabilities from one
consistent provider/bookmaker/market/line. The comparison uses only fixtures
with model, bookmaker and settled-outcome observations all present.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from veltrix_v2.evaluation.binary_metrics import (
    BinaryForecast, BinaryScoreReport, SettledBinaryOutcome, score_binary_market,
)
from veltrix_v2.evaluation.odds_normalization import NormalizedBookProbability


@dataclass(frozen=True, slots=True)
class BinaryBenchmarkComparison:
    market: str
    source_id: str
    bookmaker_id: str
    line: object
    eligible_fixture_count: int
    model_coverage: float
    bookmaker_coverage: float
    common_sample_size: int
    model_report: BinaryScoreReport
    bookmaker_report: BinaryScoreReport
    brier_delta: float
    log_loss_delta: float
    model_beats_brier: bool
    model_beats_log_loss: bool


def compare_binary_to_bookmaker(
    model_forecasts: Iterable[BinaryForecast],
    bookmaker_probabilities: Iterable[NormalizedBookProbability],
    outcomes: Iterable[SettledBinaryOutcome],
    *,
    eligible_fixture_ids: Iterable[str],
    affirmative_selection: str,
) -> BinaryBenchmarkComparison:
    """Compare model and no-vig bookmaker probabilities on identical fixtures."""
    models = tuple(model_forecasts)
    books = tuple(bookmaker_probabilities)
    settled = tuple(outcomes)
    eligible = tuple(eligible_fixture_ids)
    if not eligible or len(eligible) != len(set(eligible)):
        raise ValueError("BINARY_BENCHMARK_ELIGIBLE_FIXTURES_INVALID")
    if not books:
        raise ValueError("BINARY_BENCHMARK_QUOTES_REQUIRED")
    if affirmative_selection.upper() not in {"YES", "OVER"}:
        raise ValueError("BINARY_BENCHMARK_AFFIRMATIVE_SELECTION_INVALID")

    first = books[0]
    market = first.market.upper()
    if market not in {"BTTS", "TOTALS", "OVER_UNDER"}:
        raise ValueError("BINARY_BENCHMARK_MARKET_UNSUPPORTED")
    if market == "BTTS" and affirmative_selection.upper() != "YES":
        raise ValueError("BINARY_BENCHMARK_SELECTION_DOES_NOT_MATCH_MARKET")
    if market in {"TOTALS", "OVER_UNDER"} and affirmative_selection.upper() != "OVER":
        raise ValueError("BINARY_BENCHMARK_SELECTION_DOES_NOT_MATCH_MARKET")

    book_by_fixture: dict[str, float] = {}
    for row in books:
        if (
            row.source_id != first.source_id
            or row.bookmaker_id != first.bookmaker_id
            or row.market.upper() != market
            or row.line != first.line
        ):
            raise ValueError("BINARY_BENCHMARK_MIXED_BOOKMAKER_MARKET_OR_LINE")
        if row.fixture_id in book_by_fixture:
            raise ValueError("BINARY_BENCHMARK_DUPLICATE_FIXTURE_QUOTE")
        if row.selection.upper() == affirmative_selection.upper():
            book_by_fixture[row.fixture_id] = float(row.normalized_probability)
    if len(book_by_fixture) != len(books):
        raise ValueError("BINARY_BENCHMARK_AFFIRMATIVE_SELECTION_MISSING")

    model_by_fixture = {row.fixture_id: row for row in models}
    outcome_by_fixture = {row.fixture_id: row for row in settled}
    if len(model_by_fixture) != len(models) or len(outcome_by_fixture) != len(settled):
        raise ValueError("BINARY_BENCHMARK_DUPLICATE_FIXTURE")
    eligible_set = set(eligible)
    if not set(model_by_fixture) <= eligible_set or not set(book_by_fixture) <= eligible_set:
        raise ValueError("BINARY_BENCHMARK_FIXTURE_OUTSIDE_ELIGIBLE_UNIVERSE")
    if set(model_by_fixture) - set(outcome_by_fixture) or set(book_by_fixture) - set(outcome_by_fixture):
        raise ValueError("BINARY_BENCHMARK_SETTLED_OUTCOME_MISSING")

    common = tuple(sorted(set(model_by_fixture) & set(book_by_fixture) & set(outcome_by_fixture)))
    if not common:
        raise ValueError("BINARY_BENCHMARK_NO_COMMON_SETTLED_FIXTURES")
    common_outcomes = tuple(outcome_by_fixture[fixture_id] for fixture_id in common)
    model_common = tuple(model_by_fixture[fixture_id] for fixture_id in common)
    book_common = tuple(
        BinaryForecast(fixture_id, book_by_fixture[fixture_id])
        for fixture_id in common
    )
    common_eligible = common
    model_report = score_binary_market(
        model_common, common_outcomes, eligible_fixture_ids=common_eligible
    )
    bookmaker_report = score_binary_market(
        book_common, common_outcomes, eligible_fixture_ids=common_eligible
    )
    model_coverage = len(model_by_fixture) / len(eligible)
    bookmaker_coverage = len(book_by_fixture) / len(eligible)
    brier_delta = model_report.brier_score - bookmaker_report.brier_score
    log_loss_delta = model_report.log_loss - bookmaker_report.log_loss
    return BinaryBenchmarkComparison(
        market=market,
        source_id=first.source_id,
        bookmaker_id=first.bookmaker_id,
        line=first.line,
        eligible_fixture_count=len(eligible),
        model_coverage=model_coverage,
        bookmaker_coverage=bookmaker_coverage,
        common_sample_size=len(common),
        model_report=model_report,
        bookmaker_report=bookmaker_report,
        brier_delta=brier_delta,
        log_loss_delta=log_loss_delta,
        model_beats_brier=brier_delta < 0.0,
        model_beats_log_loss=log_loss_delta < 0.0,
    )
