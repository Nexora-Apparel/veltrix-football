from dataclasses import replace

import pytest

from veltrix_v2.providers.provider_access import (
    ExecutionMode,
    ProviderAccessPolicy,
    UseStatus,
    evaluate_provider_access,
)


def base_policy(**overrides):
    policy = ProviderAccessPolicy(
        provider="free_results_source",
        mode=ExecutionMode.LIVE,
        network_enabled=True,
        permitted_use=UseStatus.DOCUMENTED,
        daily_request_limit=60,
        daily_requests_used=10,
        max_requests_per_run=5,
    )
    return replace(policy, **overrides)


@pytest.mark.parametrize("mode", [ExecutionMode.OFFLINE, ExecutionMode.MOCK])
def test_offline_and_mock_execution_need_no_account_evidence(mode):
    decision = evaluate_provider_access(ProviderAccessPolicy(
        provider="local-fixture",
        mode=mode,
        network_enabled=False,
        permitted_use=UseStatus.UNKNOWN,
    ))
    assert decision.allowed
    assert decision.reason_code == "OFFLINE_EXECUTION_ALLOWED"


def test_free_live_provider_is_allowed_with_documented_use_and_request_headroom():
    decision = evaluate_provider_access(base_policy())
    assert decision.allowed
    assert decision.reason_code == "FREE_LIVE_ACCESS_ALLOWED"


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (UseStatus.UNKNOWN, "PROVIDER_USE_NOT_VERIFIED"),
        (UseStatus.PROHIBITED, "PROVIDER_USE_PROHIBITED"),
    ],
)
def test_live_provider_requires_nonprohibited_documented_use(status, reason):
    decision = evaluate_provider_access(base_policy(permitted_use=status))
    assert not decision.allowed
    assert decision.reason_code == reason


def test_paid_requests_are_never_authorized_by_free_first_policy():
    for policy in (
        base_policy(estimated_cost_minor=1),
        base_policy(spend_authorized=True),
    ):
        decision = evaluate_provider_access(policy)
        assert not decision.allowed
        assert decision.reason_code == "PAID_REQUESTS_DISABLED"


def test_free_tier_request_limit_is_enforced_before_dispatch():
    decision = evaluate_provider_access(base_policy(daily_requests_used=56))
    assert not decision.allowed
    assert decision.reason_code == "FREE_TIER_REQUEST_LIMIT_EXCEEDED"


def test_invalid_limits_and_usage_fail_closed():
    assert evaluate_provider_access(base_policy(max_requests_per_run=True)).reason_code == "RUN_REQUEST_LIMIT_INVALID"
    assert evaluate_provider_access(base_policy(daily_requests_used=-1)).reason_code == "DAILY_USAGE_INVALID"
    assert evaluate_provider_access(base_policy(daily_request_limit=0)).reason_code == "DAILY_REQUEST_LIMIT_INVALID"


def test_live_network_must_be_explicitly_enabled():
    decision = evaluate_provider_access(base_policy(network_enabled=False))
    assert not decision.allowed
    assert decision.reason_code == "LIVE_NETWORK_NOT_ENABLED"


def test_offline_mode_cannot_smuggle_network_or_cost():
    network = evaluate_provider_access(base_policy(
        mode=ExecutionMode.OFFLINE, network_enabled=True,
    ))
    cost = evaluate_provider_access(base_policy(
        mode=ExecutionMode.MOCK, network_enabled=False, estimated_cost_minor=1,
    ))
    assert network.reason_code == "NONLIVE_MODE_CANNOT_ENABLE_NETWORK"
    assert cost.reason_code == "NONLIVE_MODE_COST_MUST_BE_ZERO"


def test_invalid_policy_is_rejected():
    assert not evaluate_provider_access(None).allowed
