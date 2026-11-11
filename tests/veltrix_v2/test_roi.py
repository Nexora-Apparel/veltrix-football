from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from veltrix_v2.evaluation.roi import evaluate_roi
from veltrix_v2.evaluation.settlement import (
    MarketBet, MatchResult, settle_market_bet,
)


def settled(fixture, market, selection, *, status_result="COMPLETED",
            home=2, away=1, odds="2.0", stake="10", line=None, match_date=None):
    bet = MarketBet(
        fixture_id=fixture, market=market, selection=selection,
        decimal_odds=Decimal(odds), stake=Decimal(stake),
        line=None if line is None else Decimal(line),
    )
    result = MatchResult(
        fixture_id=fixture, status=status_result,
        home_goals_regulation=home, away_goals_regulation=away,
        match_date=(match_date if match_date is not None else date(2026, 11, int(fixture[1:]) if fixture[1:].isdigit() else 1)),
        match_date_source_observation_id=(f"obs-{fixture}" if (match_date is not None or fixture) else None),
    )
    return settle_market_bet(bet, result)


def test_roi_accounts_for_win_loss_push_and_excludes_void_turnover():
    rows = [
        settled("f1", "1X2", "HOME", odds="2.0", stake="10"),
        settled("f2", "1X2", "AWAY", odds="3.0", stake="20"),
        settled("f3", "TOTALS", "OVER", home=1, away=1, line="2.0"),
        settled("f4", "BTTS", "YES", status_result="POSTPONED"),
    ]
    report = evaluate_roi(rows, bootstrap_draws=500)
    overall = report.overall
    assert (overall.wins, overall.losses, overall.pushes, overall.voids) == (1, 1, 1, 1)
    assert overall.settled_turnover == Decimal("40")
    assert overall.gross_return == Decimal("30")
    assert overall.net_profit == Decimal("-10")
    assert overall.roi == Decimal("-0.25")
    assert overall.win_rate == Decimal("0.5")
    assert overall.win_rate_ci_95 is not None
    assert overall.roi_ci_95 is not None
    assert overall.roi_ci_method == "date_block_bootstrap_by_match_date"


def test_market_summaries_are_separate():
    rows = [
        settled("f1", "1X2", "HOME"),
        settled("f2", "BTTS", "NO", home=0, away=1),
    ]
    report = evaluate_roi(rows, bootstrap_draws=0)
    by_market = {item.market: item for item in report.markets}
    assert set(by_market) == {"1X2", "BTTS"}
    assert by_market["1X2"].wins == 1
    assert by_market["BTTS"].wins == 1


def test_void_only_sample_has_no_roi_or_win_rate():
    rows = [settled("f1", "1X2", "HOME", status_result="CANCELLED")]
    summary = evaluate_roi(rows).overall
    assert summary.roi is None
    assert summary.win_rate is None
    assert summary.settled_turnover == Decimal("0")
    assert summary.voids == 1


def test_empty_sample_returns_zero_counts_and_null_rates():
    report = evaluate_roi([])
    assert report.total_bets == 0
    assert report.overall.total_bets == 0
    assert report.overall.roi is None
    assert report.overall.win_rate is None
    assert report.markets == ()


def test_duplicate_settlement_identity_is_rejected():
    row = settled("f1", "1X2", "HOME")
    with pytest.raises(ValueError, match="duplicate settlement identity"):
        evaluate_roi([row, row])


def test_malformed_profit_is_rejected():
    row = settled("f1", "1X2", "HOME")
    with pytest.raises(ValueError, match="net_profit"):
        evaluate_roi([replace(row, net_profit=Decimal("999"))])


def test_invalid_money_values_are_rejected():
    row = settled("f1", "1X2", "HOME")
    with pytest.raises(ValueError, match="finite Decimal"):
        evaluate_roi([replace(row, stake=Decimal("NaN"))])


def test_bootstrap_interval_is_deterministic():
    rows = [
        settled("f1", "1X2", "HOME"),
        settled("f2", "1X2", "AWAY"),
        settled("f3", "1X2", "HOME", odds="1.8"),
    ]
    first = evaluate_roi(rows, bootstrap_draws=500).overall.roi_ci_95
    second = evaluate_roi(rows, bootstrap_draws=500).overall.roi_ci_95
    assert first == second


def test_invalid_bootstrap_draw_count_is_rejected():
    with pytest.raises(ValueError, match="bootstrap_draws"):
        evaluate_roi([], bootstrap_draws=-1)


def test_date_block_bootstrap_groups_all_fixtures_from_each_match_date():
    same_date = [
        settled("f1", "1X2", "HOME", match_date=date(2026, 11, 1)),
        settled("f2", "BTTS", "YES", match_date=date(2026, 11, 1)),
    ]
    report = evaluate_roi(same_date, bootstrap_draws=500)
    assert report.overall.roi_ci_95 is None
    assert report.overall.roi_ci_method == "unavailable_insufficient_match_dates"

    multiple_dates = same_date + [
        settled("f3", "1X2", "AWAY", match_date=date(2026, 11, 2)),
        settled("f4", "BTTS", "NO", home=0, away=1, match_date=date(2026, 11, 2)),
        settled("f5", "1X2", "HOME", odds="1.8", match_date=date(2026, 11, 3)),
    ]
    first = evaluate_roi(multiple_dates, bootstrap_draws=500).overall.roi_ci_95
    second = evaluate_roi(multiple_dates, bootstrap_draws=500).overall.roi_ci_95
    assert first is not None
    assert first == second


def test_missing_source_match_date_withholds_roi_interval():
    rows = [
        settled("f1", "1X2", "HOME", match_date=date(2026, 11, 1)),
        settled("f2", "1X2", "AWAY", match_date=None),
    ]
    report = evaluate_roi(rows, bootstrap_draws=500)
    assert report.overall.roi_ci_95 is None
    assert report.overall.roi_ci_method == "unavailable_missing_match_date"


def test_conflicting_match_date_provenance_for_one_fixture_is_rejected():
    first = settled("f1", "1X2", "HOME", match_date=date(2026, 11, 1))
    second = settled("f1", "BTTS", "YES", match_date=date(2026, 11, 2))
    with pytest.raises(ValueError, match="match-date provenance conflicts"):
        evaluate_roi([first, second])
