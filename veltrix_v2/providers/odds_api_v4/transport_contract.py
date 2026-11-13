"""Mock-only transport boundary and exact raw response envelope validation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Callable, Mapping

from veltrix_v2.providers.odds_api_v4.quota_headers import ParsedQuotaHeaders, parse_quota_headers
from veltrix_v2.providers.odds_api_v4.dispatch_guard import (
    DispatchContext, authorize_dispatch,
)


QUOTA_HEADERS = frozenset({
    "x-requests-used", "x-requests-remaining", "x-requests-last",
})


@dataclass(frozen=True)
class TransportPolicy:
    method: str = "GET"
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    max_response_bytes: int = 2_000_000
    allow_redirects: bool = False


@dataclass(frozen=True)
class RawTransportResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    retrieved_at: datetime


@dataclass(frozen=True)
class ResponseEnvelope:
    status_code: int
    raw_body: bytes
    response_sha256: str
    retrieved_at: datetime
    raw_quota_headers: tuple[tuple[str, str], ...]
    quota_evidence: ParsedQuotaHeaders


@dataclass(frozen=True)
class EnvelopeDecision:
    accepted: bool
    reason_code: str
    envelope: ResponseEnvelope | None


def validate_transport_response(
    response: RawTransportResponse,
    *,
    max_response_bytes: int = 2_000_000,
) -> EnvelopeDecision:
    if not isinstance(response, RawTransportResponse):
        return EnvelopeDecision(False, "TRANSPORT_RESPONSE_TYPE_INVALID", None)
    if (not isinstance(response.status_code, int) or isinstance(response.status_code, bool)
            or response.status_code < 100 or response.status_code > 599):
        return EnvelopeDecision(False, "HTTP_STATUS_INVALID", None)
    if not isinstance(response.body, bytes):
        return EnvelopeDecision(False, "RESPONSE_BODY_NOT_BYTES", None)
    if (not isinstance(max_response_bytes, int) or isinstance(max_response_bytes, bool)
            or max_response_bytes < 1 or len(response.body) > max_response_bytes):
        return EnvelopeDecision(False, "RESPONSE_BODY_LIMIT_EXCEEDED", None)
    if (not isinstance(response.retrieved_at, datetime)
            or response.retrieved_at.tzinfo is None
            or response.retrieved_at.utcoffset() is None):
        return EnvelopeDecision(False, "RESPONSE_RETRIEVAL_TIME_INVALID", None)
    if not isinstance(response.headers, Mapping):
        return EnvelopeDecision(False, "RESPONSE_HEADERS_INVALID", None)

    header_pairs = []
    for name, value in response.headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            return EnvelopeDecision(False, "RESPONSE_HEADER_TYPE_INVALID", None)
        header_pairs.append((name, value))

    quota_evidence = parse_quota_headers(header_pairs)
    if any(code.endswith("_DUPLICATE") for code in quota_evidence.reason_codes):
        return EnvelopeDecision(False, "DUPLICATE_QUOTA_HEADER", None)

    envelope = ResponseEnvelope(
        status_code=response.status_code,
        raw_body=response.body,
        response_sha256=hashlib.sha256(response.body).hexdigest(),
        retrieved_at=response.retrieved_at,
        raw_quota_headers=quota_evidence.raw_headers,
        quota_evidence=quota_evidence,
    )
    return EnvelopeDecision(True, "RAW_RESPONSE_ENVELOPE_ACCEPTED", envelope)


def execute_with_injected_transport(
    *,
    context: DispatchContext,
    send: Callable[[str, TransportPolicy], RawTransportResponse],
) -> EnvelopeDecision:
    """Invoke one injected transport only after the full dispatch guard passes."""
    if not isinstance(context, DispatchContext):
        return EnvelopeDecision(False, "DISPATCH_CONTEXT_INVALID", None)
    authorization = authorize_dispatch(context)
    if not authorization.allowed:
        return EnvelopeDecision(False, authorization.reason_code, None)
    if not callable(send):
        return EnvelopeDecision(False, "TRANSPORT_NOT_INJECTED", None)
    policy = TransportPolicy()
    try:
        response = send(context.endpoint_url, policy)
    except Exception:
        return EnvelopeDecision(False, "TRANSPORT_OUTCOME_UNCERTAIN", None)
    return validate_transport_response(response, max_response_bytes=policy.max_response_bytes)
