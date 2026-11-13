from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from veltrix_v2.providers.odds_api_v4.activation_gate import (
    AccountTermsEvidence, ActivationScope, ProviderBudgetEvidence,
    RightsApprovalEvidence, evaluate_activation_gate,
)


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
TERMS = AccountTermsEvidence(
    "the_odds_api", "acct-1", "terms-v1", "evidence://terms",
    "a" * 64, NOW - timedelta(days=3), NOW - timedelta(days=2),
)
RIGHTS = RightsApprovalEvidence(
    "the_odds_api", "odds_api_v4", "acct-1", "approval-1", "APPROVED",
    "terms-v1", ("EPL", "Ligue 1"), ("h2h", "totals", "btts"),
    ("uk",), ("derived_features",), NOW - timedelta(days=2),
    NOW - timedelta(days=1), NOW + timedelta(days=20),
    "evidence://rights", "b" * 64,
)
BUDGET = ProviderBudgetEvidence(
    "the_odds_api", "acct-1", date(2026, 11, 1), date(2026, 12, 1),
    1000, 800, 900, 100, 50, NOW - timedelta(minutes=2),
    NOW + timedelta(minutes=10), "evidence://budget", "c" * 64,
)
SCOPE = ActivationScope(
    "the_odds_api", "odds_api_v4", "acct-1", "terms-v1",
    ("EPL",), ("h2h", "btts"), ("uk",), "derived_features",
    NOW - timedelta(minutes=1), NOW, 10, 100, 20, 50, 3,
)


def test_exact_account_terms_rights_scope_and_fresh_budget_are_required():
    result = evaluate_activation_gate(terms=TERMS, rights=RIGHTS, budget=BUDGET, scope=SCOPE)
    assert result.allowed
    assert result.reason_codes == ()
    assert result.monthly_credit_headroom == 800
    assert result.run_credit_headroom == 80
    assert result.provider_credit_headroom == 750
    assert result.request_count_headroom == 47


def test_account_terms_version_must_match_exactly():
    result = evaluate_activation_gate(
        terms=replace(TERMS, accepted_terms_version="other"),
        rights=RIGHTS, budget=BUDGET, scope=SCOPE,
    )
    assert "ACCOUNT_TERMS_VERSION_MISMATCH" in result.reason_codes
    assert not result.allowed


def test_rights_must_be_approved_and_recorded_before_evaluation():
    revoked = evaluate_activation_gate(
        terms=TERMS, rights=replace(RIGHTS, status="REVOKED"),
        budget=BUDGET, scope=SCOPE,
    )
    assert "SOURCE_RIGHTS_NOT_APPROVED" in revoked.reason_codes
    late = evaluate_activation_gate(
        terms=TERMS, rights=replace(RIGHTS, recorded_at=NOW + timedelta(seconds=1)),
        budget=BUDGET, scope=SCOPE,
    )
    assert "RIGHTS_EVIDENCE_NOT_AVAILABLE_AS_OF_RIGHTS_CHECK" in late.reason_codes


def test_exact_competition_market_region_and_use_scope_cannot_expand():
    result = evaluate_activation_gate(
        terms=TERMS,
        rights=replace(RIGHTS, markets=("h2h",)),
        budget=BUDGET,
        scope=SCOPE,
    )
    assert "MARKET_SCOPE_NOT_APPROVED" in result.reason_codes
    wildcard = evaluate_activation_gate(
        terms=TERMS, rights=replace(RIGHTS, regions=("*",)),
        budget=BUDGET, scope=SCOPE,
    )
    assert "RIGHTS_REGION_SCOPE_INVALID" in wildcard.reason_codes


def test_budget_expiry_billing_period_and_remaining_credits_fail_closed():
    expired = evaluate_activation_gate(
        terms=TERMS, rights=RIGHTS,
        budget=replace(BUDGET, valid_until=NOW),
        scope=SCOPE,
    )
    assert "BUDGET_EVIDENCE_STALE_OR_EXPIRED" in expired.reason_codes
    insufficient = evaluate_activation_gate(
        terms=TERMS, rights=RIGHTS,
        budget=replace(BUDGET, provider_remaining=5),
        scope=SCOPE,
    )
    assert "PROVIDER_REMAINING_CREDITS_INSUFFICIENT" in insufficient.reason_codes


def test_monthly_per_run_and_request_count_caps_are_independent():
    result = evaluate_activation_gate(
        terms=TERMS, rights=RIGHTS,
        budget=replace(BUDGET, monthly_hard_cap=105, per_run_hard_cap=25, request_count_cap=3),
        scope=SCOPE,
    )
    assert "MONTHLY_CREDIT_CAP_EXCEEDED" in result.reason_codes
    assert "PER_RUN_CREDIT_CAP_EXCEEDED" in result.reason_codes
    assert "REQUEST_COUNT_CAP_EXCEEDED" in result.reason_codes


def test_unknown_terms_or_budget_hashes_and_naive_timestamps_fail_closed():
    result = evaluate_activation_gate(
        terms=replace(TERMS, evidence_sha256="unknown"),
        rights=RIGHTS,
        budget=replace(BUDGET, evidence_sha256="bad"),
        scope=replace(SCOPE, dispatch_at=datetime(2026, 11, 13, 12)),
    )
    assert "ACCOUNT_TERMS_EVIDENCE_HASH_INVALID" in result.reason_codes
    assert "BUDGET_EVIDENCE_HASH_INVALID" in result.reason_codes
    assert "ACTIVATION_TIME_INVALID" in result.reason_codes

def test_malformed_rights_scope_and_datetime_billing_period_fail_closed_without_crashing():
    malformed = evaluate_activation_gate(
        terms=TERMS, rights=replace(RIGHTS, competitions=None),
        budget=replace(BUDGET, billing_period_start=NOW),
        scope=SCOPE,
    )
    assert "RIGHTS_COMPETITION_SCOPE_INVALID" in malformed.reason_codes
    assert "BUDGET_BILLING_PERIOD_INVALID" in malformed.reason_codes


def test_terms_acceptance_and_rights_effective_ordering_are_enforced():
    terms_result = evaluate_activation_gate(
        terms=replace(TERMS, accepted_at=NOW, recorded_at=NOW-timedelta(seconds=1)),
        rights=RIGHTS, budget=BUDGET, scope=SCOPE,
    )
    assert "ACCOUNT_TERMS_EVIDENCE_NOT_AVAILABLE_AS_OF_RIGHTS_CHECK" in terms_result.reason_codes
    rights_result = evaluate_activation_gate(
        terms=TERMS,
        rights=replace(RIGHTS, effective_at=NOW, recorded_at=NOW-timedelta(seconds=1)),
        budget=BUDGET, scope=SCOPE,
    )
    assert "RIGHTS_EVIDENCE_NOT_AVAILABLE_AS_OF_RIGHTS_CHECK" in rights_result.reason_codes
