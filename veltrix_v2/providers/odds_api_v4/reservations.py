"""Pure validation for durable credit reservations; no database or provider I/O."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReservationBudget:
    provider: str
    account_ref: str
    period_start: date
    period_end: date
    monthly_allowance: int | None
    provider_remaining: int | None
    monthly_hard_cap: int | None
    per_run_hard_cap: int | None
    request_count_cap: int | None
    observed_at: datetime | None
    evidence_sha256: str | None


@dataclass(frozen=True)
class ReservationRequest:
    reservation_key: str
    provider: str
    account_ref: str
    period_start: date
    period_end: date
    run_key: str
    manifest_id: int
    request_key: str
    attempt_number: int
    request_fingerprint: str
    estimated_credits: int
    requested_at: datetime


@dataclass(frozen=True)
class ReservationDecision:
    allowed: bool
    reason_code: str


def _nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def validate_reservation(
    request: ReservationRequest,
    budget: ReservationBudget,
    *,
    now: datetime,
) -> ReservationDecision:
    """Validate immutable request/budget identity before calling the DB function.

    This is deliberately not a reservation. Only the PostgreSQL transaction can
    atomically reserve shared capacity.
    """
    if not isinstance(request, ReservationRequest) or not isinstance(budget, ReservationBudget):
        return ReservationDecision(False, "RESERVATION_INPUT_TYPE_INVALID")
    if not _aware(now) or not _aware(request.requested_at):
        return ReservationDecision(False, "RESERVATION_TIME_MUST_BE_AWARE")
    if not all(isinstance(v, str) and v.strip() for v in (
        request.reservation_key, request.provider, request.account_ref,
        request.run_key, request.request_key, budget.provider, budget.account_ref,
    )):
        return ReservationDecision(False, "RESERVATION_IDENTITY_INVALID")
    if (request.provider != budget.provider or request.account_ref != budget.account_ref
            or request.period_start != budget.period_start or request.period_end != budget.period_end):
        return ReservationDecision(False, "BUDGET_IDENTITY_MISMATCH")
    if (not isinstance(request.manifest_id, int) or isinstance(request.manifest_id, bool)
            or request.manifest_id < 1 or not isinstance(request.attempt_number, int)
            or isinstance(request.attempt_number, bool) or request.attempt_number < 1):
        return ReservationDecision(False, "REQUEST_ATTEMPT_ID_INVALID")
    if not _SHA256.fullmatch(request.request_fingerprint or ""):
        return ReservationDecision(False, "REQUEST_FINGERPRINT_INVALID")
    if not _nonnegative_integer(request.estimated_credits) or request.estimated_credits < 0:
        return ReservationDecision(False, "ESTIMATED_CREDITS_INVALID")
    limits = (
        budget.monthly_allowance, budget.provider_remaining,
        budget.monthly_hard_cap, budget.per_run_hard_cap,
        budget.request_count_cap,
    )
    if any(not _nonnegative_integer(v) for v in limits):
        return ReservationDecision(False, "BUDGET_EVIDENCE_INCOMPLETE")
    if any(v == 0 for v in (budget.monthly_allowance, budget.monthly_hard_cap,
                            budget.per_run_hard_cap, budget.request_count_cap)):
        return ReservationDecision(False, "BUDGET_LIMIT_NOT_POSITIVE")
    if not _aware(budget.observed_at) or not _SHA256.fullmatch(budget.evidence_sha256 or ""):
        return ReservationDecision(False, "BUDGET_EVIDENCE_INVALID")
    if budget.period_end <= budget.period_start or not (
        budget.period_start <= request.requested_at.date() < budget.period_end
    ):
        return ReservationDecision(False, "BILLING_PERIOD_MISMATCH")
    if budget.observed_at > now or budget.observed_at > request.requested_at:
        return ReservationDecision(False, "BUDGET_EVIDENCE_FROM_FUTURE")
    if request.estimated_credits > min(
        budget.monthly_allowance, budget.provider_remaining,
        budget.monthly_hard_cap, budget.per_run_hard_cap,
    ):
        return ReservationDecision(False, "SINGLE_RESERVATION_EXCEEDS_LIMIT")
    return ReservationDecision(True, "VALIDATION_ACCEPTED_NOT_RESERVED")
