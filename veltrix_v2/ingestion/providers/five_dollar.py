"""Strict, offline response parser for the 5DollarFootballAPI fixture schema.

This module performs no HTTP requests and reads no credentials. Transport,
account capability, quota reservation and persistence remain separate ports.
"""
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
