#!/usr/bin/env python3
"""Credit-preflight wrapper for the manual StrikerAPI 17-competition probe.

No provider request is made until both the observed remaining balance and an
operator-approved credit ceiling are present and the complete maximum scan
fits inside both values.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.provider_request_budget import (
    BudgetError,
    RequestBudgetLedger,
    RequestBudgetPlan,
)
from scripts.verify_strikerapi import ProbeError, call_api
from scripts.verify_strikerapi_17_competitions import MAX_CALLS, qualify

CREDITS_PER_CALL = 2


def build_ledger(remaining_credits: int | None, approved_max_credits: int | None) -> RequestBudgetLedger:
    """Validate all spend limits before a provider transport can be called."""
    if approved_max_credits is None:
        raise BudgetError("operator-approved maximum credits are required")
    plan = RequestBudgetPlan(
        provider="StrikerAPI",
        max_calls=MAX_CALLS,
        cost_per_call=CREDITS_PER_CALL,
        approved_max_cost=approved_max_credits,
        observed_remaining=remaining_credits,
        retry_reserve_calls=0,
        requires_observed_balance=True,
    )
    return RequestBudgetLedger(plan)


def run_budgeted_qualification(
    api_key: str,
    remaining_credits: int | None,
    approved_max_credits: int | None,
    now: datetime,
    transport: Callable = call_api,
    pause_seconds: float = 7.0,
    sleep: Callable = time.sleep,
) -> dict:
    """Run qualification through a metered transport; useful for zero-network tests."""
    ledger = build_ledger(remaining_credits, approved_max_credits)

    def metered_transport(*args, **kwargs):
        ledger.before_request()
        return transport(*args, **kwargs)

    report = qualify(
        api_key,
        now,
        call=metered_transport,
        pause_seconds=pause_seconds,
        sleep=sleep,
    )
    report["request_budget"].update(ledger.report())
    report["request_budget"]["maximum_calls"] = MAX_CALLS
    report["request_budget"]["maximum_credits"] = MAX_CALLS * CREDITS_PER_CALL
    report["request_budget"]["actual_calls"] = ledger.calls_made
    report["request_budget"]["actual_documented_credits"] = ledger.cost_consumed
    report["request_budget"]["preflight_passed"] = True
    return report


def _read_nonnegative_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise BudgetError(f"{name} must be a non-negative integer") from None
    if value < 0:
        raise BudgetError(f"{name} must be a non-negative integer")
    return value


def main() -> int:
    key = os.getenv("STRIKERAPI_API_KEY", "").strip()
    if not key:
        print("STRIKERAPI_17_LEAGUE_RESULT: BLOCKED_MISSING_SECRET")
        return 2

    try:
        remaining = _read_nonnegative_int("STRIKERAPI_REMAINING_CREDITS")
        approved = _read_nonnegative_int("STRIKERAPI_APPROVED_MAX_CREDITS")
        report = run_budgeted_qualification(
            key, remaining, approved, datetime.now(timezone.utc)
        )
    except BudgetError as exc:
        print(f"STRIKERAPI_17_LEAGUE_RESULT: BLOCKED_BUDGET_PREFLIGHT ({str(exc)[:180]})")
        print("PROVIDER_REQUESTS: 0; DATABASE_WRITES: 0; IMPORTS: 0")
        return 4
    except ProbeError as exc:
        print(f"STRIKERAPI_17_LEAGUE_FAILED: {str(exc)[:160]}")
        print("DATABASE_WRITES: 0; IMPORTS: 0; CHECKPOINTS: 0; CANONICAL_MERGES: 0")
        return 1

    output = Path("strikerapi_17_competition_coverage.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"STRIKERAPI_17_CALLS: {report['request_budget']['actual_calls']}; "
          f"credits={report['request_budget']['actual_documented_credits']}; "
          f"approved_max={report['request_budget']['approved_max_cost']}; "
          f"observed_remaining_before_run={report['request_budget']['observed_remaining_before_run']}")
    print(f"STRIKERAPI_17_ACCEPTANCE: {'PASS' if report['acceptance_pass'] else 'FAIL_REVIEW_REQUIRED'}")
    print(f"STRIKERAPI_17_REPORT: {output.name}")
    print("DATABASE_WRITES: 0; IMPORTS: 0; CHECKPOINTS: 0; CANONICAL_MERGES: 0")
    return 0 if report["acceptance_pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
