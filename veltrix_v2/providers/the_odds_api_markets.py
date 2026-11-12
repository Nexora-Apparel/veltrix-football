"""The Odds API 1X2 and totals quote parsers.

These snapshots support independent bookmaker benchmarking and value/CLV
analysis. They are not model-strength features. Every quote must be linked to
the immutable ProviderObservation that captured the provider response.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.providers.the_odds_api import SOURCE_ID


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"THE_ODDS_{field.upper()}_MUST_BE_AWARE")
    return value.astimezone(timezone.utc)


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if result.tzinfo is None or result.utcoffset() is None:
        return None
    return result.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _price(value: Any) -> Decimal | None:
    result = _decimal(value)
    return result if result is not None and result > Decimal("1") else None


def _event(
    payload: Any, *, provider_event_id: str, kickoff_at: datetime,
    captured_at: datetime, source_observation_id: str,
) -> tuple[dict[str, Any], datetime, datetime]:
    if not isinstance(provider_event_id, str) or not provider_event_id.strip():
        raise ValueError("THE_ODDS_PROVIDER_EVENT_ID_REQUIRED")
    if not isinstance(source_observation_id, str) or not source_observation_id.strip():
        raise ValueError("THE_ODDS_SOURCE_OBSERVATION_ID_REQUIRED")
    kickoff = _utc(kickoff_at, "kickoff")
    captured = _utc(captured_at, "capture")
    if captured >= kickoff:
        raise ValueError("THE_ODDS_CAPTURE_MUST_PRECEDE_KICKOFF")
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    matches = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("id") or "") == provider_event_id
    ]
    if len(matches) != 1:
        raise ValueError("THE_ODDS_EVENT_MISSING_OR_DUPLICATE")
    event = matches[0]
    event_kickoff = _time(event.get("commence_time"))
    if event_kickoff is None:
        raise ValueError("THE_ODDS_EVENT_KICKOFF_TIMESTAMP_MISSING")
    if event_kickoff != kickoff:
        raise ValueError("THE_ODDS_EVENT_KICKOFF_MISMATCH")
    return event, kickoff, captured


def _snapshot_id(
    fixture_id: str, event_id: str, bookmaker_id: str, market: str,
    selection: str, line: Decimal | None, captured_at: datetime,
) -> str:
    raw = "|".join((
        fixture_id, event_id, bookmaker_id, market, selection,
        "" if line is None else str(line), captured_at.isoformat(),
    ))
    return "toa:" + sha256(raw.encode("utf-8")).hexdigest()


def _base_rows(
    event: dict[str, Any], *, fixture_id: str, provider_event_id: str,
    kickoff: datetime, captured: datetime, source_observation_id: str,
    market_key: str,
):
    home = str(event.get("home_team") or "").strip()
    away = str(event.get("away_team") or "").strip()
    if market_key == "h2h" and (not home or not away or home.casefold() == away.casefold()):
        raise ValueError("THE_ODDS_HOME_AWAY_TEAM_IDENTITY_INVALID")
    seen: set[str] = set()
    for bookmaker in event.get("bookmakers") or []:
        if not isinstance(bookmaker, dict):
            continue
        bookmaker_id = str(bookmaker.get("key") or "").strip()
        if not bookmaker_id:
            continue
        if bookmaker_id in seen:
            raise ValueError("THE_ODDS_DUPLICATE_BOOKMAKER_ID")
        seen.add(bookmaker_id)
        market = next((
            row for row in bookmaker.get("markets") or []
            if isinstance(row, dict) and row.get("key") == market_key
        ), None)
        if market is None:
            continue
        quote_at = _time(market.get("last_update"))
        if quote_at is None:
            raise ValueError("THE_ODDS_QUOTE_TIMESTAMP_MISSING")
        if quote_at > captured or quote_at >= kickoff:
            raise ValueError("THE_ODDS_QUOTE_TIMESTAMP_OUT_OF_RANGE")
        yield bookmaker_id, market, quote_at, home, away


def parse_event_1x2_odds(
    payload: Any,
    *,
    fixture_id: str,
    provider_event_id: str,
    kickoff_at: datetime,
    captured_at: datetime,
    source_observation_id: str,
) -> tuple[OddsSnapshot, ...]:
    """Parse complete same-bookmaker 1X2 markets from a captured h2h response."""
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ValueError("THE_ODDS_FIXTURE_ID_REQUIRED")
    event, kickoff, captured = _event(
        payload, provider_event_id=provider_event_id, kickoff_at=kickoff_at,
        captured_at=captured_at, source_observation_id=source_observation_id,
    )
    output: list[OddsSnapshot] = []
    for bookmaker_id, market, quote_at, home, away in _base_rows(
        event, fixture_id=fixture_id, provider_event_id=provider_event_id,
        kickoff=kickoff, captured=captured, source_observation_id=source_observation_id,
        market_key="h2h",
    ):
        prices: dict[str, Decimal] = {}
        for outcome in market.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            name = str(outcome.get("name") or "").strip().casefold()
            selection = (
                "DRAW" if name == "draw"
                else "HOME" if name == home.casefold()
                else "AWAY" if name == away.casefold()
                else None
            )
            price = _price(outcome.get("price"))
            if selection and price is not None:
                if selection in prices:
                    raise ValueError("THE_ODDS_1X2_DUPLICATE_SELECTION")
                prices[selection] = price
        if set(prices) != {"HOME", "DRAW", "AWAY"}:
            continue
        for selection in ("HOME", "DRAW", "AWAY"):
            output.append(OddsSnapshot(
                snapshot_id=_snapshot_id(
                    fixture_id, provider_event_id, bookmaker_id, "1X2",
                    selection, None, captured,
                ),
                fixture_id=fixture_id,
                source_id=SOURCE_ID,
                bookmaker_id=bookmaker_id,
                market="1X2",
                selection=selection,
                decimal_odds=prices[selection],
                captured_at=captured,
                kickoff_at=kickoff,
                provider_quote_at=quote_at,
                provider_event_id=provider_event_id,
                source_observation_id=source_observation_id,
            ))
    return tuple(output)


def parse_event_totals_odds(
    payload: Any,
    *,
    fixture_id: str,
    provider_event_id: str,
    kickoff_at: datetime,
    captured_at: datetime,
    source_observation_id: str,
) -> tuple[OddsSnapshot, ...]:
    """Parse complete Over/Under pairs, retaining each provider line separately."""
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ValueError("THE_ODDS_FIXTURE_ID_REQUIRED")
    event, kickoff, captured = _event(
        payload, provider_event_id=provider_event_id, kickoff_at=kickoff_at,
        captured_at=captured_at, source_observation_id=source_observation_id,
    )
    output: list[OddsSnapshot] = []
    for bookmaker_id, market, quote_at, _, _ in _base_rows(
        event, fixture_id=fixture_id, provider_event_id=provider_event_id,
        kickoff=kickoff, captured=captured, source_observation_id=source_observation_id,
        market_key="totals",
    ):
        grouped: dict[Decimal, dict[str, Decimal]] = {}
        for outcome in market.get("outcomes") or []:
            if not isinstance(outcome, dict):
                continue
            name = str(outcome.get("name") or "").strip().casefold()
            selection = "OVER" if name == "over" else "UNDER" if name == "under" else None
            line = _decimal(outcome.get("point"))
            price = _price(outcome.get("price"))
            if selection is None or line is None or line <= 0 or price is None:
                continue
            group = grouped.setdefault(line, {})
            if selection in group:
                raise ValueError("THE_ODDS_TOTALS_DUPLICATE_SELECTION")
            group[selection] = price
        for line, prices in sorted(grouped.items()):
            if set(prices) != {"OVER", "UNDER"}:
                continue
            for selection in ("OVER", "UNDER"):
                output.append(OddsSnapshot(
                    snapshot_id=_snapshot_id(
                        fixture_id, provider_event_id, bookmaker_id, "TOTALS",
                        selection, line, captured,
                    ),
                    fixture_id=fixture_id,
                    source_id=SOURCE_ID,
                    bookmaker_id=bookmaker_id,
                    market="TOTALS",
                    selection=selection,
                    decimal_odds=prices[selection],
                    captured_at=captured,
                    kickoff_at=kickoff,
                    line=line,
                    provider_quote_at=quote_at,
                    provider_event_id=provider_event_id,
                    source_observation_id=source_observation_id,
                ))
    return tuple(output)


@dataclass(frozen=True, slots=True)
class TheOddsMarketCapture:
    fixture_id: str
    provider_event_id: str
    market: str
    captured_at: datetime
    snapshots: tuple[OddsSnapshot, ...]
    requests_remaining: int | None
    requests_used: int | None
    last_request_cost: int | None


def fetch_event_market_odds(
    *,
    api_key: str,
    sport_key: str,
    event_id: str,
    fixture_id: str,
    market: str,
    kickoff_at: datetime,
    captured_at: datetime,
    source_observation_id: str,
    regions: str = "uk",
    timeout_seconds: float = 15.0,
    opener=None,
) -> TheOddsMarketCapture:
    """Fetch one market for one event; one market per request bounds quota cost."""
    import json
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode, quote
    from urllib.request import Request, urlopen

    from veltrix_v2.providers.the_odds_api import BASE_URL, TheOddsProviderError

    market_key = {"1X2": "h2h", "TOTALS": "totals"}.get(market)
    if market_key is None:
        raise ValueError("THE_ODDS_MARKET_UNSUPPORTED")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("THE_ODDS_API_KEY_REQUIRED")
    if not isinstance(sport_key, str) or not sport_key.strip():
        raise ValueError("THE_ODDS_SPORT_KEY_REQUIRED")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("THE_ODDS_PROVIDER_EVENT_ID_REQUIRED")
    if not isinstance(source_observation_id, str) or not source_observation_id.strip():
        raise ValueError("THE_ODDS_SOURCE_OBSERVATION_ID_REQUIRED")
    kickoff = _utc(kickoff_at, "kickoff")
    captured = _utc(captured_at, "capture")
    if captured >= kickoff:
        raise ValueError("THE_ODDS_CAPTURE_MUST_PRECEDE_KICKOFF")
    query = urlencode({
        "apiKey": api_key,
        "regions": regions,
        "markets": market_key,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    })
    url = (
        f"{BASE_URL}/sports/{quote(sport_key, safe='')}/events/"
        f"{quote(event_id, safe='')}/odds?{query}"
    )
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "VELTRIX-FOOTBALL/2.0"},
        method="GET",
    )
    opener = opener or urlopen
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

    parser = parse_event_1x2_odds if market == "1X2" else parse_event_totals_odds
    snapshots = parser(
        payload,
        fixture_id=fixture_id,
        provider_event_id=event_id,
        kickoff_at=kickoff,
        captured_at=captured,
        source_observation_id=source_observation_id,
    )

    def header_int(name: str) -> int | None:
        try:
            return int(headers.get(name))
        except (TypeError, ValueError):
            return None

    return TheOddsMarketCapture(
        fixture_id=fixture_id,
        provider_event_id=event_id,
        market=market,
        captured_at=captured,
        snapshots=snapshots,
        requests_remaining=header_int("x-requests-remaining"),
        requests_used=header_int("x-requests-used"),
        last_request_cost=header_int("x-requests-last"),
    )


def fetch_event_1x2_odds(**kwargs) -> TheOddsMarketCapture:
    return fetch_event_market_odds(market="1X2", **kwargs)


def fetch_event_totals_odds(**kwargs) -> TheOddsMarketCapture:
    return fetch_event_market_odds(market="TOTALS", **kwargs)
