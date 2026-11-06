"""Verified provider-market-key mappings and canonical quote selection contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class CanonicalMarket(StrEnum):
    ONE_X_TWO = "1X2"
    BTTS = "BTTS"
    TOTALS = "TOTALS"


class CanonicalSelection(StrEnum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    YES = "YES"
    NO = "NO"
    OVER = "OVER"
    UNDER = "UNDER"


@dataclass(frozen=True, slots=True)
class VerifiedMarketKeyMapping:
    provider: str
    source_id: str
    provider_market_key: str
    canonical_market: CanonicalMarket
    mapping_version: str
    evidence_ref: str
    valid_from_utc: datetime
    verified_at_utc: datetime
    valid_to_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class NormalizedOddsQuote:
    canonical_fixture_id: str
    canonical_market: CanonicalMarket
    selection: CanonicalSelection
    line: Decimal | None
    decimal_odds: Decimal
    bookmaker_key: str
    bookmaker_title: str
    provider: str
    source_id: str
    provider_event_id: str
    source_record_id: str
    provider_market_key: str
    quote_updated_at_utc: datetime
    fetched_at_utc: datetime
    raw_response_sha256: str
    mapping_evidence_ref: str


@dataclass(frozen=True, slots=True)
class MarketMappingDecision:
    allowed: bool
    reason_code: str
    normalized_quote: NormalizedOddsQuote | None
