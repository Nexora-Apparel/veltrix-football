"""Fail-closed request-budget accounting for provider acquisition runs.

This module is deliberately transport- and database-independent. Callers must
supply an observed balance and an operator-approved ceiling for credit-limited
providers before making network requests.
"""
from __future__ import annotations

from dataclasses import dataclass


class BudgetError(ValueError):
    """Raised when a provider request cannot be safely budgeted."""


@dataclass(frozen=True)
class RequestBudgetPlan:
    provider: str
    max_calls: int
    cost_per_call: int
    approved_max_cost: int
    observed_remaining: int | None
    retry_reserve_calls: int = 0
    requires_observed_balance: bool = True

    @property
    def reserved_calls(self) -> int:
        return self.max_calls + self.retry_reserve_calls

    @property
    def reserved_cost(self) -> int:
        return self.reserved_calls * self.cost_per_call

    def validate(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise BudgetError("provider must be a non-empty string")
        for name, value in (
            ("max_calls", self.max_calls),
            ("cost_per_call", self.cost_per_call),
            ("approved_max_cost", self.approved_max_cost),
            ("retry_reserve_calls", self.retry_reserve_calls),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise BudgetError(f"{name} must be a non-negative integer")
        if self.max_calls < 1 or self.cost_per_call < 1:
            raise BudgetError("max_calls and cost_per_call must be positive")
        if self.requires_observed_balance:
            if (isinstance(self.observed_remaining, bool)
                    or not isinstance(self.observed_remaining, int)
                    or self.observed_remaining < 0):
                raise BudgetError("observed remaining balance is required for this provider")
        elif self.observed_remaining is not None and (
            isinstance(self.observed_remaining, bool)
            or not isinstance(self.observed_remaining, int)
            or self.observed_remaining < 0
        ):
            raise BudgetError("observed_remaining must be a non-negative integer or None")
        if self.reserved_cost > self.approved_max_cost:
            raise BudgetError("planned calls plus retry reserve exceed approved cost ceiling")
        if self.observed_remaining is not None and self.reserved_cost > self.observed_remaining:
            raise BudgetError("planned calls plus retry reserve exceed observed remaining balance")


@dataclass
class RequestBudgetLedger:
    plan: RequestBudgetPlan
    calls_made: int = 0
    cost_consumed: int = 0

    def __post_init__(self) -> None:
        self.plan.validate()

    def before_request(self) -> None:
        """Reserve one call immediately before each network attempt, including retries."""
        if self.calls_made >= self.plan.reserved_calls:
            raise BudgetError("request call budget exhausted")
        next_cost = self.cost_consumed + self.plan.cost_per_call
        if next_cost > self.plan.approved_max_cost:
            raise BudgetError("approved request cost ceiling would be exceeded")
        if self.plan.observed_remaining is not None and next_cost > self.plan.observed_remaining:
            raise BudgetError("observed provider balance would be exceeded")
        self.calls_made += 1
        self.cost_consumed = next_cost

    def report(self) -> dict:
        return {
            "provider": self.plan.provider,
            "planned_calls": self.plan.max_calls,
            "retry_reserve_calls": self.plan.retry_reserve_calls,
            "reserved_calls": self.plan.reserved_calls,
            "calls_made": self.calls_made,
            "cost_per_call": self.plan.cost_per_call,
            "approved_max_cost": self.plan.approved_max_cost,
            "observed_remaining_before_run": self.plan.observed_remaining,
            "cost_consumed": self.cost_consumed,
            "remaining_observed_budget": (
                None if self.plan.observed_remaining is None
                else self.plan.observed_remaining - self.cost_consumed
            ),
        }


def retry_allowed(http_status: int, retries_used: int, max_retries: int) -> bool:
    """Only bounded HTTP 429 retries are allowed; 401/402 and other errors stop."""
    for name, value in (("http_status", http_status), ("retries_used", retries_used),
                        ("max_retries", max_retries)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BudgetError(f"{name} must be a non-negative integer")
    return http_status == 429 and retries_used < max_retries
