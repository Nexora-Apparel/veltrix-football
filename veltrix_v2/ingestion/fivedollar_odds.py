"""Pure parser for timestamped 5DollarFootballAPI per-fixture odds snapshots.

The caller supplies the UTC time at which VELTRIX retrieved the response.
Only pre-match Bet365 closing/current prices are emitted. Missing markets are
reported, never synthesized. The fixed 2.5 total line is selected explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any

from veltrix_v2.contracts.odds import OddsSnapshot

SOURCE_ID = "5dollarfootballapi"


@dataclass(frozen=True, slots=True)
class FiveDollarOddsCapture:
    fixture_id: str
    captured_at: datetime
    bookmaker_id: str
    snapshots: tuple[OddsSnapshot, ...]
    missing_markets: tuple[str, ...]


def _price(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite() or price <= Decimal("1"):
        return None
    return price


def _snapshot_id(
    fixture_id: str, market: str, selection: str, line: Decimal | None,
    captured_at: datetime, bookmaker_id: str,
) -> str:
    raw = "|".join((
        fixture_id, market, selection, str(line) if line is not None else "",
        captured_at.isoformat(), bookmaker_id,
    ))
    return "5d:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_fivedollar_fixture_odds(
    payload: dict[str, Any],
    *,
    fixture_id: str,
    kickoff_at: datetime,
    captured_at: datetime,
    bookmaker_slug: str = "bet365",
    total_line: Decimal = Decimal("2.5"),
) -> FiveDollarOddsCapture:
    if not isinstance(payload, dict) or payload.get("success") != 1:
        raise ValueError("FIVEDOLLAR_ODDS_RESPONSE_NOT_SUCCESS")
    if not fixture_id or not fixture_id.strip():
        raise ValueError("FIVEDOLLAR_ODDS_FIXTURE_ID_REQUIRED")
    if kickoff_at.tzinfo is None or kickoff_at.utcoffset() is None:
        raise ValueError("FIVEDOLLAR_ODDS_KICKOFF_MUST_BE_AWARE")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("FIVEDOLLAR_ODDS_CAPTURE_MUST_BE_AWARE")
    if not isinstance(total_line, Decimal) or not total_line.is_finite():
        raise ValueError("FIVEDOLLAR_ODDS_TOTAL_LINE_INVALID")
    if total_line < 0 or total_line % Decimal("1") != Decimal("0.5"):
        raise ValueError("FIVEDOLLAR_ODDS_TOTAL_LINE_MUST_BE_HALF_GOAL")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("FIVEDOLLAR_ODDS_DATA_MISSING")
    response_fixture_id = str(data.get("fixture_id", ""))
    if response_fixture_id and response_fixture_id != str(fixture_id):
        raise ValueError("FIVEDOLLAR_ODDS_FIXTURE_ID_MISMATCH")
    books = data.get("bookmakers")
    if not isinstance(books, list):
        raise ValueError("FIVEDOLLAR_ODDS_BOOKMAKERS_MISSING")
    book = next(
        (item for item in books if isinstance(item, dict) and item.get("slug") == bookmaker_slug),
        None,
    )
    if book is None:
        raise ValueError("FIVEDOLLAR_ODDS_BOOKMAKER_MISSING")
    odds = book.get("odds")
    if not isinstance(odds, dict):
        raise ValueError("FIVEDOLLAR_ODDS_MARKETS_MISSING")
    capture = captured_at.astimezone(timezone.utc)
    kickoff = kickoff_at.astimezone(timezone.utc)
    if capture >= kickoff:
        raise ValueError("FIVEDOLLAR_ODDS_CAPTURE_MUST_PRECEDE_KICKOFF")
    bookmaker_id = str(book.get("slug", bookmaker_slug))
    snapshots: list[OddsSnapshot] = []
    present: set[str] = set()

    def add_market(market: str, values: dict[str, Any], selections: tuple[str, ...], line: Decimal | None = None) -> None:
        prices = {selection: _price(values.get(selection.lower())) for selection in selections}
        if any(price is None for price in prices.values()):
            return
        for selection in selections:
            price = prices[selection]
            assert price is not None
            snapshots.append(OddsSnapshot(
                snapshot_id=_snapshot_id(str(fixture_id), market, selection, line, capture, bookmaker_id),
                fixture_id=str(fixture_id),
                source_id=SOURCE_ID,
                bookmaker_id=bookmaker_id,
                market=market,
                selection=selection,
                decimal_odds=price,
                captured_at=capture,
                kickoff_at=kickoff,
                line=line,
            ))
        present.add(market)

    one_x_two = odds.get("1x2")
    if isinstance(one_x_two, dict) and isinstance(one_x_two.get("closing"), dict):
        add_market("1X2", one_x_two["closing"], ("HOME", "DRAW", "AWAY"))

    btts = odds.get("btts")
    if isinstance(btts, dict) and isinstance(btts.get("closing"), dict):
        add_market("BTTS", btts["closing"], ("YES", "NO"))

    fixed_lines = odds.get("goal_line_fixed")
    if isinstance(fixed_lines, list):
        selected = next(
            (
                item for item in fixed_lines
                if isinstance(item, dict)
                and item.get("line") is not None
                and Decimal(str(item["line"])) == total_line
            ),
            None,
        )
        if selected is not None and isinstance(selected.get("closing"), dict):
            add_market("TOTALS", selected["closing"], ("OVER", "UNDER"), total_line)

    expected = ("1X2", "BTTS", "TOTALS")
    return FiveDollarOddsCapture(
        fixture_id=str(fixture_id),
        captured_at=capture,
        bookmaker_id=bookmaker_id,
        snapshots=tuple(snapshots),
        missing_markets=tuple(market for market in expected if market not in present),
    )
