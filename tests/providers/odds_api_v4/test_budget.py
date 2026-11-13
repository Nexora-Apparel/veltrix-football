import pytest

from veltrix_v2.providers.odds_api_v4.budget import (
    CreditBudget, PlannedRequest, plan_request, reconcile_quota_headers,
)


def budget(**changes):
    values = dict(monthly_allowance=100, provider_remaining=50,
                  monthly_hard_cap=80, per_run_hard_cap=20,
                  month_committed=10, run_committed=2)
    values.update(changes)
    return CreditBudget(**values)


def test_bulk_estimate_and_exact_run_cap_boundary():
    req = PlannedRequest("bulk_odds", regions=2, markets=("h2h", "totals"), sport_key="soccer")
    result = plan_request(req, budget(run_committed=16))
    assert result.allowed and result.estimated_credits == 4
    assert result.remaining_run_credits == 0


def test_one_credit_over_run_cap_rejected():
    req = PlannedRequest("bulk_odds", regions=1, markets=("h2h",), sport_key="soccer")
    result = plan_request(req, budget(run_committed=20))
    assert not result.allowed
    assert result.reason_code == "PER_RUN_CAP_EXCEEDED"


def test_event_odds_uses_conservative_requested_market_bound():
    req = PlannedRequest("event_odds", regions=2, markets=("btts", "h2h"), sport_key="soccer")
    assert plan_request(req, budget()).estimated_credits == 4


def test_discovery_is_zero_credit_but_requires_valid_budget():
    req = PlannedRequest("events_discovery")
    assert plan_request(req, budget()).estimated_credits == 0
    assert not plan_request(req, budget(monthly_allowance=-1)).allowed


def test_provider_remaining_and_monthly_cap_are_independently_enforced():
    req = PlannedRequest("bulk_odds", markets=("h2h", "totals"), sport_key="soccer")
    assert plan_request(req, budget(provider_remaining=1)).reason_code == "PROVIDER_ALLOWANCE_EXCEEDED"
    assert plan_request(req, budget(month_committed=79)).reason_code == "MONTHLY_CAP_EXCEEDED"


def test_unknown_or_invalid_quota_headers_stay_unknown():
    evidence = reconcile_quota_headers({"X-Requests-Used": "4", "x-requests-remaining": "unknown"})
    assert evidence.requests_used == 4
    assert evidence.requests_remaining is None
    assert not evidence.valid


def test_complete_quota_headers_are_case_insensitive():
    evidence = reconcile_quota_headers({"X-Requests-Used": "4",
        "X-Requests-Remaining": "90", "X-Requests-Last": "2"})
    assert evidence.valid
    assert (evidence.requests_used, evidence.requests_remaining, evidence.requests_last) == (4, 90, 2)


def test_budget_inputs_reject_booleans_and_no_mutation():
    req = PlannedRequest("bulk_odds", markets=("h2h",), sport_key="soccer")
    original = budget()
    result = plan_request(req, CreditBudget(**{**original.__dict__, "run_committed": True}))
    assert not result.allowed
    assert result.reason_code == "BUDGET_INPUT_INVALID"
    assert original.run_committed == 2
