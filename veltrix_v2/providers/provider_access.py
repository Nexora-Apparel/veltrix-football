"""Provider-neutral execution policy for free-first football data capture.

Offline and deterministic mock runs do not require provider-account evidence.
Live requests are allowed only for sources whose permitted use is documented.
Paid requests are always denied by this free-first policy.
This module performs no network, credential, database, or scheduling I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionMode(str, Enum):
    OFFLINE = "offline"
    MOCK = "mock"
    LIVE = "live"


class UseStatus(str, Enum):
    DOCUMENTED = "documented"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"


@dataclass(frozen=True)
class ProviderAccessPolicy:
    provider: str
    mode: ExecutionMode
    network_enabled: bool
    permitted_use: UseStatus
    estimated_cost_minor: int = 0
    spend_authorized: bool = False
    credential_ref: str | None = None
    daily_request_limit: int | None = None
    daily_requests_used: int = 0
    max_requests_per_run: int = 1


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason_code: str


def evaluate_provider_access(policy: ProviderAccessPolicy) -> AccessDecision:
    """Fail closed for live access while keeping offline engineering friction-free."""
    if not isinstance(policy, ProviderAccessPolicy):
        return AccessDecision(False, "POLICY_TYPE_INVALID")
    if not isinstance(policy.provider, str) or not policy.provider.strip():
        return AccessDecision(False, "PROVIDER_ID_REQUIRED")
    if not isinstance(policy.mode, ExecutionMode):
        return AccessDecision(False, "EXECUTION_MODE_INVALID")
    if type(policy.network_enabled) is not bool or type(policy.spend_authorized) is not bool:
        return AccessDecision(False, "BOOLEAN_POLICY_INVALID")
    if not isinstance(policy.permitted_use, UseStatus):
        return AccessDecision(False, "PERMITTED_USE_STATUS_INVALID")

    if policy.mode in (ExecutionMode.OFFLINE, ExecutionMode.MOCK):
        if policy.network_enabled:
            return AccessDecision(False, "NONLIVE_MODE_CANNOT_ENABLE_NETWORK")
        if policy.estimated_cost_minor != 0:
            return AccessDecision(False, "NONLIVE_MODE_COST_MUST_BE_ZERO")
        return AccessDecision(True, "OFFLINE_EXECUTION_ALLOWED")

    if not policy.network_enabled:
        return AccessDecision(False, "LIVE_NETWORK_NOT_ENABLED")
    if policy.permitted_use is UseStatus.PROHIBITED:
        return AccessDecision(False, "PROVIDER_USE_PROHIBITED")
    if policy.permitted_use is UseStatus.UNKNOWN:
        return AccessDecision(False, "PROVIDER_USE_NOT_VERIFIED")
    if policy.estimated_cost_minor != 0 or policy.spend_authorized:
        return AccessDecision(False, "PAID_REQUESTS_DISABLED")
    if (not isinstance(policy.max_requests_per_run, int)
            or isinstance(policy.max_requests_per_run, bool)
            or policy.max_requests_per_run < 1):
        return AccessDecision(False, "RUN_REQUEST_LIMIT_INVALID")
    if (not isinstance(policy.daily_requests_used, int)
            or isinstance(policy.daily_requests_used, bool)
            or policy.daily_requests_used < 0):
        return AccessDecision(False, "DAILY_USAGE_INVALID")
    if policy.daily_request_limit is not None:
        if (not isinstance(policy.daily_request_limit, int)
                or isinstance(policy.daily_request_limit, bool)
                or policy.daily_request_limit < 1):
            return AccessDecision(False, "DAILY_REQUEST_LIMIT_INVALID")
        if policy.daily_requests_used + policy.max_requests_per_run > policy.daily_request_limit:
            return AccessDecision(False, "FREE_TIER_REQUEST_LIMIT_EXCEEDED")
    if policy.credential_ref is not None and (
        not isinstance(policy.credential_ref, str) or not policy.credential_ref.strip()
    ):
        return AccessDecision(False, "CREDENTIAL_REFERENCE_INVALID")
    return AccessDecision(True, "FREE_LIVE_ACCESS_ALLOWED")
