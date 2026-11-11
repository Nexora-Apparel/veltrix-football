"""Stake-weighted paper ROI and settlement performance diagnostics.

ROI uses settled exposure: WIN, LOSS and PUSH stakes are included; VOID stakes
are excluded. Pushes contribute zero net profit and remain in turnover. Void
returns are bookkeeping only and never inflate gross profit or turnover.

The ROI interval uses a deterministic percentile bootstrap over source-backed
match-date clusters. Every selection and fixture from a sampled match date
remains in the same draw. If any settled row lacks a match date, the interval
is withheld rather than falling back to an IID or fixture-only estimate.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import random
from typing import Iterable

from veltrix_v2.evaluation.settlement import Settlement

ZERO = Decimal("0")
ONE = Decimal("1")
VALID_STATUSES = {"WIN", "LOSS", "PUSH", "VOID"}


def _decimal(value: Decimal, field: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    return value


@dataclass(frozen=True, slots=True)
class MarketPerformance:
    market: str
    total_bets: int
    wins: int
    losses: int
    pushes: int
    voids: int
    decisive_bets: int
    settled_bets: int
    win_rate: Decimal | None
    win_rate_ci_95: tuple[Decimal, Decimal] | None
    settled_turnover: Decimal
    gross_return: Decimal
    net_profit: Decimal
    roi: Decimal | None
    roi_ci_95: tuple[Decimal, Decimal] | None
    roi_ci_method: str


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    total_bets: int
    markets: tuple[MarketPerformance, ...]
    overall: MarketPerformance


def _wilson_interval(wins: int, trials: int) -> tuple[Decimal, Decimal] | None:
    if trials == 0:
        return None
    # 95% Wilson score interval, z = 1.959963984540054.
    z = 1.959963984540054
    n = float(trials)
    p = wins / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denominator
    margin = z * ((p * (1.0 - p) / n + z2 / (4.0 * n * n)) ** 0.5) / denominator
    return (Decimal(str(max(0.0, centre - margin))), Decimal(str(min(1.0, centre + margin))))


def _date_block_roi_interval(
    rows: list[Settlement], *, draws: int, seed: int
) -> tuple[Decimal, Decimal] | None:
    """Bootstrap source-backed match-date blocks, retaining all fixtures/bets."""
    if draws < 100 or any(
        row.match_date is None or not row.match_date_source_observation_id
        for row in rows
    ):
        return None
    blocks: dict[object, list[Settlement]] = {}
    for row in rows:
        blocks.setdefault(row.match_date, []).append(row)
    match_dates = sorted(blocks)
    if len(match_dates) < 2:
        return None

    rng = random.Random(seed)
    samples: list[float] = []
    block_count = len(match_dates)
    for _ in range(draws):
        selected: list[Settlement] = []
        for _ in range(block_count):
            selected.extend(blocks[match_dates[rng.randrange(block_count)]])
        turnover = sum((row.stake for row in selected), ZERO)
        if turnover <= ZERO:
            continue
        profit = sum((row.net_profit for row in selected), ZERO)
        samples.append(float(profit / turnover))
    if not samples:
        return None
    samples.sort()
    low_index = int(0.025 * (len(samples) - 1))
    high_index = int(0.975 * (len(samples) - 1))
    return (Decimal(str(samples[low_index])), Decimal(str(samples[high_index])))


def _summarize(
    market: str,
    rows: list[Settlement],
    *,
    bootstrap_draws: int,
    bootstrap_seed: int,
) -> MarketPerformance:
    wins = sum(row.status == "WIN" for row in rows)
    losses = sum(row.status == "LOSS" for row in rows)
    pushes = sum(row.status == "PUSH" for row in rows)
    voids = sum(row.status == "VOID" for row in rows)
    decisive = wins + losses
    settled = wins + losses + pushes
    non_void = [row for row in rows if row.status != "VOID"]
    turnover = sum((row.stake for row in non_void), ZERO)
    gross = sum((row.gross_return for row in non_void), ZERO)
    profit = sum((row.net_profit for row in non_void), ZERO)
    roi = profit / turnover if turnover > ZERO else None
    roi_interval = _date_block_roi_interval(
        non_void, draws=bootstrap_draws, seed=bootstrap_seed
    )
    if any(row.match_date is None for row in non_void):
        roi_interval_method = "unavailable_missing_match_date"
    elif any(not row.match_date_source_observation_id for row in non_void):
        roi_interval_method = "unavailable_unproven_match_date"
    elif len({row.match_date for row in non_void}) < 2:
        roi_interval_method = "unavailable_insufficient_match_dates"
    elif bootstrap_draws < 100:
        roi_interval_method = "unavailable_insufficient_bootstrap_draws"
    elif roi is None:
        roi_interval_method = "unavailable_zero_turnover"
    elif roi_interval is None:
        roi_interval_method = "unavailable_bootstrap_failed"
    else:
        roi_interval_method = "date_block_bootstrap_by_match_date"
    return MarketPerformance(
        market=market,
        total_bets=len(rows),
        wins=wins,
        losses=losses,
        pushes=pushes,
        voids=voids,
        decisive_bets=decisive,
        settled_bets=settled,
        win_rate=Decimal(wins) / Decimal(decisive) if decisive else None,
        win_rate_ci_95=_wilson_interval(wins, decisive),
        settled_turnover=turnover,
        gross_return=gross,
        net_profit=profit,
        roi=roi,
        roi_ci_95=roi_interval,
        roi_ci_method=roi_interval_method,
    )


def evaluate_roi(
    settlements: Iterable[Settlement],
    *,
    bootstrap_draws: int = 2000,
    bootstrap_seed: int = 20261111,
) -> PerformanceReport:
    """Summarize ROI by market and overall; reject malformed/duplicate rows.

    Uniqueness is one settlement per (fixture, market, selection, period).
    If a selection is corrected, retain the correction in a separate audit
    history and pass only the authoritative current settlement here.
    """
    if isinstance(bootstrap_draws, bool) or not isinstance(bootstrap_draws, int) or bootstrap_draws < 0:
        raise ValueError("bootstrap_draws must be a non-negative integer")
    rows = list(settlements)
    seen: set[tuple[str, str, str, str]] = set()
    fixture_date_provenance: dict[str, tuple[object, str | None]] = {}
    for row in rows:
        if not isinstance(row, Settlement):
            raise ValueError("all rows must be Settlement instances")
        if row.status not in VALID_STATUSES:
            raise ValueError("unsupported settlement status")
        identity_fields = (row.fixture_id, row.market, row.selection, row.period)
        if any(not isinstance(value, str) or not value.strip() for value in identity_fields):
            raise ValueError("settlement identity fields are required")
        key = (row.fixture_id, row.market, row.selection, row.period)
        if key in seen:
            raise ValueError("duplicate settlement identity")
        seen.add(key)
        prior_date_provenance = fixture_date_provenance.get(row.fixture_id)
        current_date_provenance = (row.match_date, row.match_date_source_observation_id)
        if prior_date_provenance is not None and prior_date_provenance != current_date_provenance:
            raise ValueError("settlement match-date provenance conflicts within fixture")
        fixture_date_provenance[row.fixture_id] = current_date_provenance
        stake = _decimal(row.stake, "stake")
        odds = _decimal(row.decimal_odds, "decimal_odds")
        gross = _decimal(row.gross_return, "gross_return")
        profit = _decimal(row.net_profit, "net_profit")
        if stake <= ZERO or odds <= ONE or gross < ZERO:
            raise ValueError("invalid settlement monetary values")
        if profit != gross - stake:
            raise ValueError("net_profit must equal gross_return minus stake")
        if row.status == "WIN" and gross != stake * odds:
            raise ValueError("WIN gross_return must equal stake times decimal odds")
        if row.status in {"LOSS"} and (gross != ZERO or profit != -stake):
            raise ValueError("LOSS must lose the full stake")
        if row.status in {"PUSH", "VOID"} and (gross != stake or profit != ZERO):
            raise ValueError("PUSH and VOID must return the stake")
    markets = sorted({row.market for row in rows})
    summaries = tuple(
        _summarize(
            market,
            [row for row in rows if row.market == market],
            bootstrap_draws=bootstrap_draws,
            bootstrap_seed=bootstrap_seed + index,
        )
        for index, market in enumerate(markets)
    )
    overall = _summarize(
        "ALL",
        rows,
        bootstrap_draws=bootstrap_draws,
        bootstrap_seed=bootstrap_seed + len(markets),
    )
    return PerformanceReport(total_bets=len(rows), markets=summaries, overall=overall)
