"""Point-in-time bookmaker quote contract for the isolated VELTRIX 2.0 benchmark lane.

Odds are evaluation/benchmark evidence only. This module does not expose odds as
football-strength model features.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional


def _aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _decimal(value: Decimal | str | int | float, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class OddsSnapshot:
    """One immutable, timestamped quote for one fixture/market/selection/line."""

    snapshot_id: str
    fixture_id: str
    source_id: str
    bookmaker_id: str
    market: str
    selection: str
    decimal_odds: Decimal
    captured_at: datetime
    kickoff_at: datetime
    line: Optional[Decimal] = None
    provider_quote_at: Optional[datetime] = None
    provider_event_id: Optional[str] = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("snapshot_id", "fixture_id", "source_id", "bookmaker_id", "market", "selection"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")

        captured = _aware_utc(self.captured_at, "captured_at")
        kickoff = _aware_utc(self.kickoff_at, "kickoff_at")
        if captured >= kickoff:
            raise ValueError("odds snapshot must be captured strictly before kickoff")

        odds = _decimal(self.decimal_odds, "decimal_odds")
        if odds <= Decimal("1"):
            raise ValueError("decimal_odds must be greater than 1.0")

        line = None if self.line is None else _decimal(self.line, "line")
        provider_quote = None if self.provider_quote_at is None else _aware_utc(self.provider_quote_at, "provider_quote_at")
        if provider_quote is not None and provider_quote >= kickoff:
            raise ValueError("provider_quote_at must be strictly before kickoff")
        if provider_quote is not None and provider_quote > captured:
            raise ValueError("provider_quote_at cannot be after captured_at")
        provider_event_id = self.provider_event_id
        if provider_event_id is not None and (not isinstance(provider_event_id, str) or not provider_event_id.strip()):
            raise ValueError("provider_event_id must be a non-empty string when supplied")
        if self.schema_version != 1:
            raise ValueError("unsupported odds snapshot schema_version")

        object.__setattr__(self, "captured_at", captured)
        object.__setattr__(self, "kickoff_at", kickoff)
        object.__setattr__(self, "decimal_odds", odds)
        object.__setattr__(self, "line", line)
        object.__setattr__(self, "provider_quote_at", provider_quote)
        object.__setattr__(self, "provider_event_id", provider_event_id)
