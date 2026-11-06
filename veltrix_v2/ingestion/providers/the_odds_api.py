"""Strict, offline response parser for The Odds API v4 event-odds schema."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from veltrix_v2.ingestion.ports import (
    ProviderBatchResponse,
    ProviderRequestSpec,
    RawProviderRecord,
)
from veltrix_v2.ingestion.providers.five_dollar import ProviderResponseError


PROVIDER_NAME = "The Odds API"
SOURCE_ID = "the-odds-api"


@dataclass(frozen=True, slots=True)
class OddsApiQuotaHeaders:
    remaining: int | None
    used: int | None
    last_cost: int | None
    cost_observed: bool


@dataclass(frozen=True, slots=True)
class ParsedOddsApiBatch:
    response: ProviderBatchResponse
    quota_headers: OddsApiQuotaHeaders
    market_keys_seen: tuple[str, ...]


def _header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.casefold()
    return next((str(value) for key, value in headers.items() if key.casefold() == target), None)


def _integer_header(headers: Mapping[str, str], name: str) -> int | None:
    value = _header(headers, name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_event_odds_batch(
    request: ProviderRequestSpec,
    *,
    http_status: int,
    headers: Mapping[str, str],
    raw_body: bytes,
    fetched_at_utc: datetime,
) -> ParsedOddsApiBatch:
    """Parse one odds response without assuming that BTTS or totals exist."""
    if request.provider != PROVIDER_NAME:
        raise ProviderResponseError("REQUEST_PROVIDER_MISMATCH")
    if fetched_at_utc.tzinfo is None or fetched_at_utc.utcoffset() is None:
        raise ProviderResponseError("FETCH_TIMESTAMP_NOT_TIMEZONE_AWARE")

    quota = OddsApiQuotaHeaders(
        remaining=_integer_header(headers, "x-requests-remaining"),
        used=_integer_header(headers, "x-requests-used"),
        last_cost=_integer_header(headers, "x-requests-last"),
        cost_observed=_integer_header(headers, "x-requests-last") is not None,
    )
    retry_after = _integer_header(headers, "Retry-After")
    if http_status == 429:
        raise ProviderResponseError(
            "PROVIDER_RATE_LIMITED", retryable=True,
            retry_after_seconds=retry_after,
        )
    if http_status in {401, 403}:
        raise ProviderResponseError("PROVIDER_AUTH_OR_PLAN_DENIED")
    if http_status >= 500:
        raise ProviderResponseError("PROVIDER_SERVER_ERROR", retryable=True)
    if http_status != 200:
        raise ProviderResponseError(f"PROVIDER_REQUEST_REJECTED:HTTP_{http_status}")

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID_JSON") from exc
    if not isinstance(body, list):
        raise ProviderResponseError("ODDS_RESPONSE_NOT_LIST")

    records: list[RawProviderRecord] = []
    market_keys: set[str] = set()
    for index, event in enumerate(body):
        if not isinstance(event, dict):
            raise ProviderResponseError(f"ODDS_EVENT_NOT_OBJECT:{index}")
        event_id = event.get("id")
        sport_key = event.get("sport_key")
        if not event_id or not sport_key:
            raise ProviderResponseError(f"ODDS_EVENT_IDENTITY_INCOMPLETE:{index}")
        bookmakers = event.get("bookmakers")
        if bookmakers is not None and not isinstance(bookmakers, list):
            raise ProviderResponseError(f"ODDS_BOOKMAKERS_NOT_LIST:{index}")
        for bookmaker in bookmakers or []:
            if not isinstance(bookmaker, dict):
                continue
            markets = bookmaker.get("markets") or []
            if not isinstance(markets, list):
                raise ProviderResponseError(f"ODDS_MARKETS_NOT_LIST:{index}")
            for market in markets:
                if isinstance(market, dict) and isinstance(market.get("key"), str):
                    market_keys.add(market["key"])
        records.append(RawProviderRecord(
            provider=PROVIDER_NAME,
            source_id=SOURCE_ID,
            provider_record_id=str(event_id),
            provider_fixture_id=str(event_id),
            provider_competition_id=str(sport_key),
            data_class=request.data_class,
            raw_payload=raw_body,
        ))

    consumed = quota.last_cost if quota.last_cost is not None else request.quota_units
    if consumed < 0:
        raise ProviderResponseError("ODDS_QUOTA_COST_INVALID")
    response = ProviderBatchResponse(
        request_id=request.request_id,
        provider=PROVIDER_NAME,
        fetched_at_utc=fetched_at_utc,
        records=tuple(records),
        quota_units_consumed=consumed,
    )
    return ParsedOddsApiBatch(
        response=response,
        quota_headers=quota,
        market_keys_seen=tuple(sorted(market_keys)),
    )
