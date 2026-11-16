"""Fail-closed reconciliation of provider quota snapshots; no I/O."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class QuotaSnapshot:
    provider: str
    account_ref: str
    period_start: date
    period_end: date
    observed_at: datetime
    requests_used: int | None
    requests_remaining: int | None
    requests_last: int | None
    evidence_sha256: str


@dataclass(frozen=True)
class QuotaReconciliation:
    status: str
    reason_code: str
    actual_credits: int | None
    releasable_credits: int | None
    freeze_account: bool


def _counter(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def reconcile_quota_usage(
    before: QuotaSnapshot,
    after: QuotaSnapshot,
    *,
    reserved_credits: int,
) -> QuotaReconciliation:
    """Reconcile one request only when the complete quota delta is exact."""
    if not isinstance(before, QuotaSnapshot) or not isinstance(after, QuotaSnapshot):
        return QuotaReconciliation("UNKNOWN", "QUOTA_SNAPSHOT_TYPE_INVALID", None, None, True)
    if not _counter(reserved_credits):
        return QuotaReconciliation("UNKNOWN", "RESERVATION_AMOUNT_INVALID", None, None, True)
    if not all(isinstance(v, str) and v.strip() for v in (
        before.provider, before.account_ref, after.provider, after.account_ref,
    )):
        return QuotaReconciliation("UNKNOWN", "QUOTA_IDENTITY_INVALID", None, None, True)
    if (before.provider != after.provider or before.account_ref != after.account_ref
            or before.period_start != after.period_start or before.period_end != after.period_end):
        return QuotaReconciliation("UNKNOWN", "QUOTA_SNAPSHOT_IDENTITY_MISMATCH", None, None, True)
    if (not _aware(before.observed_at) or not _aware(after.observed_at)
            or after.observed_at <= before.observed_at):
        return QuotaReconciliation("UNKNOWN", "QUOTA_SNAPSHOT_TIME_INVALID", None, None, True)
    if not all(_counter(v) for v in (
        before.requests_used, before.requests_remaining, before.requests_last,
        after.requests_used, after.requests_remaining, after.requests_last,
    )):
        return QuotaReconciliation("UNKNOWN", "QUOTA_COUNTERS_INCOMPLETE", None, None, True)
    if (not _SHA256.fullmatch(before.evidence_sha256 or "")
            or not _SHA256.fullmatch(after.evidence_sha256 or "")):
        return QuotaReconciliation("UNKNOWN", "QUOTA_EVIDENCE_HASH_INVALID", None, None, True)
    if (after.requests_used < before.requests_used
            or after.requests_remaining > before.requests_remaining):
        return QuotaReconciliation("UNKNOWN", "QUOTA_COUNTERS_NON_MONOTONIC", None, None, True)

    used_delta = after.requests_used - before.requests_used
    remaining_delta = before.requests_remaining - after.requests_remaining
    actual = after.requests_last
    if used_delta != remaining_delta or actual != used_delta:
        return QuotaReconciliation("UNKNOWN", "QUOTA_RECONCILIATION_UNKNOWN", None, None, True)
    if actual > reserved_credits:
        return QuotaReconciliation("OVERRUN", "CREDIT_OVERRUN", actual, 0, True)
    return QuotaReconciliation(
        "RECONCILED", "QUOTA_RECONCILED", actual,
        reserved_credits - actual, False
    )
