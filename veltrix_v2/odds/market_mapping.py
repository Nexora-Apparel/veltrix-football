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

    def __post_init__(self) -> None:
        required = (
            self.canonical_fixture_id, self.bookmaker_key, self.bookmaker_title,
            self.provider, self.source_id, self.provider_event_id,
            self.source_record_id, self.provider_market_key,
            self.mapping_evidence_ref,
        )
        if any(not value or not value.strip() for value in required):
            raise ValueError("normalized odds quote identity fields are required")
        if not self.decimal_odds.is_finite() or self.decimal_odds <= Decimal("1"):
            raise ValueError("normalized decimal odds must be finite and greater than 1.0")
        if self.line is not None and (not self.line.is_finite() or self.line <= 0):
            raise ValueError("normalized line must be positive and finite")
        if self.canonical_market is CanonicalMarket.TOTALS and self.line is None:
            raise ValueError("normalized totals quote requires a line")
        if self.canonical_market is not CanonicalMarket.TOTALS and self.line is not None:
            raise ValueError("only totals quotes may carry a line")
        for value, field in (
            (self.quote_updated_at_utc, "quote_updated_at_utc"),
            (self.fetched_at_utc, "fetched_at_utc"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")
        if self.quote_updated_at_utc > self.fetched_at_utc:
            raise ValueError("quote update cannot be later than fetch time")
        if len(self.raw_response_sha256) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.raw_response_sha256.lower()
        ):
            raise ValueError("raw_response_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class MarketMappingDecision:
    allowed: bool
    reason_code: str
    normalized_quote: NormalizedOddsQuote | None
