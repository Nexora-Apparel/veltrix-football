"""Exact-sample bookmaker benchmark comparison for binary markets.

Benchmark inputs must already be normalized no-vig probabilities from one
consistent provider/bookmaker/market/line. The comparison uses only fixtures
with model, bookmaker and settled-outcome observations all present.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
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
    line: Decimal | None
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
    selections_by_fixture: dict[str, dict[str, NormalizedBookProbability]] = {}
    expected_selections = {"BTTS": {"YES", "NO"}, "TOTALS": {"OVER", "UNDER"}, "OVER_UNDER": {"OVER", "UNDER"}}[market]
    seen_snapshot_ids: set[str] = set()
    for row in books:
        if (
            row.source_id != first.source_id
            or row.bookmaker_id != first.bookmaker_id
            or row.market.upper() != market
            or row.line != first.line
        ):
            raise ValueError("BINARY_BENCHMARK_MIXED_BOOKMAKER_MARKET_OR_LINE")
        if not row.fixture_id or not row.fixture_id.strip():
            raise ValueError("BINARY_BENCHMARK_FIXTURE_ID_REQUIRED")
        if row.snapshot_id in seen_snapshot_ids:
            raise ValueError("BINARY_BENCHMARK_DUPLICATE_SNAPSHOT_ID")
        seen_snapshot_ids.add(row.snapshot_id)
        probability = row.normalized_probability
        if not isinstance(probability, Decimal) or not probability.is_finite() or not Decimal("0") < probability < Decimal("1"):
            raise ValueError("BINARY_BENCHMARK_PROBABILITY_INVALID")
        if row.captured_at >= row.kickoff_at:
            raise ValueError("BINARY_BENCHMARK_QUOTE_NOT_PREMATCH")
        selections = selections_by_fixture.setdefault(row.fixture_id, {})
        if selections:
            existing = next(iter(selections.values()))
            if row.captured_at != existing.captured_at or row.kickoff_at != existing.kickoff_at:
                raise ValueError("BINARY_BENCHMARK_SELECTION_TIMESTAMPS_MISMATCH")
        selection = row.selection.upper()
        if selection in selections:
            raise ValueError("BINARY_BENCHMARK_DUPLICATE_FIXTURE_QUOTE")
        selections[selection] = row
    for fixture_id, selections in selections_by_fixture.items():
        if set(selections) != expected_selections:
            raise ValueError("BINARY_BENCHMARK_INCOMPLETE_BOOKMAKER_MARKET")
        book_by_fixture[fixture_id] = float(
            selections[affirmative_selection.upper()].normalized_probability
        )

    model_by_fixture = {row.fixture_id: row for row in models}
    outcome_by_fixture = {row.fixture_id: row for row in settled}
    if len(model_by_fixture) != len(models) or len(outcome_by_fixture) != len(settled):
        raise ValueError("BINARY_BENCHMARK_DUPLICATE_FIXTURE")
    eligible_set = set(eligible)
    if not set(model_by_fixture) <= eligible_set or not set(book_by_fixture) <= eligible_set or not set(outcome_by_fixture) <= eligible_set:
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
