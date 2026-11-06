"""Strict, offline response parser for The Odds API v4 event-odds schema."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Mapping
from urllib.parse import urlencode

from veltrix_v2.ingestion.ports import (
    ProviderBatchResponse,
    ProviderRequestSpec,
    RawProviderRecord,
)
from veltrix_v2.ingestion.providers.errors import ProviderResponseError
from veltrix_v2.ingestion.providers.transport import HttpGetTransport


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
    if isinstance(body, dict):
        body = [body]
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


class TheOddsApiAdapter:
    """Disabled-by-default The Odds API v4 adapter with credit preflight."""

    provider_name = PROVIDER_NAME
    base_url = "https://api.the-odds-api.com/v4"
    allowed_regions = frozenset({"us", "us2", "uk", "au", "eu"})

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport: HttpGetTransport | None = None,
        enabled: bool = False,
        timeout_seconds: float = 15,
    ):
        self._api_key = api_key
        self._transport = transport
        self._enabled = enabled
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _csv_values(value: object, field: str) -> tuple[str, ...]:
        values = tuple(part.strip() for part in str(value or "").split(",") if part.strip())
        if not values:
            raise ProviderResponseError(f"{field.upper()}_REQUIRED")
        if len(set(values)) != len(values):
            raise ProviderResponseError(f"{field.upper()}_DUPLICATES")
        return values

    def _build_url(self, request: ProviderRequestSpec) -> tuple[str, bool]:
        params = dict(request.parameters)
        sport_key = str(params.pop("sport_key", ""))
        if not re.fullmatch(r"[a-z0-9_]+", sport_key):
            raise ProviderResponseError("SPORT_KEY_INVALID")

        if request.endpoint == "sport_events":
            path = f"/sports/{sport_key}/events"
            allowed = {"dateFormat", "commenceTimeFrom", "commenceTimeTo", "eventIds"}
            historical = False
        elif request.endpoint == "sport_odds":
            path = f"/sports/{sport_key}/odds"
            allowed = {"regions", "markets", "oddsFormat", "dateFormat"}
            historical = False
        elif request.endpoint == "historical_sport_odds":
            path = f"/historical/sports/{sport_key}/odds"
            allowed = {"regions", "markets", "date", "oddsFormat", "dateFormat"}
            historical = True
        elif request.endpoint == "event_odds":
            event_id = str(params.pop("event_id", ""))
            if not re.fullmatch(r"[A-Za-z0-9_-]+", event_id):
                raise ProviderResponseError("EVENT_ID_INVALID")
            path = f"/sports/{sport_key}/events/{event_id}/odds"
            allowed = {"regions", "markets", "oddsFormat", "dateFormat"}
            historical = False
        else:
            raise ProviderResponseError("ENDPOINT_NOT_ALLOWLISTED")

        unknown = set(params) - allowed
        if unknown:
            raise ProviderResponseError("UNSUPPORTED_QUERY_PARAMETER")

        if request.endpoint != "sport_events":
            regions = self._csv_values(params.get("regions"), "regions")
            if any(region not in self.allowed_regions for region in regions):
                raise ProviderResponseError("REGION_NOT_ALLOWLISTED")
            markets = self._csv_values(params.get("markets"), "markets")
            if any(not re.fullmatch(r"[a-z0-9_]+", market) for market in markets):
                raise ProviderResponseError("MARKET_KEY_INVALID")
            params["regions"] = ",".join(regions)
            params["markets"] = ",".join(markets)
        else:
            params.setdefault("dateFormat", "iso")

        if historical:
            snapshot_date = params.get("date")
            if not isinstance(snapshot_date, str) or not snapshot_date.strip():
                raise ProviderResponseError("HISTORICAL_SNAPSHOT_DATE_REQUIRED")
            try:
                parsed_date = datetime.fromisoformat(snapshot_date.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ProviderResponseError("HISTORICAL_SNAPSHOT_DATE_INVALID") from exc
            if parsed_date.tzinfo is None:
                raise ProviderResponseError("HISTORICAL_SNAPSHOT_DATE_NOT_TIMEZONE_AWARE")
            regions = self._csv_values(params["regions"], "regions")
            markets = self._csv_values(params["markets"], "markets")
            required_credits = 10 * len(regions) * len(markets)
            if request.quota_units != required_credits:
                raise ProviderResponseError("HISTORICAL_ODDS_CREDIT_RESERVATION_MISMATCH")
        params.setdefault("oddsFormat", "decimal")
        params.setdefault("dateFormat", "iso")
        params["apiKey"] = self._api_key or ""
        return f"{self.base_url}{path}?{urlencode(params)}", historical

    def fetch(self, request: ProviderRequestSpec) -> ProviderBatchResponse:
        if not self._enabled:
            raise ProviderResponseError("PROVIDER_TRANSPORT_DISABLED")
        if not self._api_key:
            raise ProviderResponseError("PROVIDER_CREDENTIAL_MISSING")
        if self._transport is None:
            raise ProviderResponseError("PROVIDER_TRANSPORT_NOT_CONFIGURED")
        if request.provider != self.provider_name:
            raise ProviderResponseError("REQUEST_PROVIDER_MISMATCH")
        url, historical = self._build_url(request)
        try:
            response = self._transport.get(
                url, headers={"Accept": "application/json"},
                timeout_seconds=self._timeout_seconds,
            )
        except ConnectionError as exc:
            raise ProviderResponseError("PROVIDER_NETWORK_ERROR", retryable=True) from exc
        parsed = parse_event_odds_batch(
            request,
            http_status=response.status_code,
            headers=response.headers,
            raw_body=response.body,
            fetched_at_utc=datetime.now(timezone.utc),
        )
        if request.endpoint in {"sport_odds", "historical_sport_odds", "event_odds"}:
            if not parsed.quota_headers.cost_observed:
                raise ProviderResponseError("ODDS_QUOTA_COST_UNOBSERVED")
            if historical and parsed.response.quota_units_consumed != request.quota_units:
                raise ProviderResponseError("HISTORICAL_ODDS_CREDIT_COST_MISMATCH")
            if parsed.response.quota_units_consumed > request.quota_units:
                raise ProviderResponseError("ODDS_QUOTA_COST_EXCEEDED_RESERVATION")
        return parsed.response
