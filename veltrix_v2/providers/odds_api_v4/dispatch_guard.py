"""Final offline authorization gate for a future provider dispatcher."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from urllib.parse import parse_qsl, urlsplit


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_QUERY = frozenset({
    "regions", "markets", "oddsFormat", "dateFormat",
    "commenceTimeFrom", "commenceTimeTo",
})
_ALLOWED_PATHS = (
    re.compile(r"^/v4/sports$"),
    re.compile(r"^/v4/sports/[a-z0-9_]+/events$"),
    re.compile(r"^/v4/sports/[a-z0-9_]+/odds$"),
    re.compile(r"^/v4/sports/[a-z0-9_]+/events/[A-Za-z0-9_-]+/odds$"),
)


@dataclass(frozen=True)
class DispatchContext:
    provider: str
    endpoint_url: str
    manifest_sha256: str
    request_fingerprint: str
    reservation_fingerprint: str
    reservation_key: str
    preflight_approved: bool
    terms_acceptance_verified: bool
    rights_approved: bool
    budget_evidence_fresh: bool
    reservation_committed: bool
    capture_state: str
    operator_dispatch_enabled: bool
    emergency_stop: bool
    attempt_number: int
    max_attempts: int
    previous_attempt_reconciled: bool
    budget_valid_until: datetime
    now: datetime


@dataclass(frozen=True)
class DispatchDecision:
    allowed: bool
    reason_code: str


def _valid_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.hostname != "api.the-odds-api.com"
                or parsed.port not in (None, 443) or parsed.username is not None
                or parsed.password is not None or parsed.fragment):
            return False
        if not any(pattern.fullmatch(parsed.path) for pattern in _ALLOWED_PATHS):
            return False
        query = parse_qsl(parsed.query, keep_blank_values=True)
        keys = [key for key, _ in query]
        if len(keys) != len(set(keys)) or any(key not in _ALLOWED_QUERY or not item for key, item in query):
            return False
        return True
    except (TypeError, ValueError):
        return False


def authorize_dispatch(context: DispatchContext) -> DispatchDecision:
    """Return authorization only; never performs or schedules a provider request."""
    if not isinstance(context, DispatchContext):
        return DispatchDecision(False, "DISPATCH_CONTEXT_INVALID")
    boolean_fields = (
        context.preflight_approved, context.terms_acceptance_verified,
        context.rights_approved, context.budget_evidence_fresh,
        context.reservation_committed, context.operator_dispatch_enabled,
        context.emergency_stop, context.previous_attempt_reconciled,
    )
    if any(type(value) is not bool for value in boolean_fields):
        return DispatchDecision(False, "DISPATCH_BOOLEAN_EVIDENCE_INVALID")
    if not isinstance(context.provider, str) or context.provider != "the_odds_api":
        return DispatchDecision(False, "PROVIDER_NOT_ALLOWLISTED")
    if not _valid_url(context.endpoint_url):
        return DispatchDecision(False, "ENDPOINT_URL_NOT_ALLOWLISTED")
    if not _SHA256.fullmatch(context.manifest_sha256 or ""):
        return DispatchDecision(False, "MANIFEST_HASH_INVALID")
    if not _SHA256.fullmatch(context.request_fingerprint or ""):
        return DispatchDecision(False, "REQUEST_FINGERPRINT_INVALID")
    if context.request_fingerprint != context.reservation_fingerprint:
        return DispatchDecision(False, "RESERVATION_FINGERPRINT_MISMATCH")
    if not isinstance(context.reservation_key, str) or not context.reservation_key.strip():
        return DispatchDecision(False, "RESERVATION_IDENTITY_MISSING")
    if not context.preflight_approved:
        return DispatchDecision(False, "PREFLIGHT_NOT_APPROVED")
    if not context.terms_acceptance_verified:
        return DispatchDecision(False, "ACCOUNT_TERMS_EVIDENCE_MISSING")
    if not context.rights_approved:
        return DispatchDecision(False, "SOURCE_RIGHTS_NOT_APPROVED")
    if not context.budget_evidence_fresh:
        return DispatchDecision(False, "BUDGET_EVIDENCE_NOT_FRESH")
    if (not isinstance(context.now, datetime) or context.now.tzinfo is None
            or context.now.utcoffset() is None
            or not isinstance(context.budget_valid_until, datetime)
            or context.budget_valid_until.tzinfo is None
            or context.budget_valid_until.utcoffset() is None):
        return DispatchDecision(False, "DISPATCH_TIME_INVALID")
    if context.now > context.budget_valid_until:
        return DispatchDecision(False, "BUDGET_EVIDENCE_EXPIRED")
    if not context.reservation_committed or context.capture_state != "CREDIT_RESERVED":
        return DispatchDecision(False, "CREDIT_RESERVATION_NOT_COMMITTED")
    if not context.operator_dispatch_enabled:
        return DispatchDecision(False, "OPERATOR_DISPATCH_DISABLED")
    if context.emergency_stop:
        return DispatchDecision(False, "EMERGENCY_STOP_ACTIVE")
    if (not isinstance(context.max_attempts, int) or isinstance(context.max_attempts, bool)
            or context.max_attempts < 1 or context.max_attempts > 2
            or not isinstance(context.attempt_number, int)
            or isinstance(context.attempt_number, bool)
            or context.attempt_number < 1 or context.attempt_number > context.max_attempts):
        return DispatchDecision(False, "ATTEMPT_LIMIT_INVALID")
    if context.attempt_number > 1 and not context.previous_attempt_reconciled:
        return DispatchDecision(False, "PREVIOUS_ATTEMPT_NOT_RECONCILED")
    return DispatchDecision(True, "DISPATCH_AUTHORIZED")
