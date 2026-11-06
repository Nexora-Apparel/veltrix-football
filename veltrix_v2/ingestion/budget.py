"""Fail-closed provider quota budget decisions.

This module is deterministic and offline. It never calls a provider or mutates
quota counters; persistence and atomic reservation belong to an adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    provider: str
    quota_scope: str
    unit_name: str
    snapshot_id: str
    measured_at_utc: datetime
    period_ends_at_utc: datetime
    limit_units: int
    used_units: int
    reserved_units: int


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    allowed: bool
    reason_code: str
    provider: str
    quota_scope: str
    requested_units: int
    available_units: int
    snapshot_id: str | None


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def evaluate_quota_request(
    snapshot: QuotaSnapshot | None,
    *,
    requested_units: int,
    now_utc: datetime,
    max_snapshot_age: timedelta = timedelta(hours=24),
) -> QuotaDecision:
    """Authorize a request without spending the protected reserve.

    A missing, stale, malformed, expired or overdrawn quota snapshot fails
    closed. Callers must atomically reserve units in their quota repository
    after this preflight decision to prevent concurrent overspend.
    """
    if requested_units < 1:
        raise ValueError("requested_units must be positive")
    if max_snapshot_age < timedelta(0):
        raise ValueError("max_snapshot_age cannot be negative")
    now = _aware_utc(now_utc, "now_utc")

    if snapshot is None:
        return QuotaDecision(False, "QUOTA_SNAPSHOT_MISSING", "unknown", "unknown", requested_units, 0, None)

    measured = _aware_utc(snapshot.measured_at_utc, "measured_at_utc")
    period_end = _aware_utc(snapshot.period_ends_at_utc, "period_ends_at_utc")
    identity = (snapshot.provider, snapshot.quota_scope, snapshot.unit_name, snapshot.snapshot_id)
    if any(not value.strip() for value in identity):
        return QuotaDecision(False, "QUOTA_SNAPSHOT_INVALID", snapshot.provider or "unknown", snapshot.quota_scope or "unknown", requested_units, 0, snapshot.snapshot_id or None)
    if min(snapshot.limit_units, snapshot.used_units, snapshot.reserved_units) < 0:
        return QuotaDecision(False, "QUOTA_SNAPSHOT_INVALID", snapshot.provider, snapshot.quota_scope, requested_units, 0, snapshot.snapshot_id)
    if snapshot.used_units + snapshot.reserved_units > snapshot.limit_units:
        return QuotaDecision(False, "QUOTA_SNAPSHOT_OVERDRAWN", snapshot.provider, snapshot.quota_scope, requested_units, 0, snapshot.snapshot_id)
    if measured > now:
        return QuotaDecision(False, "QUOTA_SNAPSHOT_FROM_FUTURE", snapshot.provider, snapshot.quota_scope, requested_units, 0, snapshot.snapshot_id)
    if now - measured > max_snapshot_age:
        return QuotaDecision(False, "QUOTA_SNAPSHOT_STALE", snapshot.provider, snapshot.quota_scope, requested_units, 0, snapshot.snapshot_id)
    if now >= period_end:
        return QuotaDecision(False, "QUOTA_PERIOD_EXPIRED", snapshot.provider, snapshot.quota_scope, requested_units, 0, snapshot.snapshot_id)

    available = snapshot.limit_units - snapshot.used_units - snapshot.reserved_units
    if requested_units > available:
        return QuotaDecision(False, "QUOTA_RESERVE_PROTECTED", snapshot.provider, snapshot.quota_scope, requested_units, available, snapshot.snapshot_id)
    return QuotaDecision(True, "QUOTA_AVAILABLE", snapshot.provider, snapshot.quota_scope, requested_units, available, snapshot.snapshot_id)
