"""Deterministic preflight credit budgeting; no provider or runtime access."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class CreditBudget:
    # Optional monthly fields are advisory only; personal-use probes do not
    # require billing-period or allowance documentation.
    monthly_allowance: int | None
    provider_remaining: int | None
    monthly_hard_cap: int | None
    per_run_hard_cap: int
    month_committed: int = 0
    run_committed: int = 0


@dataclass(frozen=True)
class PlannedRequest:
    endpoint_class: str
    regions: int = 1
    markets: tuple[str, ...] = ()
    sport_key: str | None = None


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    estimated_credits: int | None
    remaining_run_credits: int | None
    remaining_monthly_credits: int | None
    reason_code: str


@dataclass(frozen=True)
class QuotaEvidence:
    requests_used: int | None
    requests_remaining: int | None
    requests_last: int | None
    valid: bool


def _valid_nonnegative(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def plan_request(request: PlannedRequest, budget: CreditBudget) -> BudgetDecision:
    """Fail-closed estimate. Call before every individual network attempt."""
    if not isinstance(request, PlannedRequest) or not isinstance(budget, CreditBudget):
        return BudgetDecision(False, None, None, None, "REQUEST_OR_BUDGET_TYPE_INVALID")
    if not isinstance(request.endpoint_class, str) or not request.endpoint_class:
        return BudgetDecision(False, None, None, None, "REQUEST_SHAPE_INVALID")
    required = (budget.per_run_hard_cap, budget.run_committed)
    optional = (budget.monthly_allowance, budget.monthly_hard_cap, budget.month_committed)
    if (any(not _valid_nonnegative(v) for v in required)
            or any(v is not None and not _valid_nonnegative(v) for v in optional)):
        return BudgetDecision(False, None, None, None, "BUDGET_INPUT_INVALID")
    if budget.per_run_hard_cap == 0:
        return BudgetDecision(False, None, None, None, "BUDGET_LIMIT_MUST_BE_POSITIVE")
    if budget.provider_remaining is not None and not _valid_nonnegative(budget.provider_remaining):
        return BudgetDecision(False, None, None, None, "PROVIDER_REMAINING_INVALID")
    if budget.run_committed > budget.per_run_hard_cap:
        return BudgetDecision(False, None, None, None, "BUDGET_STATE_INCONSISTENT")
    monthly_limits = [v for v in (budget.monthly_allowance, budget.monthly_hard_cap) if v is not None]
    remaining_month = min(monthly_limits) - (budget.month_committed or 0) if monthly_limits else None
    if remaining_month is not None and remaining_month < 0:
        return BudgetDecision(False, None, None, remaining_month, "BUDGET_STATE_INCONSISTENT")
    if not isinstance(request.regions, int) or isinstance(request.regions, bool) or request.regions < 1:
        return BudgetDecision(False, None, None, None, "REQUEST_SHAPE_INVALID")
    if request.endpoint_class in {"sports_discovery", "events_discovery"}:
        estimate = 0
    elif request.endpoint_class in {"bulk_odds", "event_odds"}:
        if (not request.sport_key or not isinstance(request.markets, tuple) or not request.markets
                or any(not isinstance(m, str) or not m for m in request.markets)):
            return BudgetDecision(False, None, None, None, "REQUEST_SHAPE_INVALID")
        estimate = len(set(request.markets)) * request.regions
    else:
        return BudgetDecision(False, None, None, None, "ENDPOINT_CLASS_UNSUPPORTED")
    remaining_run = budget.per_run_hard_cap - budget.run_committed
    if estimate > 0 and budget.provider_remaining is None:
        return BudgetDecision(False, estimate, remaining_run, remaining_month,
                              "PROVIDER_QUOTA_UNKNOWN")
    limits = [remaining_run]
    if budget.provider_remaining is not None:
        limits.append(budget.provider_remaining)
    if remaining_month is not None:
        limits.append(remaining_month)
    if estimate > min(limits):
        reason = ("PROVIDER_ALLOWANCE_EXCEEDED" if budget.provider_remaining is not None
                  and estimate > budget.provider_remaining else
                  "PER_RUN_CAP_EXCEEDED" if estimate > remaining_run else
                  "MONTHLY_CAP_EXCEEDED")
        return BudgetDecision(False, estimate, remaining_run, remaining_month, reason)
    return BudgetDecision(True, estimate, remaining_run - estimate,
                          None if remaining_month is None else remaining_month - estimate,
                          "BUDGET_APPROVED")


def reconcile_quota_headers(headers: Mapping[str, str]) -> QuotaEvidence:
    """Read only the three documented quota headers; malformed stays unknown."""
    if not isinstance(headers, Mapping):
        return QuotaEvidence(None, None, None, False)
    normalized = {k.casefold(): v for k, v in headers.items() if isinstance(k, str)}
    def read(name: str) -> int | None:
        raw = normalized.get(name)
        if isinstance(raw, bool) or raw is None:
            return None
        try:
            text_value = str(raw).strip()
            if not text_value.isascii() or not text_value.isdecimal():
                return None
            value = int(text_value)
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None
    used = read("x-requests-used")
    remaining = read("x-requests-remaining")
    last = read("x-requests-last")
    valid = used is not None and remaining is not None and last is not None
    return QuotaEvidence(used, remaining, last, valid)
