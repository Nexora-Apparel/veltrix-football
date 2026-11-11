"""Deterministic paper-settlement contracts for football markets.

Settlement is based on an explicitly declared match period. Penalty shoot-outs
are never included. Postponed, cancelled and abandoned fixtures are void; no
partial abandoned score is treated as a completed result.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

MatchStatus = Literal["COMPLETED", "ABANDONED", "POSTPONED", "CANCELLED"]
Market = Literal["1X2", "BTTS", "TOTALS", "OVER_UNDER"]
Period = Literal["REGULATION", "INCLUDING_EXTRA_TIME"]
SettlementStatus = Literal["WIN", "LOSS", "PUSH", "VOID"]


def _money(value: Decimal | str | int | float, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class MatchResult:
    fixture_id: str
    status: MatchStatus
    home_goals_regulation: int | None = None
    away_goals_regulation: int | None = None
    home_goals_extra_time: int = 0
    away_goals_extra_time: int = 0
    penalties_included: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.fixture_id, str) or not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if self.status not in ("COMPLETED", "ABANDONED", "POSTPONED", "CANCELLED"):
            raise ValueError("unsupported match status")
        if self.status == "COMPLETED":
            if self.home_goals_regulation is None or self.away_goals_regulation is None:
                raise ValueError("completed match requires regulation-time goals")
            for name in ("home_goals_regulation", "away_goals_regulation",
                         "home_goals_extra_time", "away_goals_extra_time"):
                value = getattr(self, name)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{name} must be a non-negative integer")
        if self.penalties_included:
            raise ValueError("penalty shoot-out goals must never enter match settlement")


@dataclass(frozen=True, slots=True)
class MarketBet:
    fixture_id: str
    market: Market
    selection: str
    decimal_odds: Decimal
    stake: Decimal
    line: Decimal | None = None
    period: Period = "REGULATION"

    def __post_init__(self) -> None:
        if not isinstance(self.fixture_id, str) or not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if self.market not in ("1X2", "BTTS", "TOTALS", "OVER_UNDER"):
            raise ValueError("unsupported market")
        if not isinstance(self.selection, str) or not self.selection.strip():
            raise ValueError("selection is required")
        odds = _money(self.decimal_odds, "decimal_odds")
        stake = _money(self.stake, "stake")
        if odds <= Decimal("1"):
            raise ValueError("decimal_odds must be greater than 1")
        if stake <= Decimal("0"):
            raise ValueError("stake must be positive")
        if self.period not in ("REGULATION", "INCLUDING_EXTRA_TIME"):
            raise ValueError("unsupported settlement period")
        line = None if self.line is None else _money(self.line, "line")
        if self.market in ("TOTALS", "OVER_UNDER"):
            if line is None or line < 0:
                raise ValueError("totals market requires a non-negative line")
            if self.selection.upper() not in ("OVER", "UNDER"):
                raise ValueError("totals selection must be OVER or UNDER")
        elif line is not None:
            raise ValueError("line is only valid for totals markets")
        if self.market == "1X2" and self.selection.upper() not in ("HOME", "DRAW", "AWAY"):
            raise ValueError("1X2 selection must be HOME, DRAW or AWAY")
        if self.market == "BTTS" and self.selection.upper() not in ("YES", "NO"):
            raise ValueError("BTTS selection must be YES or NO")
        object.__setattr__(self, "decimal_odds", odds)
        object.__setattr__(self, "stake", stake)
        object.__setattr__(self, "line", line)
        object.__setattr__(self, "selection", self.selection.upper())


@dataclass(frozen=True, slots=True)
class Settlement:
    fixture_id: str
    market: str
    selection: str
    status: SettlementStatus
    stake: Decimal
    decimal_odds: Decimal
    gross_return: Decimal
    net_profit: Decimal
    period: str


def settle_market_bet(bet: MarketBet, result: MatchResult) -> Settlement:
    if bet.fixture_id != result.fixture_id:
        raise ValueError("settlement fixture identity mismatch")

    if result.status != "COMPLETED":
        status: SettlementStatus = "VOID"
        gross_return = bet.stake
    else:
        home = result.home_goals_regulation
        away = result.away_goals_regulation
        assert home is not None and away is not None
        if bet.period == "INCLUDING_EXTRA_TIME":
            home += result.home_goals_extra_time
            away += result.away_goals_extra_time

        if bet.market == "1X2":
            actual = "HOME" if home > away else "AWAY" if home < away else "DRAW"
            won = bet.selection == actual
            status = "WIN" if won else "LOSS"
        elif bet.market == "BTTS":
            actual_yes = home > 0 and away > 0
            won = (bet.selection == "YES") == actual_yes
            status = "WIN" if won else "LOSS"
        else:
            total = Decimal(home + away)
            assert bet.line is not None
            if total == bet.line:
                status = "PUSH"
            else:
                actual_over = total > bet.line
                won = (bet.selection == "OVER") == actual_over
                status = "WIN" if won else "LOSS"

        if status == "WIN":
            gross_return = bet.stake * bet.decimal_odds
        elif status == "LOSS":
            gross_return = Decimal("0")
        else:  # PUSH
            gross_return = bet.stake

    return Settlement(
        fixture_id=bet.fixture_id,
        market=bet.market,
        selection=bet.selection,
        status=status,
        stake=bet.stake,
        decimal_odds=bet.decimal_odds,
        gross_return=gross_return,
        net_profit=gross_return - bet.stake,
        period=bet.period,
    )
