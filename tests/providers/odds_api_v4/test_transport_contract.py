from datetime import datetime, timezone
import hashlib

from veltrix_v2.providers.odds_api_v4.transport_contract import (
    RawTransportResponse, TransportPolicy, execute_with_injected_transport,
    validate_transport_response,
)


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


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
        ("x-requests-last", "3"),
        ("x-requests-remaining", "987"),
        ("x-requests-used", "00123"),
    )


def test_missing_quota_headers_remain_missing_not_zero():
    result = validate_transport_response(RawTransportResponse(204, {}, b"", NOW))
    assert result.accepted
    assert result.envelope.raw_quota_headers == ()


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
        dispatch_allowed=True,
        request_url="https://api.the-odds-api.com/v4/sports",
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
        dispatch_allowed=True,
        request_url="https://api.the-odds-api.com/v4/sports",
        send=broken_send,
    )
    assert result.reason_code == "TRANSPORT_OUTCOME_UNCERTAIN"
    assert len(calls) == 1


def test_unauthorized_dispatch_never_calls_transport():
    calls = []
    result = execute_with_injected_transport(
        dispatch_allowed=False,
        request_url="https://api.the-odds-api.com/v4/sports",
        send=lambda url, policy: calls.append(url),
    )
    assert result.reason_code == "DISPATCH_NOT_AUTHORIZED"
    assert calls == []
