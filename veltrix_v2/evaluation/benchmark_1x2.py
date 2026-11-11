"""Exact-common-sample 1X2 bookmaker benchmark comparison.

Consumes normalized complete same-bookmaker 1X2 market snapshots. The model and
benchmark are scored only on fixtures where both forecasts and the settled
outcome exist. Coverage against the complete eligible test universe is kept.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from veltrix_v2.evaluation.metrics import (
    BenchmarkComparison1X2, Forecast1X2, SettledOutcome1X2, compare_1x2_forecasts,
)
from veltrix_v2.evaluation.odds_normalization import NormalizedBookProbability


@dataclass(frozen=True, slots=True)
class BookmakerComparison1X2:
    source_id: str
    bookmaker_id: str
    eligible_fixture_count: int
    model_coverage: float
    bookmaker_coverage: float
    common_sample_size: int
    comparison: BenchmarkComparison1X2


def compare_1x2_to_bookmaker(
    model_forecasts: Iterable[Forecast1X2],
    bookmaker_probabilities: Iterable[NormalizedBookProbability],
    outcomes: Iterable[SettledOutcome1X2],
    *,
    eligible_fixture_ids: Iterable[str],
) -> BookmakerComparison1X2:
    models = tuple(model_forecasts)
    books = tuple(bookmaker_probabilities)
    settled = tuple(outcomes)
    eligible = tuple(eligible_fixture_ids)
    if not eligible or len(eligible) != len(set(eligible)):
        raise ValueError("1X2_BENCHMARK_ELIGIBLE_FIXTURES_INVALID")
    if not books:
        raise ValueError("1X2_BENCHMARK_QUOTES_REQUIRED")
    first = books[0]
    if first.market.upper() != "1X2" or first.line is not None:
        raise ValueError("1X2_BENCHMARK_MARKET_OR_LINE_INVALID")

    groups: dict[str, dict[str, NormalizedBookProbability]] = {}
    seen_snapshots: set[str] = set()
    for row in books:
        if (
            row.source_id != first.source_id
            or row.bookmaker_id != first.bookmaker_id
            or row.market.upper() != "1X2"
            or row.line is not None
        ):
            raise ValueError("1X2_BENCHMARK_MIXED_BOOKMAKER_MARKET")
        if row.snapshot_id in seen_snapshots:
            raise ValueError("1X2_BENCHMARK_DUPLICATE_SNAPSHOT")
        seen_snapshots.add(row.snapshot_id)
        if row.captured_at >= row.kickoff_at:
            raise ValueError("1X2_BENCHMARK_QUOTE_NOT_PREMATCH")
        if not row.fixture_id or not row.fixture_id.strip():
            raise ValueError("1X2_BENCHMARK_FIXTURE_ID_REQUIRED")
        group = groups.setdefault(row.fixture_id, {})
        selection = row.selection.upper()
        if selection in group:
            raise ValueError("1X2_BENCHMARK_DUPLICATE_SELECTION")
        if group:
            prior = next(iter(group.values()))
            if prior.captured_at != row.captured_at or prior.kickoff_at != row.kickoff_at:
                raise ValueError("1X2_BENCHMARK_SELECTION_TIMESTAMPS_MISMATCH")
        group[selection] = row

    book_by_fixture: dict[str, Forecast1X2] = {}
    for fixture_id, group in groups.items():
        if set(group) != {"HOME", "DRAW", "AWAY"}:
            raise ValueError("1X2_BENCHMARK_INCOMPLETE_MARKET")
        book_by_fixture[fixture_id] = Forecast1X2(
            fixture_id,
            float(group["HOME"].normalized_probability),
            float(group["DRAW"].normalized_probability),
            float(group["AWAY"].normalized_probability),
        )

    model_by_fixture = {row.fixture_id: row for row in models}
    outcome_by_fixture = {row.fixture_id: row for row in settled}
    if len(model_by_fixture) != len(models) or len(outcome_by_fixture) != len(settled):
        raise ValueError("1X2_BENCHMARK_DUPLICATE_FIXTURE")
    eligible_set = set(eligible)
    if (
        not set(model_by_fixture) <= eligible_set
        or not set(book_by_fixture) <= eligible_set
        or not set(outcome_by_fixture) <= eligible_set
    ):
        raise ValueError("1X2_BENCHMARK_FIXTURE_OUTSIDE_ELIGIBLE_UNIVERSE")
    if (
        set(model_by_fixture) - set(outcome_by_fixture)
        or set(book_by_fixture) - set(outcome_by_fixture)
    ):
        raise ValueError("1X2_BENCHMARK_SETTLED_OUTCOME_MISSING")

    common = tuple(sorted(set(model_by_fixture) & set(book_by_fixture) & set(outcome_by_fixture)))
    if not common:
        raise ValueError("1X2_BENCHMARK_NO_COMMON_SETTLED_FIXTURES")
    model_common = tuple(model_by_fixture[key] for key in common)
    book_common = tuple(book_by_fixture[key] for key in common)
    outcome_common = tuple(outcome_by_fixture[key] for key in common)
    comparison = compare_1x2_forecasts(model_common, book_common, outcome_common)
    return BookmakerComparison1X2(
        source_id=first.source_id,
        bookmaker_id=first.bookmaker_id,
        eligible_fixture_count=len(eligible),
        model_coverage=len(model_by_fixture) / len(eligible),
        bookmaker_coverage=len(book_by_fixture) / len(eligible),
        common_sample_size=len(common),
        comparison=comparison,
    )
