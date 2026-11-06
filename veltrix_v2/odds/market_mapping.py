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

    def __post_init__(self) -> None:
        required = (
            self.provider, self.source_id, self.provider_market_key,
            self.mapping_version, self.evidence_ref,
        )
        if any(not value or not value.strip() for value in required):
            raise ValueError("market mapping identity and evidence fields are required")
        timestamps = (
            (self.valid_from_utc, "valid_from_utc"),
            (self.verified_at_utc, "verified_at_utc"),
        )
        for value, field in timestamps:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")
        if self.valid_to_utc is not None:
            if self.valid_to_utc.tzinfo is None or self.valid_to_utc.utcoffset() is None:
                raise ValueError("valid_to_utc must be timezone-aware")
            if self.valid_to_utc <= self.valid_from_utc:
                raise ValueError("valid_to_utc must be after valid_from_utc")


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
