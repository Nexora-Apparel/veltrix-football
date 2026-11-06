"""Strict, offline response parser for the 5DollarFootballAPI fixture schema.

This module performs no HTTP requests and reads no credentials. Transport,
account capability, quota reservation and persistence remain separate ports.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping
from urllib.parse import urlencode

from veltrix_v2.ingestion.providers.errors import ProviderResponseError
from veltrix_v2.ingestion.providers.transport import HttpGetTransport
from veltrix_v2.ingestion.ports import (
    ProviderBatchResponse,
    ProviderRequestSpec,
    RawProviderRecord,
)


PROVIDER_NAME = "5DollarFootballAPI"
SOURCE_ID = "5dollarfootballapi"


class ProviderLeagueRedirect(ProviderResponseError):
    def __init__(self, old_provider_competition_id: str, canonical_provider_competition_id: str):
        super().__init__("PROVIDER_LEAGUE_ID_REDIRECT", retryable=False)
        self.old_provider_competition_id = old_provider_competition_id
        self.canonical_provider_competition_id = canonical_provider_competition_id


@dataclass(frozen=True, slots=True)
class FiveDollarQuotaHeaders:
    limit: int | None
    remaining: int | None
    reset: str | None
    retry_after_seconds: int | None


@dataclass(frozen=True, slots=True)
class ParsedFiveDollarBatch:
    response: ProviderBatchResponse
    pagination_page: int
    pagination_per_page: int
    has_more: bool
    quota_headers: FiveDollarQuotaHeaders


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


def _parse_body(raw_body: bytes) -> dict:
    try:
        value = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderResponseError("PROVIDER_RESPONSE_INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise ProviderResponseError("PROVIDER_RESPONSE_NOT_OBJECT")
    return value


def parse_fixture_batch(
    request: ProviderRequestSpec,
    *,
    http_status: int,
    headers: Mapping[str, str],
    raw_body: bytes,
    fetched_at_utc: datetime,
) -> ParsedFiveDollarBatch:
    """Parse one fixture-list response while retaining the exact response bytes."""
    if request.provider != PROVIDER_NAME:
        raise ProviderResponseError("REQUEST_PROVIDER_MISMATCH")
    if fetched_at_utc.tzinfo is None or fetched_at_utc.utcoffset() is None:
        raise ProviderResponseError("FETCH_TIMESTAMP_NOT_TIMEZONE_AWARE")

    quota_headers = FiveDollarQuotaHeaders(
        limit=_integer_header(headers, "X-RateLimit-Limit"),
        remaining=_integer_header(headers, "X-RateLimit-Remaining"),
        reset=_header(headers, "X-RateLimit-Reset"),
        retry_after_seconds=_integer_header(headers, "Retry-After"),
    )
    if http_status == 429:
        raise ProviderResponseError(
            "PROVIDER_RATE_LIMITED",
            retryable=True,
            retry_after_seconds=quota_headers.retry_after_seconds,
        )
    if http_status in {401, 403}:
        raise ProviderResponseError("PROVIDER_AUTH_OR_PLAN_DENIED")
    if http_status >= 500:
        raise ProviderResponseError("PROVIDER_SERVER_ERROR", retryable=True)

    body = _parse_body(raw_body) if raw_body else {}

    if http_status == 301 and (body.get("error") or {}).get("code") == "league_moved":
        old_id = request.parameters.get("league_id")
        new_id = (body.get("error") or {}).get("canonical_id")
        if old_id is None or new_id is None:
            raise ProviderResponseError("LEAGUE_REDIRECT_MISSING_IDENTITY")
        raise ProviderLeagueRedirect(str(old_id), str(new_id))
    if http_status != 200:
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        code = str(error.get("code") or f"HTTP_{http_status}").upper()
        raise ProviderResponseError(f"PROVIDER_REQUEST_REJECTED:{code}")

    if body.get("success") != 1:
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        code = str(error.get("code") or "UNSUCCESSFUL_RESPONSE").upper()
        raise ProviderResponseError(f"PROVIDER_REQUEST_REJECTED:{code}")

    data = body.get("data")
    if not isinstance(data, list):
        raise ProviderResponseError("FIXTURE_DATA_NOT_LIST")

    records: list[RawProviderRecord] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ProviderResponseError(f"FIXTURE_ROW_NOT_OBJECT:{index}")
        league = item.get("league") if isinstance(item.get("league"), dict) else {}
        teams = item.get("teams") if isinstance(item.get("teams"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        fixture_id = item.get("id")
        competition_id = league.get("id")
        home_id, away_id = home.get("id"), away.get("id")
        if fixture_id is None or competition_id is None or home_id is None or away_id is None:
            raise ProviderResponseError(f"FIXTURE_SOURCE_IDENTITY_INCOMPLETE:{index}")
        records.append(RawProviderRecord(
            provider=PROVIDER_NAME,
            source_id=SOURCE_ID,
            provider_record_id=str(fixture_id),
            provider_fixture_id=str(fixture_id),
            provider_competition_id=str(competition_id),
            data_class=request.data_class,
            raw_payload=raw_body,
            provider_home_team_id=str(home_id),
            provider_away_team_id=str(away_id),
        ))

    pagination = body.get("pagination") if isinstance(body.get("pagination"), dict) else {}
    page = pagination.get("page", request.parameters.get("page", 1))
    per_page = pagination.get("per_page", request.parameters.get("per_page", len(data) or 1))
    try:
        page, per_page = int(page), int(per_page)
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("PAGINATION_METADATA_INVALID") from exc
    if page < 1 or per_page < 1:
        raise ProviderResponseError("PAGINATION_METADATA_INVALID")

    response = ProviderBatchResponse(
        request_id=request.request_id,
        provider=PROVIDER_NAME,
        fetched_at_utc=fetched_at_utc,
        records=tuple(records),
        quota_units_consumed=request.quota_units,
    )
    return ParsedFiveDollarBatch(
        response=response,
        pagination_page=page,
        pagination_per_page=per_page,
        has_more=bool(pagination.get("has_more", False)),
        quota_headers=quota_headers,
    )


class FiveDollarFixtureAdapter:
    """Disabled-by-default 5Dollar fixture transport with strict endpoint allowlisting."""

    provider_name = PROVIDER_NAME
    base_url = "https://api.5dollarfootballapi.com/v1"

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

    def _build_url(self, request: ProviderRequestSpec) -> str:
        if request.data_class != "fixtures":
            raise ProviderResponseError("UNSUPPORTED_DATA_CLASS")
        params = dict(request.parameters)
        if request.endpoint == "fixtures":
            allowed = {"start_time", "end_time", "status", "page", "per_page", "lang"}
            if "start_time" not in params or "end_time" not in params:
                raise ProviderResponseError("FIXTURE_WINDOW_REQUIRED")
            try:
                start, end = int(params["start_time"]), int(params["end_time"])
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError("FIXTURE_WINDOW_INVALID") from exc
            if end <= start or end - start > 86400:
                raise ProviderResponseError("FIXTURE_WINDOW_EXCEEDS_24_HOURS")
            path = "/fixtures"
        elif request.endpoint == "league_fixtures":
            allowed = {"league_id", "start_time", "end_time", "season", "status", "page", "per_page", "order", "lang"}
            league_id = params.pop("league_id", None)
            if league_id is None or not str(league_id).isdigit():
                raise ProviderResponseError("LEAGUE_ID_REQUIRED")
            if request.competition_ids and str(league_id) not in request.competition_ids:
                raise ProviderResponseError("LEAGUE_ID_OUTSIDE_REQUEST_SCOPE")
            path = f"/leagues/{league_id}/fixtures"
        elif request.endpoint == "team_fixtures":
            allowed = {"team_id", "start_time", "end_time", "status", "page", "per_page", "order", "lang"}
            team_id = params.pop("team_id", None)
            if team_id is None or not str(team_id).isdigit():
                raise ProviderResponseError("TEAM_ID_REQUIRED")
            path = f"/teams/{team_id}/fixtures"
        else:
            raise ProviderResponseError("ENDPOINT_NOT_ALLOWLISTED")

        unknown = set(params) - allowed
        if unknown:
            raise ProviderResponseError("UNSUPPORTED_QUERY_PARAMETER")
        if "page" in params:
            try:
                page = int(params["page"])
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError("PAGE_INVALID") from exc
            if page < 1:
                raise ProviderResponseError("PAGE_MUST_BE_POSITIVE")
        try:
            per_page = int(params.get("per_page", 100))
        except (TypeError, ValueError) as exc:
            raise ProviderResponseError("PER_PAGE_INVALID") from exc
        if not 1 <= per_page <= 100:
            raise ProviderResponseError("PER_PAGE_OUT_OF_RANGE")
        if "start_time" in params or "end_time" in params:
            try:
                start, end = int(params["start_time"]), int(params["end_time"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProviderResponseError("FIXTURE_WINDOW_INVALID") from exc
            if end <= start:
                raise ProviderResponseError("FIXTURE_WINDOW_INVALID")
        if "status" in params and params["status"] not in {"all", "scheduled", "live", "finished", "unknown"}:
            raise ProviderResponseError("INVALID_FIXTURE_STATUS")
        if "order" in params and params["order"] not in {"asc", "desc"}:
            raise ProviderResponseError("INVALID_FIXTURE_ORDER")
        return f"{self.base_url}{path}?{urlencode(params)}"

    def fetch(self, request: ProviderRequestSpec) -> ProviderBatchResponse:
        if not self._enabled:
            raise ProviderResponseError("PROVIDER_TRANSPORT_DISABLED")
        if not self._api_key:
            raise ProviderResponseError("PROVIDER_CREDENTIAL_MISSING")
        if self._transport is None:
            raise ProviderResponseError("PROVIDER_TRANSPORT_NOT_CONFIGURED")
        if request.provider != self.provider_name:
            raise ProviderResponseError("REQUEST_PROVIDER_MISMATCH")
        url = self._build_url(request)
        try:
            response = self._transport.get(
                url,
                headers={"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"},
                timeout_seconds=self._timeout_seconds,
            )
        except ConnectionError as exc:
            raise ProviderResponseError("PROVIDER_NETWORK_ERROR", retryable=True) from exc
        parsed = parse_fixture_batch(
            request,
            http_status=response.status_code,
            headers=response.headers,
            raw_body=response.body,
            fetched_at_utc=datetime.now(timezone.utc),
        )
        return parsed.response
