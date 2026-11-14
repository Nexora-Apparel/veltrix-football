from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from veltrix_v2.providers.odds_api_v4.reconciliation import (
    QuotaSnapshot, reconcile_quota_usage,
)


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
BEFORE = QuotaSnapshot(
    "the_odds_api", "acct-1", date(2026, 11, 1), date(2026, 12, 1),
    NOW, 100, 900, 2, "a" * 64,
)


def after(*, used=103, remaining=897, last=3, at=NOW + timedelta(seconds=2)):
    return replace(BEFORE, observed_at=at, requests_used=used,
                   requests_remaining=remaining, requests_last=last,
                   evidence_sha256="b" * 64)


def test_exact_quota_delta_reconciles_and_releases_only_unused_hold():
    result = reconcile_quota_usage(BEFORE, after(), reserved_credits=5)
    assert (result.status, result.actual_credits, result.releasable_credits) == (
        "RECONCILED", 3, 2
    )
    assert not result.freeze_account


def test_exact_full_usage_reconciles_without_release():
    result = reconcile_quota_usage(
        BEFORE, after(used=105, remaining=895, last=5), reserved_credits=5
    )
    assert result.status == "RECONCILED"
    assert result.releasable_credits == 0


def test_overrun_is_explicit_and_freezes_account():
    result = reconcile_quota_usage(
        BEFORE, after(used=106, remaining=894, last=6), reserved_credits=5
    )
    assert result.status == "OVERRUN"
    assert result.actual_credits == 6
    assert result.freeze_account


def test_zero_usage_requires_exact_unchanged_counters_and_zero_last_cost():
    result = reconcile_quota_usage(
        BEFORE, after(used=100, remaining=900, last=0), reserved_credits=5
    )
    assert result.status == "RECONCILED"
    assert result.actual_credits == 0
    assert result.releasable_credits == 5


def test_missing_or_malformed_counter_remains_unknown():
    for changed in (
        {"requests_used": None},
        {"requests_remaining": -1},
        {"requests_last": True},
    ):
        result = reconcile_quota_usage(BEFORE, replace(after(), **changed), reserved_credits=5)
        assert result.status == "UNKNOWN"
        assert result.freeze_account


def test_external_quota_movement_is_not_apportioned():
    result = reconcile_quota_usage(
        BEFORE, after(used=105, remaining=895, last=3), reserved_credits=5
    )
    assert result.reason_code == "QUOTA_RECONCILIATION_UNKNOWN"
    assert result.releasable_credits is None


def test_identity_period_and_time_mismatch_fail_closed():
    assert reconcile_quota_usage(
        BEFORE, replace(after(), account_ref="other"), reserved_credits=5
    ).reason_code == "QUOTA_SNAPSHOT_IDENTITY_MISMATCH"
    assert reconcile_quota_usage(
        BEFORE, replace(after(), observed_at=NOW), reserved_credits=5
    ).reason_code == "QUOTA_SNAPSHOT_TIME_INVALID"


def test_evidence_hash_and_reserved_amount_are_validated():
    assert reconcile_quota_usage(
        BEFORE, replace(after(), evidence_sha256="bad"), reserved_credits=5
    ).reason_code == "QUOTA_EVIDENCE_HASH_INVALID"
    assert reconcile_quota_usage(
        BEFORE, after(), reserved_credits=True
    ).reason_code == "RESERVATION_AMOUNT_INVALID"
