from dataclasses import replace
from datetime import date, datetime, timezone

from veltrix_v2.providers.odds_api_v4.reservations import (
    ReservationBudget, ReservationRequest, validate_reservation,
)


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
BUDGET = ReservationBudget(
    provider="the_odds_api", account_ref="acct-test",
    period_start=date(2026, 11, 1), period_end=date(2026, 12, 1),
    monthly_allowance=1000, provider_remaining=800,
    monthly_hard_cap=700, per_run_hard_cap=100, request_count_cap=500,
    observed_at=NOW, valid_until=datetime(2026, 11, 13, 12, 15, tzinfo=timezone.utc),
    evidence_sha256="a" * 64,
)
REQUEST = ReservationRequest(
    reservation_key="res-001", provider="the_odds_api", account_ref="acct-test",
    period_start=date(2026, 11, 1), period_end=date(2026, 12, 1),
    run_key="run-001", manifest_id=1, request_key="request-001",
    attempt_number=1, request_fingerprint="b" * 64,
    estimated_credits=10, requested_at=NOW,
)


def test_valid_precheck_is_explicitly_not_a_reservation():
    result = validate_reservation(REQUEST, BUDGET, now=NOW)
    assert result.allowed
    assert result.reason_code == "VALIDATION_ACCEPTED_NOT_RESERVED"


def test_unknown_or_invalid_budget_values_fail_closed():
    for field in ("monthly_allowance", "provider_remaining", "monthly_hard_cap",
                  "per_run_hard_cap", "request_count_cap"):
        result = validate_reservation(REQUEST, replace(BUDGET, **{field: None}), now=NOW)
        assert not result.allowed
        assert result.reason_code == "BUDGET_EVIDENCE_INCOMPLETE"


def test_account_period_and_request_fingerprint_are_bound():
    assert validate_reservation(
        REQUEST, replace(BUDGET, account_ref="other"), now=NOW
    ).reason_code == "BUDGET_IDENTITY_MISMATCH"
    assert validate_reservation(
        replace(REQUEST, request_fingerprint="bad"), BUDGET, now=NOW
    ).reason_code == "REQUEST_FINGERPRINT_INVALID"


def test_single_request_must_fit_every_independent_limit():
    for field in ("monthly_allowance", "provider_remaining", "monthly_hard_cap", "per_run_hard_cap"):
        result = validate_reservation(
            REQUEST, replace(BUDGET, **{field: 5}), now=NOW
        )
        assert result.reason_code == "SINGLE_RESERVATION_EXCEEDS_LIMIT"


def test_zero_caps_and_stale_or_future_budget_evidence_fail():
    assert validate_reservation(
        REQUEST, replace(BUDGET, request_count_cap=0), now=NOW
    ).reason_code == "BUDGET_LIMIT_NOT_POSITIVE"
    assert validate_reservation(
        REQUEST, replace(BUDGET, observed_at=NOW.replace(year=2027)), now=NOW
    ).reason_code == "BUDGET_EVIDENCE_FROM_FUTURE"


def test_expired_budget_snapshot_fails_closed():
    expired = replace(BUDGET, observed_at=NOW.replace(minute=30, hour=11), valid_until=NOW.replace(hour=11, minute=59))
    result = validate_reservation(REQUEST, expired, now=NOW)
    assert result.reason_code == "BUDGET_EVIDENCE_STALE"


def test_naive_timestamps_and_wrong_billing_period_fail():
    assert validate_reservation(
        replace(REQUEST, requested_at=datetime(2026, 11, 13, 12)), BUDGET, now=NOW
    ).reason_code == "RESERVATION_TIME_MUST_BE_AWARE"
    assert validate_reservation(
        replace(REQUEST, requested_at=datetime(2026, 12, 1, tzinfo=timezone.utc)),
        BUDGET, now=NOW,
    ).reason_code == "BILLING_PERIOD_MISMATCH"
