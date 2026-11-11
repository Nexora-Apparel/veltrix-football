"""The Odds API v4 BTTS fallback with timestamp-preserving snapshots.

This client is intended only for missing BTTS quotes after the primary
5Dollar per-fixture board has been inspected. Calls are event-specific and
consume monthly quota; callers must enforce a per-day/per-month budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
import hashlib
import json

from veltrix_v2.contracts.odds import OddsSnapshot

BASE_URL = "https://api.the-odds-api.com/v4"
SOURCE_ID = "the-odds-api"


@dataclass(frozen=True, slots=True)
class TheOddsBTTSCapture:
    fixture_id: str
    provider_event_id: str
    sport_key: str
    captured_at: datetime
    snapshots: tuple[OddsSnapshot, ...]
    missing_bookmakers: tuple[str, ...]
    requests_remaining: int | None
    requests_used: int | None
    last_request_cost: int | None


class TheOddsProviderError(RuntimeError):
    def __init__(self, status_code: int | None, code: str, retry_after: str | None = None):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.retry_after = retry_after


def _aware(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"THE_ODDS_{field.upper()}_MUST_BE_AWARE")
    return value.astimezone(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _price(value: Any) -> Decimal | None:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not price.is_finite() or price <= Decimal("1"):
        return None
    return price


def _snapshot_id(
    fixture_id: str, event_id: str, bookmaker: str, selection: str,
    captured_at: datetime,
) -> str:
    raw = "|".join((fixture_id, event_id, bookmaker, selection, captured_at.isoformat()))
    return "toa:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_event_btts_odds(
    payload: Any,
    *,
    fixture_id: str,
    provider_event_id: str,
    sport_key: str,
    kickoff_at: datetime,
    captured_at: datetime,
) -> TheOddsBTTSCapture:
    if not fixture_id or not fixture_id.strip() or not provider_event_id or not provider_event_id.strip():
        raise ValueError("THE_ODDS_FIXTURE_AND_EVENT_IDS_REQUIRED")
    kickoff = _aware(kickoff_at, "kickoff")
    captured = _aware(captured_at, "capture")
    if captured >= kickoff:
        raise ValueError("THE_ODDS_CAPTURE_MUST_PRECEDE_KICKOFF")
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    matching = [
        row for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("id"), str)
        and str(row.get("id")) == str(provider_event_id)
    ]
    if not matching:
        raise ValueError("THE_ODDS_EVENT_NOT_FOUND_IN_RESPONSE")
    event = matching[0]
    event_kickoff = _parse_time(event.get("commence_time"))
    if event_kickoff is None:
        raise ValueError("THE_ODDS_EVENT_KICKOFF_TIMESTAMP_MISSING")
    if event_kickoff != kickoff:
        raise ValueError("THE_ODDS_EVENT_KICKOFF_MISMATCH")

    snapshots: list[OddsSnapshot] = []
    seen_bookmakers: set[str] = set()
    missing: list[str] = []
    for bookmaker in event.get("bookmakers") or []:
        if not isinstance(bookmaker, dict):
            continue
        bookmaker_id = str(bookmaker.get("key") or "").strip()
        if not bookmaker_id:
            continue
        seen_bookmakers.add(bookmaker_id)
        btts_market = next(
            (
                market for market in bookmaker.get("markets") or []
                if isinstance(market, dict) and market.get("key") == "btts"
            ),
            None,
        )
        if btts_market is None:
            missing.append(bookmaker_id)
            continue
        quote_at = _parse_time(btts_market.get("last_update"))
        if quote_at is None:
            missing.append(bookmaker_id)
            continue
        if quote_at > captured:
            raise ValueError("THE_ODDS_QUOTE_TIMESTAMP_AFTER_CAPTURE")
        prices: dict[str, Decimal] = {}
        for outcome in btts_market.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            name = str(outcome.get("name") or "").strip().casefold()
            selection = "YES" if name in {"yes", "btts yes", "both teams to score - yes"} else "NO" if name in {"no", "btts no", "both teams to score - no"} else None
            price = _price(outcome.get("price"))
            if selection and price is not None and selection not in prices:
                prices[selection] = price
        if set(prices) != {"YES", "NO"}:
            missing.append(bookmaker_id)
            continue
        for selection in ("YES", "NO"):
            snapshots.append(OddsSnapshot(
                snapshot_id=_snapshot_id(str(fixture_id), str(provider_event_id), bookmaker_id, selection, captured),
                fixture_id=str(fixture_id),
                source_id=SOURCE_ID,
                bookmaker_id=bookmaker_id,
                market="BTTS",
                selection=selection,
                decimal_odds=prices[selection],
                captured_at=captured,
                kickoff_at=kickoff,
                provider_quote_at=quote_at,
                provider_event_id=str(provider_event_id),
            ))
    if not seen_bookmakers:
        raise ValueError("THE_ODDS_EVENT_HAS_NO_BOOKMAKERS")
    return TheOddsBTTSCapture(
        fixture_id=str(fixture_id),
        provider_event_id=str(provider_event_id),
        sport_key=str(sport_key),
        captured_at=captured,
        snapshots=tuple(snapshots),
        missing_bookmakers=tuple(sorted(set(missing))),
        requests_remaining=None,
        requests_used=None,
        last_request_cost=None,
    )


def fetch_event_btts_odds(
    *,
    api_key: str,
    sport_key: str,
    event_id: str,
    fixture_id: str,
    kickoff_at: datetime,
    captured_at: datetime,
    regions: str = "uk",
    timeout_seconds: float = 15.0,
    opener: Callable = urlopen,
) -> TheOddsBTTSCapture:
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("THE_ODDS_API_KEY_REQUIRED")
    if not sport_key or not sport_key.strip() or not event_id or not event_id.strip():
        raise ValueError("THE_ODDS_SPORT_AND_EVENT_IDS_REQUIRED")
    kickoff = _aware(kickoff_at, "kickoff")
    captured = _aware(captured_at, "capture")
    if captured >= kickoff:
        raise ValueError("THE_ODDS_CAPTURE_MUST_PRECEDE_KICKOFF")
    path = f"sports/{quote(sport_key, safe='')}/events/{quote(event_id, safe='')}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": "btts",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    request = Request(
        f"{BASE_URL}/{path}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "VELTRIX-FOOTBALL/2.0"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            body = response.read()
            headers = response.headers
    except HTTPError as error:
        retry_after = error.headers.get("Retry-After") if error.headers else None
        code = {
            401: "THE_ODDS_AUTHENTICATION_FAILED",
            429: "THE_ODDS_QUOTA_OR_RATE_LIMIT",
        }.get(error.code, "THE_ODDS_HTTP_ERROR")
        raise TheOddsProviderError(error.code, code, retry_after) from None
    except URLError:
        raise TheOddsProviderError(None, "THE_ODDS_NETWORK_ERROR") from None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TheOddsProviderError(None, "THE_ODDS_INVALID_JSON") from None
    result = parse_event_btts_odds(
        payload,
        fixture_id=fixture_id,
        provider_event_id=event_id,
        sport_key=sport_key,
        kickoff_at=kickoff,
        captured_at=captured,
    )
    def header_int(name: str) -> int | None:
        try:
            return int(headers.get(name))
        except (TypeError, ValueError):
            return None
    return TheOddsBTTSCapture(
        fixture_id=result.fixture_id,
        provider_event_id=result.provider_event_id,
        sport_key=result.sport_key,
        captured_at=result.captured_at,
        snapshots=result.snapshots,
        missing_bookmakers=result.missing_bookmakers,
        requests_remaining=header_int("x-requests-remaining"),
        requests_used=header_int("x-requests-used"),
        last_request_cost=header_int("x-requests-last"),
    )
