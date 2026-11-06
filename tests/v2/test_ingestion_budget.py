from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.ingestion.budget import QuotaSnapshot, evaluate_quota_request


NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def snapshot(**overrides):
    values = dict(
        provider="primary-provider",
        quota_scope="daily",
        unit_name="request_units",
        snapshot_id="quota-snapshot-001",
        measured_at_utc=NOW - timedelta(minutes=2),
        period_ends_at_utc=NOW + timedelta(hours=12),
        limit_units=100,
        used_units=50,
        reserved_units=20,
    )
    values.update(overrides)
    return QuotaSnapshot(**values)


def test_request_fits_available_budget_without_consuming_reserve():
    decision = evaluate_quota_request(snapshot(), requested_units=30, now_utc=NOW)
    assert decision.allowed
    assert decision.available_units == 30
    assert decision.reason_code == "QUOTA_AVAILABLE"


def test_request_cannot_spend_protected_reserve():
    decision = evaluate_quota_request(snapshot(), requested_units=31, now_utc=NOW)
    assert not decision.allowed
    assert decision.reason_code == "QUOTA_RESERVE_PROTECTED"
    assert decision.available_units == 30


def test_missing_quota_snapshot_fails_closed():
    decision = evaluate_quota_request(None, requested_units=1, now_utc=NOW)
    assert not decision.allowed
    assert decision.reason_code == "QUOTA_SNAPSHOT_MISSING"


def test_stale_quota_snapshot_fails_closed():
    old = snapshot(measured_at_utc=NOW - timedelta(hours=25))
    decision = evaluate_quota_request(old, requested_units=1, now_utc=NOW)
    assert not decision.allowed
    assert decision.reason_code == "QUOTA_SNAPSHOT_STALE"


def test_expired_quota_period_fails_closed():
    expired = snapshot(period_ends_at_utc=NOW)
    decision = evaluate_quota_request(expired, requested_units=1, now_utc=NOW)
    assert not decision.allowed
    assert decision.reason_code == "QUOTA_PERIOD_EXPIRED"


def test_future_dated_snapshot_fails_closed():
    future = snapshot(measured_at_utc=NOW + timedelta(seconds=1))
    decision = evaluate_quota_request(future, requested_units=1, now_utc=NOW)
    assert not decision.allowed
    assert decision.reason_code == "QUOTA_SNAPSHOT_FROM_FUTURE"


def test_overdrawn_snapshot_fails_closed():
    overdrawn = snapshot(used_units=90, reserved_units=20)
    decision = evaluate_quota_request(overdrawn, requested_units=1, now_utc=NOW)
    assert not decision.allowed
    assert decision.reason_code == "QUOTA_SNAPSHOT_OVERDRAWN"


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_quota_request(snapshot(), requested_units=1, now_utc=datetime(2026, 11, 6, 12, 0))


def test_nonpositive_request_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        evaluate_quota_request(snapshot(), requested_units=0, now_utc=NOW)
