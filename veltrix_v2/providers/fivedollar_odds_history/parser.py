"""Strict parser for 5DollarFootballAPI timestamped odds-history responses.

The parser is offline-only. It preserves source recorded_at separately from
local retrieved_at and marks a tick pre-match only when its timestamp is
strictly before the fixture kickoff and the provider tick has no in-play
minute, score, half-time or suspension marker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class OddsHistoryDiagnostic:
    code: str
    tick_index: int | None = None


@dataclass(frozen=True)
class FiveDollarOddsTick:
    provider: str
    source_id: str
    fixture_id: str
    bookmaker_slug: str
    bookmaker_name: str
    market: str
    tick_index: int
    recorded_at: datetime | None
    source_timestamp_raw: str | None
    retrieved_at: datetime
    minute: int | None
    line: Decimal | None
    home_price: Decimal | None
    draw_price: Decimal | None
    away_price: Decimal | None
    over_price: Decimal | None
    under_price: Decimal | None
    score_home: int | None
    score_away: int | None
    half_time: bool
    suspended: bool
    prematch_state: bool
    before_kickoff: bool
    eligible_prematch: bool
    response_sha256: str


@dataclass(frozen=True)
class ParsedOddsHistory:
    fixture_id: str
    bookmaker_slug: str
    market: str
    observations: tuple[FiveDollarOddsTick, ...]
    diagnostics: tuple[OddsHistoryDiagnostic, ...]
    response_sha256: str


def _aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _timestamp(value: Any) -> tuple[datetime | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    raw = value
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None, raw
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, raw
    return parsed.astimezone(timezone.utc), raw


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed <= Decimal("1") or parsed >= Decimal("10000"):
        return None
    return parsed


def _score(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def parse_odds_history(
    raw_body: bytes,
    *,
    expected_fixture_id: str,
    expected_market: str,
    retrieved_at: datetime,
    kickoff_at: datetime,
) -> ParsedOddsHistory:
    """Parse one fixture/bookmaker/market response without performing I/O."""
    if not isinstance(raw_body, bytes):
        raise TypeError("RAW_RESPONSE_MUST_BE_BYTES")
    if not isinstance(expected_fixture_id, str) or not expected_fixture_id.strip():
        raise ValueError("EXPECTED_FIXTURE_ID_REQUIRED")
    if not isinstance(expected_market, str) or expected_market not in {
        "1x2", "asian", "goalline", "goalline_fixed", "btts",
        "corner", "corner_asian", "cards", "cards_asian",
        "1x2_half", "asian_half", "goalline_half", "corner_half",
    }:
        raise ValueError("EXPECTED_MARKET_UNSUPPORTED")
    retrieved = _aware(retrieved_at, "RETRIEVED_AT")
    kickoff = _aware(kickoff_at, "KICKOFF_AT")
    digest = hashlib.sha256(raw_body).hexdigest()
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ODDS_HISTORY_RESPONSE_INVALID_JSON") from exc
    if not isinstance(payload, dict) or payload.get("success") != 1:
        raise ValueError("ODDS_HISTORY_RESPONSE_NOT_SUCCESS")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("ODDS_HISTORY_DATA_INVALID")
    fixture_value = data.get("fixture_id")
    fixture_id = str(fixture_value) if isinstance(fixture_value, (str, int)) and not isinstance(fixture_value, bool) else ""
    if fixture_id != expected_fixture_id:
        raise ValueError("ODDS_HISTORY_FIXTURE_ID_MISMATCH")
    bookmaker = data.get("bookmaker")
    if not isinstance(bookmaker, dict):
        raise ValueError("ODDS_HISTORY_BOOKMAKER_INVALID")
    slug, name = bookmaker.get("slug"), bookmaker.get("name")
    if not isinstance(slug, str) or not slug.strip() or not isinstance(name, str) or not name.strip():
        raise ValueError("ODDS_HISTORY_BOOKMAKER_IDENTITY_MISSING")
    market = data.get("market")
    if market != expected_market:
        raise ValueError("ODDS_HISTORY_MARKET_MISMATCH")
    ticks = data.get("ticks")
    if not isinstance(ticks, list):
        raise ValueError("ODDS_HISTORY_TICKS_INVALID")

    observations: list[FiveDollarOddsTick] = []
    diagnostics: list[OddsHistoryDiagnostic] = []
    seen: set[tuple[Any, ...]] = set()
    previous_time: datetime | None = None

    for index, tick in enumerate(ticks):
        if not isinstance(tick, dict):
            diagnostics.append(OddsHistoryDiagnostic("TICK_SHAPE_INVALID", index))
            continue
        recorded_at, timestamp_raw = _timestamp(tick.get("recorded_at"))
        if recorded_at is None:
            diagnostics.append(OddsHistoryDiagnostic("TICK_TIMESTAMP_MISSING_OR_UNTRUSTED", index))
        elif recorded_at > retrieved:
            diagnostics.append(OddsHistoryDiagnostic("TICK_TIMESTAMP_AFTER_RETRIEVAL", index))
        if recorded_at is not None and previous_time is not None and recorded_at < previous_time:
            diagnostics.append(OddsHistoryDiagnostic("TICK_ORDER_NOT_CHRONOLOGICAL", index))
        if recorded_at is not None:
            previous_time = recorded_at

        minute_value = tick.get("minute")
        minute = minute_value if isinstance(minute_value, int) and not isinstance(minute_value, bool) and minute_value >= 0 else None
        if minute_value is not None and minute is None:
            diagnostics.append(OddsHistoryDiagnostic("TICK_MINUTE_INVALID", index))
        line = _decimal(tick.get("line")) if tick.get("line") is not None else None

        home = _decimal(tick.get("home"))
        draw = _decimal(tick.get("draw"))
        away = _decimal(tick.get("away"))
        over = _decimal(tick.get("over"))
        under = _decimal(tick.get("under"))
        score = tick.get("score")
        if score is not None and not isinstance(score, dict):
            diagnostics.append(OddsHistoryDiagnostic("TICK_SCORE_INVALID", index))
            score = {}
        score = score or {}
        score_home = _score(score.get("home"))
        score_away = _score(score.get("away"))
        half_time = tick.get("half_time", False)
        suspended = tick.get("suspended", False)
        if type(half_time) is not bool or type(suspended) is not bool:
            diagnostics.append(OddsHistoryDiagnostic("TICK_STATE_FLAG_INVALID", index))
            half_time = half_time is True
            suspended = suspended is True

        prematch_state = (
            minute is None and score_home is None and score_away is None
            and not half_time and not suspended
        )
        before_kickoff = recorded_at is not None and recorded_at < kickoff
        if recorded_at is not None and recorded_at == kickoff:
            diagnostics.append(OddsHistoryDiagnostic("TICK_AT_KICKOFF_EXCLUDED", index))
        if recorded_at is not None and recorded_at > kickoff:
            diagnostics.append(OddsHistoryDiagnostic("TICK_AFTER_KICKOFF_EXCLUDED", index))

        if expected_market == "1x2":
            prices_valid = all(value is not None for value in (home, draw, away))
        elif expected_market == "goalline":
            prices_valid = line is not None and over is not None and under is not None
        elif expected_market == "goalline_fixed":
            prices_valid = line is not None and over is not None and under is not None
        elif expected_market == "btts":
            prices_valid = home is not None and away is not None
        else:
            prices_valid = any(value is not None for value in (home, draw, away, over, under))

        identity = (
            recorded_at, minute, line, home, draw, away, over, under,
            score_home, score_away, half_time, suspended,
        )
        if identity in seen:
            diagnostics.append(OddsHistoryDiagnostic("DUPLICATE_TICK", index))
        seen.add(identity)
        eligible = (
            recorded_at is not None and recorded_at <= retrieved
            and prematch_state and before_kickoff and prices_valid and not suspended
        )
        if not prices_valid:
            diagnostics.append(OddsHistoryDiagnostic("TICK_PRICE_OR_LINE_MISSING", index))

        observations.append(FiveDollarOddsTick(
            provider="5DollarFootballAPI",
            source_id="5dollarfootballapi",
            fixture_id=fixture_id,
            bookmaker_slug=slug,
            bookmaker_name=name,
            market=market,
            tick_index=index,
            recorded_at=recorded_at,
            source_timestamp_raw=timestamp_raw,
            retrieved_at=retrieved,
            minute=minute,
            line=line,
            home_price=home,
            draw_price=draw,
            away_price=away,
            over_price=over,
            under_price=under,
            score_home=score_home,
            score_away=score_away,
            half_time=half_time,
            suspended=suspended,
            prematch_state=prematch_state,
            before_kickoff=before_kickoff,
            eligible_prematch=eligible,
            response_sha256=digest,
        ))

    return ParsedOddsHistory(
        fixture_id=fixture_id, bookmaker_slug=slug, market=market,
        observations=tuple(observations), diagnostics=tuple(diagnostics),
        response_sha256=digest,
    )
