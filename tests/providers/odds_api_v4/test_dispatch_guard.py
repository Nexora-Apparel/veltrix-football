from dataclasses import replace
from datetime import datetime, timedelta, timezone

from veltrix_v2.providers.odds_api_v4.dispatch_guard import (
    DispatchContext, authorize_dispatch,
)


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
BASE = DispatchContext(
    provider="the_odds_api",
    endpoint_url="https://api.the-odds-api.com/v4/sports/soccer_epl/odds?regions=uk&markets=h2h",
    manifest_sha256="a" * 64,
    request_fingerprint="b" * 64,
    reservation_fingerprint="b" * 64,
    reservation_key="reservation-1",
    preflight_approved=True,
    terms_acceptance_verified=True,
    rights_approved=True,
    budget_evidence_fresh=True,
    reservation_committed=True,
    capture_state="CREDIT_RESERVED",
    operator_dispatch_enabled=True,
    emergency_stop=False,
    attempt_number=1,
    max_attempts=2,
    previous_attempt_reconciled=False,
    budget_valid_until=NOW + timedelta(minutes=5),
    now=NOW,
)


def test_complete_exactly_bound_request_passes_offline_guard():
    result = authorize_dispatch(BASE)
    assert result.allowed
    assert result.reason_code == "DISPATCH_AUTHORIZED"


def test_every_activation_gate_fails_closed():
    cases = (
        ({"preflight_approved": False}, "PREFLIGHT_NOT_APPROVED"),
        ({"terms_acceptance_verified": False}, "ACCOUNT_TERMS_EVIDENCE_MISSING"),
        ({"rights_approved": False}, "SOURCE_RIGHTS_NOT_APPROVED"),
        ({"budget_evidence_fresh": False}, "BUDGET_EVIDENCE_NOT_FRESH"),
        ({"reservation_committed": False}, "CREDIT_RESERVATION_NOT_COMMITTED"),
        ({"operator_dispatch_enabled": False}, "OPERATOR_DISPATCH_DISABLED"),
        ({"emergency_stop": True}, "EMERGENCY_STOP_ACTIVE"),
    )
    for changes, expected in cases:
        assert authorize_dispatch(replace(BASE, **changes)).reason_code == expected


def test_fingerprint_state_and_budget_expiry_are_bound():
    assert authorize_dispatch(
        replace(BASE, reservation_fingerprint="c" * 64)
    ).reason_code == "RESERVATION_FINGERPRINT_MISMATCH"
    assert authorize_dispatch(
        replace(BASE, capture_state="PREFLIGHT_APPROVED")
    ).reason_code == "CREDIT_RESERVATION_NOT_COMMITTED"
    assert authorize_dispatch(
        replace(BASE, budget_valid_until=NOW - timedelta(seconds=1))
    ).reason_code == "BUDGET_EVIDENCE_EXPIRED"


def test_endpoint_host_scheme_path_and_query_are_strict():
    for url in (
        "http://api.the-odds-api.com/v4/sports",
        "https://evil.example/v4/sports",
        "https://api.the-odds-api.com/v3/sports",
        "https://user:pass@api.the-odds-api.com/v4/sports",
        "https://api.the-odds-api.com/v4/sports?apiKey=secret",
        "https://api.the-odds-api.com/v4/sports?unknown=value",
        "https://api.the-odds-api.com/v4/sports#fragment",
    ):
        assert authorize_dispatch(replace(BASE, endpoint_url=url)).reason_code == "ENDPOINT_URL_NOT_ALLOWLISTED"


def test_retries_are_bounded_and_require_previous_attempt_reconciliation():
    assert authorize_dispatch(
        replace(BASE, attempt_number=3, max_attempts=3)
    ).reason_code == "ATTEMPT_LIMIT_INVALID"
    assert authorize_dispatch(
        replace(BASE, attempt_number=2, previous_attempt_reconciled=False)
    ).reason_code == "PREVIOUS_ATTEMPT_NOT_RECONCILED"
    assert authorize_dispatch(
        replace(BASE, attempt_number=2, previous_attempt_reconciled=True)
    ).allowed


def test_unknown_provider_and_invalid_hashes_are_rejected():
    assert authorize_dispatch(
        replace(BASE, provider="other")
    ).reason_code == "PROVIDER_NOT_ALLOWLISTED"
    assert authorize_dispatch(
        replace(BASE, manifest_sha256="bad")
    ).reason_code == "MANIFEST_HASH_INVALID"

def test_truthy_non_boolean_gate_values_and_duplicate_query_keys_are_rejected():
    assert authorize_dispatch(
        replace(BASE, operator_dispatch_enabled="true")
    ).reason_code == "DISPATCH_BOOLEAN_EVIDENCE_INVALID"
    assert authorize_dispatch(
        replace(BASE, endpoint_url=BASE.endpoint_url + "&regions=us")
    ).reason_code == "ENDPOINT_URL_NOT_ALLOWLISTED"

