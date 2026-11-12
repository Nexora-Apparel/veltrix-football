"""Exact-common-sample 1X2 bookmaker benchmark comparison.

Consumes normalized complete same-bookmaker 1X2 market snapshots. The model and
benchmark are scored only on fixtures where both forecasts and the settled
outcome exist. Coverage against the complete eligible test universe is kept.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
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
    common_fixture_ids: tuple[str, ...]
    comparison: BenchmarkComparison1X2


def _latest_complete_quote_group_per_fixture(
    rows: tuple[NormalizedBookProbability, ...],
) -> tuple[NormalizedBookProbability, ...]:
    """Select the latest complete pre-match bookmaker quote group per fixture."""
    by_fixture: dict[str, dict[tuple[object, ...], dict[str, NormalizedBookProbability]]] = {}
    for row in rows:
        key = (
            row.source_id, row.bookmaker_id, row.market.upper(), row.line,
            row.captured_at, row.kickoff_at, row.provider_quote_at,
            row.source_observation_id,
        )
        group = by_fixture.setdefault(row.fixture_id, {}).setdefault(key, {})
        selection = row.selection.upper()
        if selection in group:
            raise ValueError("1X2_BENCHMARK_DUPLICATE_SELECTION")
        group[selection] = row

    selected: list[NormalizedBookProbability] = []
    for fixture_id, groups in by_fixture.items():
        complete = [
            (key, group) for key, group in groups.items()
            if set(group) == {"HOME", "DRAW", "AWAY"}
        ]
        if not complete:
            raise ValueError("1X2_BENCHMARK_INCOMPLETE_MARKET")
        ranked = [
            (
                (key[6], key[4]),  # provider quote time, then local capture time
                key,
                group,
            )
            for key, group in complete
        ]
        best_rank = max(row[0] for row in ranked)
        best = [(key, group) for rank, key, group in ranked if rank == best_rank]
        if len(best) != 1:
            raise ValueError("1X2_BENCHMARK_LATEST_QUOTE_GROUP_AMBIGUOUS")
        selected.extend(best[0][1][selection] for selection in ("HOME", "DRAW", "AWAY"))
    return tuple(selected)


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

    books = _latest_complete_quote_group_per_fixture(books)
    first = books[0]
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
            if (
                prior.captured_at != row.captured_at
                or prior.kickoff_at != row.kickoff_at
                or prior.provider_quote_at != row.provider_quote_at
                or prior.source_observation_id != row.source_observation_id
            ):
                raise ValueError("1X2_BENCHMARK_SELECTION_TIMESTAMPS_OR_PROVENANCE_MISMATCH")
        group[selection] = row

    book_by_fixture: dict[str, Forecast1X2] = {}
    for fixture_id, group in groups.items():
        if set(group) != {"HOME", "DRAW", "AWAY"}:
            raise ValueError("1X2_BENCHMARK_INCOMPLETE_MARKET")
        probability_sum = sum(
            (row.normalized_probability for row in group.values()), Decimal("0")
        )
        if abs(probability_sum - Decimal("1")) > Decimal("0.000000001"):
            raise ValueError("1X2_BENCHMARK_NORMALIZED_SELECTIONS_MUST_SUM_TO_ONE")
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
        common_fixture_ids=common,
        comparison=comparison,
    )
