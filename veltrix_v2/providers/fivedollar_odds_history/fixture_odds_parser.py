"""Parser for the 5Dollar per-fixture Bet365 1X2 opening snapshot.

The opening quote has a provider-supplied opened_at timestamp on every plan.
Closing and in-play snapshots are intentionally ignored because this response
shape does not provide their individual source timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class OpeningOddsDiagnostic:
    code: str


@dataclass(frozen=True)
class FiveDollarOpeningOdds:
    provider: str
    source_id: str
    fixture_id: str
    bookmaker_slug: str
    market: str
    home_price: Decimal | None
    draw_price: Decimal | None
    away_price: Decimal | None
    source_timestamp_raw: str | None
    opened_at: datetime | None
    retrieved_at: datetime
    kickoff_at: datetime
    response_sha256: str
    eligible_pit: bool


@dataclass(frozen=True)
class ParsedOpeningOdds:
    observation: FiveDollarOpeningOdds
    diagnostics: tuple[OpeningOddsDiagnostic, ...]


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _price(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= Decimal("1") or number >= Decimal("10000"):
        return None
    return number


def _source_time(value: Any) -> tuple[datetime | None, str | None]:
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


def parse_fixture_opening_1x2(
    raw_body: bytes,
    *,
    expected_fixture_id: str,
    retrieved_at: datetime,
    kickoff_at: datetime,
) -> ParsedOpeningOdds:
    if not isinstance(raw_body, bytes):
        raise TypeError("RAW_RESPONSE_MUST_BE_BYTES")
    if not isinstance(expected_fixture_id, str) or not expected_fixture_id.strip():
        raise ValueError("EXPECTED_FIXTURE_ID_REQUIRED")
    retrieved = _aware(retrieved_at, "RETRIEVED_AT")
    kickoff = _aware(kickoff_at, "KICKOFF_AT")
    digest = hashlib.sha256(raw_body).hexdigest()
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("FIXTURE_ODDS_RESPONSE_INVALID_JSON") from exc
    if not isinstance(payload, dict) or payload.get("success") != 1:
        raise ValueError("FIXTURE_ODDS_RESPONSE_NOT_SUCCESS")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("FIXTURE_ODDS_DATA_INVALID")
    fixture_id_value = data.get("id", data.get("fixture_id"))
    fixture_id = (
        str(fixture_id_value)
        if isinstance(fixture_id_value, (str, int)) and not isinstance(fixture_id_value, bool)
        else ""
    )
    if fixture_id != expected_fixture_id:
        raise ValueError("FIXTURE_ODDS_ID_MISMATCH")
    odds = data.get("odds")
    if not isinstance(odds, dict):
        raise ValueError("FIXTURE_ODDS_BLOCK_MISSING")
    market = odds.get("1x2")
    if not isinstance(market, dict):
        raise ValueError("FIXTURE_ODDS_1X2_MISSING")
    opening = market.get("opening")
    diagnostics: list[OpeningOddsDiagnostic] = []
    if not isinstance(opening, dict):
        opening = {}
        diagnostics.append(OpeningOddsDiagnostic("OPENING_QUOTE_MISSING"))

    home, draw, away = (_price(opening.get(key)) for key in ("home", "draw", "away"))
    opened_at, timestamp_raw = _source_time(opening.get("opened_at"))
    if opened_at is None:
        diagnostics.append(OpeningOddsDiagnostic("OPENING_TIMESTAMP_MISSING_OR_UNTRUSTED"))
    elif opened_at > retrieved:
        diagnostics.append(OpeningOddsDiagnostic("OPENING_TIMESTAMP_AFTER_RETRIEVAL"))
    elif opened_at >= kickoff:
        diagnostics.append(OpeningOddsDiagnostic("OPENING_TIMESTAMP_NOT_PREMATCH"))
    if any(value is None for value in (home, draw, away)):
        diagnostics.append(OpeningOddsDiagnostic("OPENING_1X2_PRICE_INVALID_OR_MISSING"))

    eligible = (
        opened_at is not None and opened_at <= retrieved and opened_at < kickoff
        and all(value is not None for value in (home, draw, away))
    )
    observation = FiveDollarOpeningOdds(
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        fixture_id=fixture_id,
        bookmaker_slug="bet365",
        market="1x2",
        home_price=home,
        draw_price=draw,
        away_price=away,
        source_timestamp_raw=timestamp_raw,
        opened_at=opened_at,
        retrieved_at=retrieved,
        kickoff_at=kickoff,
        response_sha256=digest,
        eligible_pit=eligible,
    )
    return ParsedOpeningOdds(observation=observation, diagnostics=tuple(diagnostics))
