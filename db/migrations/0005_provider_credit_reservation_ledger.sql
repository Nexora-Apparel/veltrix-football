-- Phase 4.3 transactional provider credit reservation ledger.
-- Additive, append-only evidence. No provider dispatch is implemented here.

CREATE TABLE provider_credit_budget_snapshots (
    budget_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider <> ''),
    provider_account_ref TEXT NOT NULL CHECK (provider_account_ref <> ''),
    billing_period_start DATE NOT NULL,
    billing_period_end DATE NOT NULL,
    monthly_allowance INTEGER NOT NULL CHECK (monthly_allowance > 0),
    provider_remaining INTEGER NOT NULL CHECK (provider_remaining >= 0),
    monthly_hard_cap INTEGER NOT NULL CHECK (monthly_hard_cap > 0),
    per_run_hard_cap INTEGER NOT NULL CHECK (per_run_hard_cap > 0),
    request_count_cap INTEGER NOT NULL CHECK (request_count_cap > 0),
    provider_used INTEGER CHECK (provider_used IS NULL OR provider_used >= 0),
    provider_last_cost INTEGER CHECK (provider_last_cost IS NULL OR provider_last_cost >= 0),
    observed_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    evidence_uri TEXT NOT NULL CHECK (evidence_uri <> ''),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    terms_version TEXT NOT NULL CHECK (terms_version <> ''),
    terms_acceptance_evidence_uri TEXT NOT NULL CHECK (terms_acceptance_evidence_uri <> ''),
    terms_acceptance_evidence_sha256 CHAR(64) NOT NULL
        CHECK (terms_acceptance_evidence_sha256 ~ '^[0-9a-f]{64}    rights_approval_ids JSONB NOT NULL CHECK (
        jsonb_typeof(rights_approval_ids) = 'array'
        AND jsonb_array_length(rights_approval_ids) > 0
    ),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (billing_period_end > billing_period_start),
    CHECK (valid_until > observed_at)
);

CREATE INDEX provider_credit_budget_scope_idx
ON provider_credit_budget_snapshots
(provider, provider_account_ref, billing_period_start, billing_period_end, observed_at DESC);
