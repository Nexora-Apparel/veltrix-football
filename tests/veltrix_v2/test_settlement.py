from datetime import date
from decimal import Decimal

import pytest

from veltrix_v2.evaluation.settlement import (
    MarketBet,
    MatchResult,
    settle_market_bet,
)


def bet(market, selection, odds="2.0", stake="10", line=None, period="REGULATION"):
    return MarketBet(
        fixture_id="fixture-1",
        market=market,
        selection=selection,
        decimal_odds=Decimal(odds),
        stake=Decimal(stake),
        line=None if line is None else Decimal(str(line)),
        period=period,
    )


def result(home=2, away=1, *, status="COMPLETED", et_home=0, et_away=0):
    return MatchResult(
        fixture_id="fixture-1",
        status=status,
        home_goals_regulation=home,
        away_goals_regulation=away,
        home_goals_extra_time=et_home,
        away_goals_extra_time=et_away,
        match_date=date(2026, 11, 11),
    )


def test_1x2_win_and_loss_return_correct_paper_profit():
    won = settle_market_bet(bet("1X2", "HOME", odds="2.2"), result())
    lost = settle_market_bet(bet("1X2", "AWAY"), result())
    assert (won.status, won.gross_return, won.net_profit) == (
        "WIN", Decimal("22.0"), Decimal("12.0")
    )
    assert (lost.status, lost.gross_return, lost.net_profit) == (
        "LOSS", Decimal("0"), Decimal("-10")
    )


@pytest.mark.parametrize(
    "selection,home,away,expected",
    [
        ("YES", 1, 1, "WIN"),
        ("NO", 1, 1, "LOSS"),
        ("NO", 0, 2, "WIN"),
        ("YES", 0, 2, "LOSS"),
    ],
)
def test_btts_settlement(selection, home, away, expected):
    settled = settle_market_bet(bet("BTTS", selection), result(home, away))
    assert settled.status == expected


def test_integer_total_line_push_returns_stake_without_profit_or_loss():
    settled = settle_market_bet(bet("TOTALS", "OVER", line="2.0"), result(1, 1))
    assert settled.status == "PUSH"
    assert settled.gross_return == Decimal("10")
    assert settled.net_profit == Decimal("0")


@pytest.mark.parametrize(
    "selection,home,away,expected",
    [
        ("OVER", 2, 1, "WIN"),
        ("UNDER", 2, 1, "LOSS"),
        ("UNDER", 1, 1, "WIN"),
        ("OVER", 1, 1, "LOSS"),
    ],
)
def test_half_goal_totals_have_no_push(selection, home, away, expected):
    settled = settle_market_bet(
        bet("TOTALS", selection, line="2.5"), result(home, away)
    )
    assert settled.status == expected


@pytest.mark.parametrize("status", ["ABANDONED", "POSTPONED", "CANCELLED"])
def test_uncompleted_fixtures_are_void_and_stake_is_returned(status):
    settled = settle_market_bet(
        bet("1X2", "HOME"),
        result(status=status, home=1, away=0),
    )
    assert settled.status == "VOID"
    assert settled.gross_return == Decimal("10")
    assert settled.net_profit == Decimal("0")


def test_extra_time_is_excluded_by_default():
    match = result(home=1, away=1, et_home=1, et_away=0)
    regular = settle_market_bet(bet("1X2", "DRAW"), match)
    assert regular.status == "WIN"


def test_extra_time_is_included_only_when_explicitly_selected():
    match = result(home=1, away=1, et_home=1, et_away=0)
    extra_time = settle_market_bet(
        bet("1X2", "HOME", period="INCLUDING_EXTRA_TIME"), match
    )
    assert extra_time.status == "WIN"


def test_penalty_shootout_scores_are_rejected():
    with pytest.raises(ValueError, match="penalty shoot-out"):
        MatchResult(
            fixture_id="fixture-1",
            status="COMPLETED",
            home_goals_regulation=1,
            away_goals_regulation=1,
            penalties_included=True,
        )


def test_fixture_identity_mismatch_is_rejected():
    with pytest.raises(ValueError, match="identity mismatch"):
        settle_market_bet(
            bet("1X2", "HOME"),
            MatchResult("another-fixture", "COMPLETED", 1, 0),
        )


def test_quarter_goal_totals_are_rejected_until_split_stake_logic_exists():
    with pytest.raises(ValueError, match="quarter-goal"):
        bet("TOTALS", "OVER", line="2.25")


def test_invalid_completed_score_is_rejected():
    with pytest.raises(ValueError, match="non-negative integer"):
        result(home=-1, away=0)
