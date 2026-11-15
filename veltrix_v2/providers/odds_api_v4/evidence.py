"""Fail-closed point-in-time admission for The Odds API quote evidence.

Pure validation only: no network, database, environment, or model access.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class FixtureCrosswalk:
    provider: str
    source_id: str
    provider_event_id: str
    fixture_id: int
    entity_type: str
    status: str
    valid_from: datetime
    valid_until: datetime | None
    crosswalk_version_id: int


@dataclass(frozen=True)
class QuoteRights:
    approval_id: str
    provider: str
    source_id: str
    status: str
    permitted_uses: frozenset[str]
    effective_at: datetime
    recorded_at: datetime
    valid_until: datetime | None
    evidence_sha256: str


@dataclass(frozen=True)
class QuoteAdmission:
    admitted: bool
    reason_codes: tuple[str, ...]
    observation_key: str | None


def quote_observation_key(*, provider: str, source_id: str, sport_key: str,
                          provider_event_id: str, bookmaker_key: str,
                          market_key: str, selection_key: str,
                          line_point: Decimal | None, decimal_price: Decimal,
                          source_published_at: datetime, retrieved_at: datetime,
                          response_sha256: str) -> str:
    """Stable idempotency key. Price/timestamp/hash changes create a new event."""
    payload = {
        "provider": provider, "source_id": source_id, "sport_key": sport_key,
        "provider_event_id": provider_event_id, "bookmaker_key": bookmaker_key,
        "market_key": market_key, "selection_key": selection_key,
        "line_point": str(line_point) if line_point is not None else None,
        "decimal_price": str(decimal_price),
        "source_published_at": _utc(source_published_at, "SOURCE_PUBLISHED_AT").isoformat(),
        "retrieved_at": _utc(retrieved_at, "RETRIEVED_AT").isoformat(),
        "response_sha256": response_sha256,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def evaluate_quote_admission(*, quote: Any, crosswalk: FixtureCrosswalk | None,
                             rights: QuoteRights | None, fixture_id: int,
                             prediction_cutoff_at: datetime, kickoff_at: datetime,
                             evaluated_at: datetime) -> QuoteAdmission:
    """Require exact identity, valid rights, and both quote clocks before cutoff."""
    reasons: list[str] = []
    cutoff = _utc(prediction_cutoff_at, "PREDICTION_CUTOFF_AT")
    kickoff = _utc(kickoff_at, "KICKOFF_AT")
    evaluated = _utc(evaluated_at, "EVALUATED_AT")
    if cutoff >= kickoff:
        reasons.append("PREDICTION_CUTOFF_NOT_BEFORE_KICKOFF")

    provider = getattr(quote, "provider", None)
    source_id = "odds_api_v4" if provider == "the_odds_api" else None
    event_id = getattr(quote, "provider_event_id", None)
    published_raw = getattr(quote, "source_published_at", None)
    retrieved_raw = getattr(quote, "retrieved_at", None)
    response_hash = getattr(quote, "response_sha256", None)
    price = getattr(quote, "decimal_price", None)
    market = getattr(quote, "market_key", None)
    point = getattr(quote, "point", None)

    try:
        published = _utc(published_raw, "SOURCE_PUBLISHED_AT")
        retrieved = _utc(retrieved_raw, "RETRIEVED_AT")
    except ValueError:
        published = retrieved = None
        reasons.append("QUOTE_TIMESTAMP_INVALID")

    if provider != "the_odds_api" or not event_id:
        reasons.append("QUOTE_PROVIDER_OR_EVENT_ID_INVALID")
    if market not in {"h2h", "totals", "btts"}:
        reasons.append("QUOTE_MARKET_UNSUPPORTED")
    if not isinstance(price, Decimal) or not price.is_finite() or price <= Decimal("1") or price >= Decimal("10000"):
        reasons.append("QUOTE_DECIMAL_PRICE_INVALID")
    if (market == "totals" and (not isinstance(point, Decimal) or not point.is_finite())):
        reasons.append("QUOTE_TOTALS_POINT_INVALID")
    if market != "totals" and point is not None:
        reasons.append("QUOTE_UNEXPECTED_LINE_POINT")
    if not isinstance(response_hash, str) or not _SHA256.fullmatch(response_hash):
        reasons.append("QUOTE_RESPONSE_HASH_INVALID")

    if published is not None and retrieved is not None:
        if published > retrieved:
            reasons.append("SOURCE_TIMESTAMP_AFTER_RETRIEVAL")
        if published > cutoff:
            reasons.append("SOURCE_TIMESTAMP_AFTER_PREDICTION_CUTOFF")
        if retrieved > cutoff:
            reasons.append("RETRIEVAL_AFTER_PREDICTION_CUTOFF")
        if published > kickoff or retrieved >= kickoff:
            reasons.append("QUOTE_NOT_PRE_KICKOFF")

    if crosswalk is None:
        reasons.append("FIXTURE_CROSSWALK_MISSING")
    else:
        if (crosswalk.provider != provider or crosswalk.source_id != source_id
                or crosswalk.provider_event_id != event_id
                or crosswalk.fixture_id != fixture_id
                or crosswalk.entity_type != "FIXTURE"
                or crosswalk.status != "RESOLVED"):
            reasons.append("FIXTURE_CROSSWALK_MISMATCH")
        try:
            valid_from = _utc(crosswalk.valid_from, "CROSSWALK_VALID_FROM")
            valid_until = (_utc(crosswalk.valid_until, "CROSSWALK_VALID_UNTIL")
                           if crosswalk.valid_until is not None else None)
            if retrieved is not None and (valid_from > retrieved or
                    (valid_until is not None and valid_until <= retrieved)):
                reasons.append("FIXTURE_CROSSWALK_NOT_VALID_AT_RETRIEVAL")
        except ValueError:
            reasons.append("FIXTURE_CROSSWALK_TIMESTAMP_INVALID")

    if rights is None:
        reasons.append("QUOTE_RIGHTS_EVIDENCE_MISSING")
    else:
        if (rights.provider != provider or rights.source_id != source_id
                or rights.status != "APPROVED"
                or not {"COLLECTION", "STORAGE"}.issubset(rights.permitted_uses)):
            reasons.append("QUOTE_RIGHTS_SCOPE_NOT_APPROVED")
        if not _SHA256.fullmatch(rights.evidence_sha256 or ""):
            reasons.append("QUOTE_RIGHTS_HASH_INVALID")
        try:
            effective = _utc(rights.effective_at, "RIGHTS_EFFECTIVE_AT")
            recorded = _utc(rights.recorded_at, "RIGHTS_RECORDED_AT")
            until = _utc(rights.valid_until, "RIGHTS_VALID_UNTIL") if rights.valid_until else None
            if effective > evaluated or recorded > evaluated or (until and until <= evaluated):
                reasons.append("QUOTE_RIGHTS_NOT_VALID_AT_EVALUATION")
        except ValueError:
            reasons.append("QUOTE_RIGHTS_TIMESTAMP_INVALID")

    key = None
    if not reasons and published is not None and retrieved is not None:
        key = quote_observation_key(
            provider=provider, source_id=source_id,
            sport_key=quote.sport_key, provider_event_id=event_id,
            bookmaker_key=quote.bookmaker_key, market_key=market,
            selection_key=quote.selection_key, line_point=point,
            decimal_price=price, source_published_at=published,
            retrieved_at=retrieved, response_sha256=response_hash,
        )
    return QuoteAdmission(not reasons, tuple(sorted(set(reasons))), key)
