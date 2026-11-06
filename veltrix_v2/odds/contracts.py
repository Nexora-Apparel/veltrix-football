"""Provider-native odds quote contracts before canonical market mapping."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProviderOddsQuote:
    provider: str
    source_id: str
    provider_event_id: str
    provider_competition_id: str
    source_record_id: str
    home_team_name: str
    away_team_name: str
    bookmaker_key: str
    bookmaker_title: str
    provider_market_key: str
    outcome_name: str
    decimal_odds: Decimal
    point: Decimal | None
    quote_updated_at_utc: datetime
    fetched_at_utc: datetime
    raw_response_sha256: str

    def __post_init__(self) -> None:
        required = (
            self.provider, self.source_id, self.provider_event_id,
            self.provider_competition_id, self.source_record_id,
            self.home_team_name, self.away_team_name,
            self.bookmaker_key, self.bookmaker_title,
            self.provider_market_key, self.outcome_name,
        )
        if any(not value or not value.strip() for value in required):
            raise ValueError("provider odds quote identity fields are required")
        if not self.decimal_odds.is_finite() or self.decimal_odds <= Decimal("1"):
            raise ValueError("decimal odds must be finite and greater than 1.0")
        if self.point is not None and not self.point.is_finite():
            raise ValueError("odds point must be finite")
        for value, field in (
            (self.quote_updated_at_utc, "quote_updated_at_utc"),
            (self.fetched_at_utc, "fetched_at_utc"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")
        if self.quote_updated_at_utc > self.fetched_at_utc:
            raise ValueError("quote timestamp cannot be later than fetch timestamp")
        if len(self.raw_response_sha256) != 64:
            raise ValueError("raw_response_sha256 must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class RejectedOddsQuote:
    provider_event_id: str
    bookmaker_key: str | None
    market_key: str | None
    outcome_name: str | None
    reason_code: str


@dataclass(frozen=True, slots=True)
class OddsNormalizationResult:
    quotes: tuple[ProviderOddsQuote, ...]
    rejected: tuple[RejectedOddsQuote, ...]
    raw_response_sha256: str
