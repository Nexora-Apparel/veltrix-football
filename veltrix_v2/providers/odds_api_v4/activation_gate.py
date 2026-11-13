"""Account-specific, fail-closed activation evidence gate; pure offline logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AccountTermsEvidence:
    provider: str
    provider_account_ref: str
    accepted_terms_version: str
    evidence_uri: str
    evidence_sha256: str
    accepted_at: datetime
    recorded_at: datetime


@dataclass(frozen=True)
class RightsApprovalEvidence:
    provider: str
    source_id: str
    provider_account_ref: str
    approval_id: str
    status: str
    terms_version: str
    competitions: tuple[str, ...]
    markets: tuple[str, ...]
    regions: tuple[str, ...]
    permitted_uses: tuple[str, ...]
    effective_at: datetime
    recorded_at: datetime
    valid_until: datetime | None
    evidence_uri: str
    evidence_sha256: str


@dataclass(frozen=True)
class ProviderBudgetEvidence:
    provider: str
    provider_account_ref: str
    billing_period_start: date
    billing_period_end: date
    monthly_allowance: int
    provider_remaining: int
    monthly_hard_cap: int
    per_run_hard_cap: int
    request_count_cap: int
    observed_at: datetime
    valid_until: datetime
    evidence_uri: str
    evidence_sha256: str


@dataclass(frozen=True)
class ActivationScope:
    provider: str
    source_id: str
    provider_account_ref: str
    expected_terms_version: str
    competition_keys: tuple[str, ...]
    markets: tuple[str, ...]
    regions: tuple[str, ...]
    permitted_use: str
    rights_evaluated_at: datetime
    dispatch_at: datetime
    estimated_credits: int
    month_committed_credits: int
    run_committed_credits: int
    provider_credits_committed_since_snapshot: int
    request_count_committed: int


@dataclass(frozen=True)
class ActivationGateDecision:
    allowed: bool
    reason_codes: tuple[str, ...]
    monthly_credit_headroom: int | None
    run_credit_headroom: int | None
    provider_credit_headroom: int | None
    request_count_headroom: int | None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _scope_values(values: object) -> bool:
    return (
        isinstance(values, tuple) and bool(values)
        and all(_text(value) and value != "*" for value in values)
        and len(set(values)) == len(values)
    )


def _approved_scope_values(values: object) -> bool:
    return (
        isinstance(values, tuple) and bool(values)
        and all(_text(value) and value != "*" for value in values)
        and len(set(values)) == len(values)
    )


def evaluate_activation_gate(
    *,
    terms: AccountTermsEvidence,
    rights: RightsApprovalEvidence,
    budget: ProviderBudgetEvidence,
    scope: ActivationScope,
) -> ActivationGateDecision:
    """Check account-specific Terms, rights scope and quota headroom before dispatch."""
    reasons: set[str] = set()
    monthly_headroom = run_headroom = provider_headroom = request_headroom = None

    if not isinstance(terms, AccountTermsEvidence):
        reasons.add("ACCOUNT_TERMS_EVIDENCE_TYPE_INVALID")
    if not isinstance(rights, RightsApprovalEvidence):
        reasons.add("RIGHTS_EVIDENCE_TYPE_INVALID")
    if not isinstance(budget, ProviderBudgetEvidence):
        reasons.add("BUDGET_EVIDENCE_TYPE_INVALID")
    if not isinstance(scope, ActivationScope):
        reasons.add("ACTIVATION_SCOPE_TYPE_INVALID")
    if reasons:
        return ActivationGateDecision(False, tuple(sorted(reasons)), None, None, None, None)

    if scope.provider != "the_odds_api" or scope.source_id != "odds_api_v4":
        reasons.add("PROVIDER_SOURCE_NOT_ALLOWLISTED")
    if not all(_text(x) for x in (
        scope.provider_account_ref, scope.expected_terms_version, scope.permitted_use,
        terms.provider, terms.provider_account_ref, terms.accepted_terms_version,
        terms.evidence_uri, rights.provider, rights.source_id, rights.provider_account_ref,
        rights.approval_id, rights.status, rights.terms_version, rights.evidence_uri,
        budget.provider, budget.provider_account_ref, budget.evidence_uri,
    )):
        reasons.add("ACTIVATION_EVIDENCE_IDENTITY_INCOMPLETE")
    if not _hash(terms.evidence_sha256):
        reasons.add("ACCOUNT_TERMS_EVIDENCE_HASH_INVALID")
    if not _hash(rights.evidence_sha256):
        reasons.add("RIGHTS_EVIDENCE_HASH_INVALID")
    if not _hash(budget.evidence_sha256):
        reasons.add("BUDGET_EVIDENCE_HASH_INVALID")

    if (terms.provider != scope.provider or rights.provider != scope.provider
            or budget.provider != scope.provider
            or rights.source_id != scope.source_id
            or terms.provider_account_ref != scope.provider_account_ref
            or rights.provider_account_ref != scope.provider_account_ref
            or budget.provider_account_ref != scope.provider_account_ref):
        reasons.add("ACTIVATION_ACCOUNT_SCOPE_MISMATCH")

    if terms.accepted_terms_version != scope.expected_terms_version:
        reasons.add("ACCOUNT_TERMS_VERSION_MISMATCH")
    if rights.terms_version != scope.expected_terms_version:
        reasons.add("RIGHTS_TERMS_VERSION_MISMATCH")
    if rights.status != "APPROVED":
        reasons.add("SOURCE_RIGHTS_NOT_APPROVED")

    if not _aware(scope.rights_evaluated_at) or not _aware(scope.dispatch_at):
        reasons.add("ACTIVATION_TIME_INVALID")
    if not all(_aware(x) for x in (
        terms.accepted_at, terms.recorded_at, rights.effective_at,
        rights.recorded_at, budget.observed_at, budget.valid_until,
    )):
        reasons.add("ACTIVATION_EVIDENCE_TIME_INVALID")
    if (not _aware(scope.rights_evaluated_at) or not _aware(scope.dispatch_at)
            or not _aware(terms.accepted_at) or not _aware(terms.recorded_at)
            or not _aware(rights.recorded_at) or not _aware(rights.effective_at)):
        pass
    else:
        if (terms.accepted_at > terms.recorded_at
                or terms.accepted_at > scope.rights_evaluated_at
                or terms.recorded_at > scope.rights_evaluated_at):
            reasons.add("ACCOUNT_TERMS_EVIDENCE_NOT_AVAILABLE_AS_OF_RIGHTS_CHECK")
        if (rights.effective_at > rights.recorded_at
                or rights.recorded_at > scope.rights_evaluated_at
                or rights.effective_at > scope.rights_evaluated_at):
            reasons.add("RIGHTS_EVIDENCE_NOT_AVAILABLE_AS_OF_RIGHTS_CHECK")
        if rights.valid_until is not None:
            if not _aware(rights.valid_until) or rights.valid_until <= scope.rights_evaluated_at:
                reasons.add("SOURCE_RIGHTS_EXPIRED")
        if scope.rights_evaluated_at > scope.dispatch_at:
            reasons.add("RIGHTS_CHECK_AFTER_DISPATCH")

    for values, code in (
        (scope.competition_keys, "REQUEST_COMPETITION_SCOPE_INVALID"),
        (scope.markets, "REQUEST_MARKET_SCOPE_INVALID"),
        (scope.regions, "REQUEST_REGION_SCOPE_INVALID"),
    ):
        if not _scope_values(values):
            reasons.add(code)
    for values, code in (
        (rights.competitions, "RIGHTS_COMPETITION_SCOPE_INVALID"),
        (rights.markets, "RIGHTS_MARKET_SCOPE_INVALID"),
        (rights.regions, "RIGHTS_REGION_SCOPE_INVALID"),
        (rights.permitted_uses, "RIGHTS_PERMITTED_USE_SCOPE_INVALID"),
    ):
        if not _approved_scope_values(values):
            reasons.add(code)
    if (_scope_values(scope.competition_keys) and _approved_scope_values(rights.competitions)
            and not set(scope.competition_keys) <= set(rights.competitions)):
        reasons.add("COMPETITION_SCOPE_NOT_APPROVED")
    if (_scope_values(scope.markets) and _approved_scope_values(rights.markets)
            and not set(scope.markets) <= set(rights.markets)):
        reasons.add("MARKET_SCOPE_NOT_APPROVED")
    if (_scope_values(scope.regions) and _approved_scope_values(rights.regions)
            and not set(scope.regions) <= set(rights.regions)):
        reasons.add("REGION_SCOPE_NOT_APPROVED")
    if (_approved_scope_values(rights.permitted_uses)
            and scope.permitted_use not in rights.permitted_uses):
        reasons.add("PREDICTION_USE_NOT_APPROVED")

    if (not isinstance(scope.estimated_credits, int) or isinstance(scope.estimated_credits, bool)
            or scope.estimated_credits < 0):
        reasons.add("ESTIMATED_CREDITS_INVALID")
    usage_fields = (
        scope.month_committed_credits, scope.run_committed_credits,
        scope.provider_credits_committed_since_snapshot, scope.request_count_committed,
    )
    if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in usage_fields):
        reasons.add("COMMITTED_USAGE_INVALID")

    budget_fields = (
        budget.monthly_allowance, budget.provider_remaining, budget.monthly_hard_cap,
        budget.per_run_hard_cap, budget.request_count_cap,
    )
    if (any(not isinstance(x, int) or isinstance(x, bool) for x in budget_fields)
            or budget.monthly_allowance <= 0 or budget.provider_remaining < 0
            or budget.monthly_hard_cap <= 0 or budget.per_run_hard_cap <= 0
            or budget.request_count_cap <= 0):
        reasons.add("PROVIDER_BUDGET_LIMITS_INVALID")
    elif all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in usage_fields) and (
        isinstance(scope.estimated_credits, int) and not isinstance(scope.estimated_credits, bool)
        and scope.estimated_credits >= 0
    ):
        monthly_headroom = min(budget.monthly_allowance, budget.monthly_hard_cap) - scope.month_committed_credits
        run_headroom = budget.per_run_hard_cap - scope.run_committed_credits
        provider_headroom = budget.provider_remaining - scope.provider_credits_committed_since_snapshot
        request_headroom = budget.request_count_cap - scope.request_count_committed
        if monthly_headroom < scope.estimated_credits:
            reasons.add("MONTHLY_CREDIT_CAP_EXCEEDED")
        if run_headroom < scope.estimated_credits:
            reasons.add("PER_RUN_CREDIT_CAP_EXCEEDED")
        if provider_headroom < scope.estimated_credits:
            reasons.add("PROVIDER_REMAINING_CREDITS_INSUFFICIENT")
        if request_headroom < 1:
            reasons.add("REQUEST_COUNT_CAP_EXCEEDED")

    if (isinstance(budget.billing_period_start, date)
            and not isinstance(budget.billing_period_start, datetime)
            and isinstance(budget.billing_period_end, date)
            and not isinstance(budget.billing_period_end, datetime)):
        if budget.billing_period_end <= budget.billing_period_start:
            reasons.add("BUDGET_BILLING_PERIOD_INVALID")
        elif _aware(scope.dispatch_at) and not (
            budget.billing_period_start <= scope.dispatch_at.date() < budget.billing_period_end
        ):
            reasons.add("BUDGET_BILLING_PERIOD_MISMATCH")
    else:
        reasons.add("BUDGET_BILLING_PERIOD_INVALID")

    if _aware(scope.dispatch_at) and _aware(budget.observed_at) and _aware(budget.valid_until):
        if (budget.valid_until <= budget.observed_at
                or budget.observed_at > scope.dispatch_at
                or scope.dispatch_at >= budget.valid_until):
            reasons.add("BUDGET_EVIDENCE_STALE_OR_EXPIRED")

    return ActivationGateDecision(
        not reasons, tuple(sorted(reasons)), monthly_headroom, run_headroom,
        provider_headroom, request_headroom,
    )
