"""Pure offline parser for archived The Odds API v4 response bodies.

This module performs no network, environment, database, or prediction operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Mapping


@dataclass(frozen=True)
class ParseDiagnostic:
    code: str
    path: str


@dataclass(frozen=True)
class QuoteObservation:
    provider: str
    sport_key: str
    provider_event_id: str
    bookmaker_key: str
    bookmaker_title: str
    market_key: str
    selection_name: str
    selection_key: str
    decimal_price: Decimal
    point: Decimal | None
    source_published_at: datetime | None
    source_timestamp_raw: str | None
    source_timestamp_basis: str
    retrieved_at: datetime
    response_sha256: str
    eligible_timestamp: bool


@dataclass(frozen=True)
class ParsedCapture:
    observations: tuple[QuoteObservation, ...]
    diagnostics: tuple[ParseDiagnostic, ...]
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
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None, raw
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, raw
    return parsed.astimezone(timezone.utc), raw


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def _point(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _selection_key(name: str) -> str:
    return " ".join(name.casefold().split())


def _parse(
    raw_body: bytes,
    *,
    sport_key: str,
    retrieved_at: datetime,
    expected_event_id: str | None,
    allowed_markets: frozenset[str],
) -> ParsedCapture:
    if not isinstance(raw_body, bytes):
        raise TypeError("RAW_RESPONSE_MUST_BE_BYTES")
    if not isinstance(sport_key, str) or not sport_key.strip():
        raise ValueError("SPORT_KEY_REQUIRED")
    retrieved = _aware(retrieved_at, "RETRIEVED_AT")
    digest = hashlib.sha256(raw_body).hexdigest()
    diagnostics: list[ParseDiagnostic] = []
    observations: list[QuoteObservation] = []
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ODDS_RESPONSE_INVALID_JSON") from exc

    events = [payload] if isinstance(payload, dict) else payload if isinstance(payload, list) else None
    if events is None:
        raise ValueError("ODDS_RESPONSE_UNEXPECTED_ROOT_SHAPE")

    seen: set[tuple[Any, ...]] = set()
    for ei, event in enumerate(events):
        ep = f"events[{ei}]"
        if not isinstance(event, dict):
            diagnostics.append(ParseDiagnostic("EVENT_SHAPE_INVALID", ep))
            continue
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            diagnostics.append(ParseDiagnostic("EVENT_ID_MISSING", ep))
            continue
        if expected_event_id is not None and event_id != expected_event_id:
            diagnostics.append(ParseDiagnostic("EVENT_ID_MISMATCH", ep))
            continue
        bookmakers = event.get("bookmakers")
        if not isinstance(bookmakers, list):
            diagnostics.append(ParseDiagnostic("BOOKMAKERS_SHAPE_INVALID", ep))
            continue
        for bi, bookmaker in enumerate(bookmakers):
            bp = f"{ep}.bookmakers[{bi}]"
            if not isinstance(bookmaker, dict) or not isinstance(bookmaker.get("key"), str) or not bookmaker.get("key") or not isinstance(bookmaker.get("title"), str) or not bookmaker.get("title"):
                diagnostics.append(ParseDiagnostic("BOOKMAKER_IDENTITY_MISSING", bp))
                continue
            markets = bookmaker.get("markets")
            if not isinstance(markets, list):
                diagnostics.append(ParseDiagnostic("MARKETS_SHAPE_INVALID", bp))
                continue
            for mi, market in enumerate(markets):
                mp = f"{bp}.markets[{mi}]"
                if not isinstance(market, dict):
                    diagnostics.append(ParseDiagnostic("MARKET_SHAPE_INVALID", mp))
                    continue
                market_key = market.get("key")
                if not isinstance(market_key, str) or market_key not in allowed_markets:
                    if market_key is not None and not isinstance(market_key, str):
                        diagnostics.append(ParseDiagnostic("MARKET_KEY_INVALID", mp))
                    continue
                published, raw_timestamp = _timestamp(market.get("last_update"))
                if published is None:
                    diagnostics.append(ParseDiagnostic("MARKET_TIMESTAMP_MISSING_OR_UNTRUSTED", mp))
                outcomes = market.get("outcomes")
                if not isinstance(outcomes, list):
                    diagnostics.append(ParseDiagnostic("OUTCOMES_SHAPE_INVALID", mp))
                    continue
                for oi, outcome in enumerate(outcomes):
                    op = f"{mp}.outcomes[{oi}]"
                    if not isinstance(outcome, dict) or not isinstance(outcome.get("name"), str) or not outcome.get("name"):
                        diagnostics.append(ParseDiagnostic("SELECTION_NAME_MISSING", op))
                        continue
                    price = _decimal(outcome.get("price"))
                    if price is None:
                        diagnostics.append(ParseDiagnostic("PRICE_INVALID", op))
                        continue
                    point = None
                    if market_key == "totals":
                        point = _point(outcome.get("point"))
                        if point is None:
                            diagnostics.append(ParseDiagnostic("TOTALS_POINT_INVALID", op))
                            continue
                    name = outcome["name"]
                    identity = (event_id, bookmaker["key"], market_key, name, point, published, price)
                    if identity in seen:
                        diagnostics.append(ParseDiagnostic("DUPLICATE_QUOTE_ROW", op))
                    seen.add(identity)
                    observations.append(QuoteObservation(
                        provider="the_odds_api",
                        sport_key=sport_key,
                        provider_event_id=event_id,
                        bookmaker_key=bookmaker["key"],
                        bookmaker_title=bookmaker["title"],
                        market_key=market_key,
                        selection_name=name,
                        selection_key=_selection_key(name),
                        decimal_price=price,
                        point=point,
                        source_published_at=published,
                        source_timestamp_raw=raw_timestamp,
                        source_timestamp_basis="provider_timestamp",
                        retrieved_at=retrieved,
                        response_sha256=digest,
                        eligible_timestamp=published is not None,
                    ))
    return ParsedCapture(tuple(observations), tuple(diagnostics), digest)


def parse_bulk_odds(raw_body: bytes, *, sport_key: str, retrieved_at: datetime) -> ParsedCapture:
    """Parse bulk current-odds events for h2h and totals without selecting prices."""
    return _parse(raw_body, sport_key=sport_key, retrieved_at=retrieved_at,
                  expected_event_id=None, allowed_markets=frozenset({"h2h", "totals"}))


def parse_event_odds(raw_body: bytes, *, sport_key: str, event_id: str, retrieved_at: datetime) -> ParsedCapture:
    """Parse a single event-specific response; only BTTS is normalized here."""
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("EVENT_ID_REQUIRED")
    return _parse(raw_body, sport_key=sport_key, retrieved_at=retrieved_at,
                  expected_event_id=event_id, allowed_markets=frozenset({"btts"}))
