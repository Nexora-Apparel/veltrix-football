from datetime import datetime, timedelta, timezone
from decimal import Decimal

from veltrix_v2.odds.coverage import (
    OddsCoverageState,
    OddsCoverageTarget,
    evaluate_odds_coverage,
)
from veltrix_v2.odds.market_mapping import CanonicalMarket, CanonicalSelection, NormalizedOddsQuote


KICKOFF = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)
CUTOFF = KICKOFF - timedelta(minutes=15)


def target(fixture="fx-1", market=CanonicalMarket.ONE_X_TWO, line=None, age=None):
    required = {
        CanonicalMarket.ONE_X_TWO: (CanonicalSelection.HOME, CanonicalSelection.DRAW, CanonicalSelection.AWAY),
        CanonicalMarket.BTTS: (CanonicalSelection.YES, CanonicalSelection.NO),
        CanonicalMarket.TOTALS: (CanonicalSelection.OVER, CanonicalSelection.UNDER),
    }[market]
    return OddsCoverageTarget(
        canonical_fixture_id=fixture, market=market,
        kickoff_at_utc=KICKOFF, cutoff_at_utc=CUTOFF,
        required_selections=required, required_line=Decimal(str(line)) if line is not None else None,
        max_quote_age_seconds=age,
    )


def quote(selection, *, fixture="fx-1", market=CanonicalMarket.ONE_X_TWO,
          bookmaker="book-a", updated=CUTOFF - timedelta(minutes=1), line=None):
    return NormalizedOddsQuote(
        canonical_fixture_id=fixture, canonical_market=market,
        selection=selection, line=Decimal(str(line)) if line is not None else None,
        decimal_odds=Decimal("2.0"), bookmaker_key=bookmaker,
        bookmaker_title=bookmaker, provider="The Odds API",
        source_id="the-odds-api", provider_event_id="event-1",
        source_record_id="source-1", provider_market_key="market",
        quote_updated_at_utc=updated, fetched_at_utc=CUTOFF,
        raw_response_sha256="a" * 64, mapping_evidence_ref="mapping-1",
    )


def test_complete_same_bookmaker_snapshot_is_covered():
    quotes = [
        quote(CanonicalSelection.HOME),
        quote(CanonicalSelection.DRAW),
        quote(CanonicalSelection.AWAY),
    ]
    result = evaluate_odds_coverage([target()], quotes)
    assert result.results[0].state is OddsCoverageState.COVERED
    assert result.coverage_ratio == Decimal("1")


def test_selections_from_different_bookmakers_are_not_combined():
    quotes = [
        quote(CanonicalSelection.HOME, bookmaker="book-a"),
        quote(CanonicalSelection.DRAW, bookmaker="book-b"),
        quote(CanonicalSelection.AWAY, bookmaker="book-c"),
    ]
    result = evaluate_odds_coverage([target()], quotes)
    assert result.results[0].state is OddsCoverageState.INCOMPLETE


def test_quotes_from_different_timestamps_are_not_combined():
    quotes = [
        quote(CanonicalSelection.HOME, updated=CUTOFF - timedelta(minutes=1)),
        quote(CanonicalSelection.DRAW, updated=CUTOFF - timedelta(minutes=2)),
        quote(CanonicalSelection.AWAY, updated=CUTOFF - timedelta(minutes=3)),
    ]
    result = evaluate_odds_coverage([target()], quotes)
    assert result.results[0].state is OddsCoverageState.INCOMPLETE


def test_post_cutoff_quotes_do_not_count_as_pre_kickoff_coverage():
    quotes = [
        quote(selection, updated=CUTOFF + timedelta(minutes=1))
        for selection in (CanonicalSelection.HOME, CanonicalSelection.DRAW, CanonicalSelection.AWAY)
    ]
    result = evaluate_odds_coverage([target()], quotes)
    assert result.results[0].state is OddsCoverageState.MISSING


def test_stale_pre_cutoff_quotes_are_reported():
    old = CUTOFF - timedelta(hours=8)
    quotes = [
        quote(selection, updated=old)
        for selection in (CanonicalSelection.HOME, CanonicalSelection.DRAW, CanonicalSelection.AWAY)
    ]
    result = evaluate_odds_coverage([target(age=3600)], quotes)
    assert result.results[0].state is OddsCoverageState.STALE


def test_totals_coverage_requires_same_line():
    quotes = [
        quote(CanonicalSelection.OVER, market=CanonicalMarket.TOTALS, line=2.5),
        quote(CanonicalSelection.UNDER, market=CanonicalMarket.TOTALS, line=3.5),
    ]
    result = evaluate_odds_coverage(
        [target(market=CanonicalMarket.TOTALS, line=2.5)], quotes
    )
    assert result.results[0].state is OddsCoverageState.INCOMPLETE


def test_btts_requires_yes_and_no():
    result = evaluate_odds_coverage(
        [target(market=CanonicalMarket.BTTS)],
        [quote(CanonicalSelection.YES, market=CanonicalMarket.BTTS)],
    )
    assert result.results[0].state is OddsCoverageState.INCOMPLETE


def test_98_percent_coverage_threshold_is_applied_to_all_targets():
    targets = [target(f"fx-{i}") for i in range(1, 51)]
    quotes = []
    for i in range(1, 50):
        quotes.extend([
            quote(CanonicalSelection.HOME, fixture=f"fx-{i}"),
            quote(CanonicalSelection.DRAW, fixture=f"fx-{i}"),
            quote(CanonicalSelection.AWAY, fixture=f"fx-{i}"),
        ])
    result = evaluate_odds_coverage(targets, quotes, required_ratio=Decimal("0.98"))
    assert result.coverage_ratio == Decimal("0.98")
    assert result.meets_threshold is True


def test_empty_target_set_does_not_claim_coverage():
    result = evaluate_odds_coverage([], [])
    assert result.coverage_ratio == Decimal("0")
    assert result.meets_threshold is False
