from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib

from veltrix_v2.providers.odds_api_v4.dispatch_guard import DispatchContext
from veltrix_v2.providers.odds_api_v4.transport_contract import (
    RawTransportResponse, TransportPolicy, execute_with_injected_transport,
    validate_transport_response,
)


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
CONTEXT = DispatchContext(
    provider="the_odds_api",
    endpoint_url="https://api.the-odds-api.com/v4/sports",
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
    max_attempts=1,
    previous_attempt_reconciled=False,
    budget_valid_until=NOW + timedelta(minutes=5),
    now=NOW,
)


def test_raw_body_hash_and_allowlisted_headers_are_preserved_exactly():
    body = b'{"data":[]}'
    response = RawTransportResponse(
        200,
        {
            "X-Requests-Used": "00123",
            "x-requests-remaining": "987",
            "X-Requests-Last": "3",
            "Set-Cookie": "session=private",
            "Authorization": "Bearer private",
        },
        body,
        NOW,
    )
    result = validate_transport_response(response)
    assert result.accepted
    assert result.envelope.raw_body == body
    assert result.envelope.response_sha256 == hashlib.sha256(body).hexdigest()
    assert result.envelope.raw_quota_headers == (
        ("x-requests-used", "00123"),
        ("x-requests-remaining", "987"),
        ("x-requests-last", "3"),
    )
    assert result.envelope.quota_evidence.complete
    assert result.envelope.quota_evidence.requests_used == 123
    assert result.envelope.quota_evidence.requests_remaining == 987
    assert result.envelope.quota_evidence.requests_last == 3
    assert len(result.envelope.quota_evidence.evidence_sha256) == 64


def test_missing_quota_headers_remain_missing_not_zero():
    result = validate_transport_response(RawTransportResponse(204, {}, b"", NOW))
    assert result.accepted
    assert result.envelope.raw_quota_headers == ()
    assert result.envelope.quota_evidence.requests_used is None
    assert result.envelope.quota_evidence.requests_remaining is None
    assert result.envelope.quota_evidence.requests_last is None
    assert not result.envelope.quota_evidence.complete


def test_duplicate_quota_headers_are_rejected_case_insensitively():
    result = validate_transport_response(RawTransportResponse(
        200, {"X-Requests-Used": "1", "x-requests-used": "2"}, b"{}", NOW
    ))
    assert result.reason_code == "DUPLICATE_QUOTA_HEADER"


def test_invalid_and_oversized_response_envelopes_fail_closed():
    assert validate_transport_response(
        RawTransportResponse(True, {}, b"", NOW)
    ).reason_code == "HTTP_STATUS_INVALID"
    assert validate_transport_response(
        RawTransportResponse(200, {}, "not-bytes", NOW)
    ).reason_code == "RESPONSE_BODY_NOT_BYTES"
    assert validate_transport_response(
        RawTransportResponse(200, {}, b"12345", NOW), max_response_bytes=4
    ).reason_code == "RESPONSE_BODY_LIMIT_EXCEEDED"
    assert validate_transport_response(
        RawTransportResponse(200, {}, b"{}", datetime(2026, 11, 13))
    ).reason_code == "RESPONSE_RETRIEVAL_TIME_INVALID"


def test_injected_transport_receives_strict_policy_and_never_retries():
    calls = []
    def fake_send(url, policy):
        calls.append((url, policy))
        return RawTransportResponse(200, {}, b"ok", NOW)

    result = execute_with_injected_transport(
        context=CONTEXT,
        send=fake_send,
    )
    assert result.accepted
    assert len(calls) == 1
    assert calls[0][1] == TransportPolicy()
    assert calls[0][1].allow_redirects is False


def test_transport_exceptions_remain_uncertain_and_are_not_retried():
    calls = []
    def broken_send(url, policy):
        calls.append(url)
        raise TimeoutError("network timed out")

    result = execute_with_injected_transport(
        context=CONTEXT,
        send=broken_send,
    )
    assert result.reason_code == "TRANSPORT_OUTCOME_UNCERTAIN"
    assert len(calls) == 1


def test_unauthorized_dispatch_never_calls_transport():
    calls = []
    result = execute_with_injected_transport(
        context=replace(CONTEXT, operator_dispatch_enabled=False),
        send=lambda url, policy: calls.append(url),
    )
    assert result.reason_code == "OPERATOR_DISPATCH_DISABLED"
    assert calls == []

def test_malformed_quota_counter_is_retained_but_never_interpreted_as_zero():
    result = validate_transport_response(RawTransportResponse(
        200,
        {
            "x-requests-used": "unknown",
            "x-requests-remaining": "987",
            "x-requests-last": "3",
        },
        b"{}",
        NOW,
    ))
    assert result.accepted
    assert result.envelope.quota_evidence.requests_used is None
    assert "X_REQUESTS_USED_MALFORMED" in result.envelope.quota_evidence.reason_codes
