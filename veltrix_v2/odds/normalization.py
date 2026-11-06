"""Strict parser for provider-native odds quotes; no canonical market assumptions."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from veltrix_v2.odds.contracts import (
    OddsNormalizationResult,
    ProviderOddsQuote,
    RejectedOddsQuote,
)


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("QUOTE_TIMESTAMP_MISSING")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("QUOTE_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("QUOTE_TIMESTAMP_NOT_TIMEZONE_AWARE")
    return parsed


def _decimal(value: object, *, allow_zero: bool) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("ODDS_VALUE_INVALID") from exc
    if not parsed.is_finite():
        raise ValueError("ODDS_VALUE_NOT_FINITE")
    if parsed < (Decimal("0") if allow_zero else Decimal("1")):
        raise ValueError("ODDS_VALUE_OUT_OF_RANGE")
    if not allow_zero and parsed <= Decimal("1"):
        raise ValueError("DECIMAL_ODDS_NOT_GREATER_THAN_ONE")
    return parsed


def normalize_event_odds(
    raw_response: bytes,
    *,
    provider: str,
    source_id: str,
    provider_event_id: str,
    provider_competition_id: str,
    source_record_id: str,
    fetched_at_utc: datetime,
) -> OddsNormalizationResult:
    """Extract every usable bookmaker/market/outcome quote from one raw event."""
    if fetched_at_utc.tzinfo is None or fetched_at_utc.utcoffset() is None:
        raise ValueError("fetched_at_utc must be timezone-aware")
    digest = sha256(raw_response).hexdigest()
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ODDS_RESPONSE_INVALID_JSON") from exc
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict):
        events = [payload]
    else:
        raise ValueError("ODDS_RESPONSE_INVALID_SHAPE")

    event = next(
        (
            item for item in events
            if isinstance(item, dict) and str(item.get("id")) == provider_event_id
        ),
        None,
    )
    if event is None:
        raise ValueError("PROVIDER_EVENT_ID_NOT_FOUND")
    if str(event.get("sport_key")) != provider_competition_id:
        raise ValueError("PROVIDER_COMPETITION_ID_MISMATCH")
    home_name, away_name = event.get("home_team"), event.get("away_team")
    if not isinstance(home_name, str) or not home_name.strip():
        raise ValueError("HOME_TEAM_NAME_MISSING")
    if not isinstance(away_name, str) or not away_name.strip():
        raise ValueError("AWAY_TEAM_NAME_MISSING")

    bookmakers = event.get("bookmakers")
    if not isinstance(bookmakers, list):
        raise ValueError("BOOKMAKERS_NOT_LIST")

    quotes: list[ProviderOddsQuote] = []
    rejected: list[RejectedOddsQuote] = []
    fetched = fetched_at_utc
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            rejected.append(RejectedOddsQuote(provider_event_id, None, None, None, "BOOKMAKER_ROW_INVALID"))
            continue
        bookmaker_key = bookmaker.get("key")
        bookmaker_title = bookmaker.get("title")
        if not isinstance(bookmaker_key, str) or not bookmaker_key.strip():
            rejected.append(RejectedOddsQuote(provider_event_id, None, None, None, "BOOKMAKER_KEY_MISSING"))
            continue
        if not isinstance(bookmaker_title, str) or not bookmaker_title.strip():
            rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, None, None, "BOOKMAKER_TITLE_MISSING"))
            continue
        markets = bookmaker.get("markets")
        if not isinstance(markets, list):
            rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, None, None, "MARKETS_NOT_LIST"))
            continue
        for market in markets:
            if not isinstance(market, dict):
                rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, None, None, "MARKET_ROW_INVALID"))
                continue
            market_key = market.get("key")
            if not isinstance(market_key, str) or not market_key.strip():
                rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, None, None, "MARKET_KEY_MISSING"))
                continue
            try:
                updated = _parse_timestamp(market.get("last_update"))
            except ValueError as exc:
                rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, market_key, None, str(exc)))
                continue
            if updated > fetched:
                rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, market_key, None, "QUOTE_TIMESTAMP_AFTER_FETCH"))
                continue
            outcomes = market.get("outcomes")
            if not isinstance(outcomes, list):
                rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, market_key, None, "OUTCOMES_NOT_LIST"))
                continue
            for outcome in outcomes:
                if not isinstance(outcome, dict):
                    rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, market_key, None, "OUTCOME_ROW_INVALID"))
                    continue
                outcome_name = outcome.get("name")
                if not isinstance(outcome_name, str) or not outcome_name.strip():
                    rejected.append(RejectedOddsQuote(provider_event_id, bookmaker_key, market_key, None, "OUTCOME_NAME_MISSING"))
                    continue
                try:
                    odds = _decimal(outcome.get("price"), allow_zero=False)
                    point = (
                        _decimal(outcome["point"], allow_zero=True)
                        if outcome.get("point") is not None else None
                    )
                    quotes.append(ProviderOddsQuote(
                        provider=provider,
                        source_id=source_id,
                        provider_event_id=provider_event_id,
                        provider_competition_id=provider_competition_id,
                        source_record_id=source_record_id,
                        home_team_name=home_name,
                        away_team_name=away_name,
                        bookmaker_key=bookmaker_key,
                        bookmaker_title=bookmaker_title,
                        provider_market_key=market_key,
                        outcome_name=outcome_name,
                        decimal_odds=odds,
                        point=point,
                        quote_updated_at_utc=updated,
                        fetched_at_utc=fetched,
                        raw_response_sha256=digest,
                    ))
                except ValueError as exc:
                    rejected.append(RejectedOddsQuote(
                        provider_event_id, bookmaker_key, market_key,
                        outcome_name, str(exc),
                    ))

    return OddsNormalizationResult(
        quotes=tuple(quotes),
        rejected=tuple(rejected),
        raw_response_sha256=digest,
    )
