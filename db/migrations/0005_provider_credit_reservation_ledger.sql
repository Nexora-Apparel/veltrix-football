-- Phase 4.3 transactional provider credit reservation ledger.
-- Additive, append-only evidence. This migration does not dispatch provider requests.

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
    evidence_uri TEXT NOT NULL CHECK (evidence_uri <> ''),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    terms_version TEXT NOT NULL CHECK (terms_version <> ''),
    rights_approval_ids JSONB NOT NULL CHECK (
        jsonb_typeof(rights_approval_ids) = 'array'
        AND jsonb_array_length(rights_approval_ids) > 0
    ),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (billing_period_end > billing_period_start),
    CHECK (provider_remaining <= monthly_allowance),
    CHECK (provider_remaining <= monthly_hard_cap)
);
CREATE INDEX provider_credit_budget_scope_idx
    ON provider_credit_budget_snapshots(
        provider, provider_account_ref, billing_period_start, billing_period_end, observed_at DESC
    );

CREATE TABLE provider_credit_reservation_events (
    reservation_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reservation_key TEXT NOT NULL CHECK (reservation_key <> ''),
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RECONCILED',
        'RETAINED','RELEASED','OVERRUN'
    )),
    provider TEXT NOT NULL CHECK (provider <> ''),
    provider_account_ref TEXT NOT NULL CHECK (provider_account_ref <> ''),
    billing_period_start DATE NOT NULL,
    billing_period_end DATE NOT NULL,
    run_key TEXT NOT NULL CHECK (run_key <> ''),
    capture_manifest_id BIGINT NOT NULL
        REFERENCES capture_manifests(capture_manifest_id) ON DELETE RESTRICT,
    request_key TEXT NOT NULL CHECK (request_key <> ''),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    request_fingerprint CHAR(64) NOT NULL
        CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    estimated_credits INTEGER NOT NULL CHECK (estimated_credits >= 0),
    reserved_credits INTEGER NOT NULL CHECK (reserved_credits >= 0),
    actual_credits INTEGER CHECK (actual_credits IS NULL OR actual_credits >= 0),
    budget_snapshot_id BIGINT NOT NULL
        REFERENCES provider_credit_budget_snapshots(budget_snapshot_id) ON DELETE RESTRICT,
    reason_code TEXT NOT NULL CHECK (reason_code <> ''),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    previous_event_sha256 CHAR(64)
        CHECK (previous_event_sha256 IS NULL OR previous_event_sha256 ~ '^[0-9a-f]{64}$'),
    event_sha256 CHAR(64) NOT NULL CHECK (event_sha256 ~ '^[0-9a-f]{64}$'),
    actor TEXT NOT NULL CHECK (actor <> ''),
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (reservation_key, event_sequence),
    UNIQUE (provider, provider_account_ref, billing_period_start, request_key, attempt_number),
    CHECK (billing_period_end > billing_period_start),
    CHECK (
        (event_type IN ('RECONCILED','OVERRUN') AND actual_credits IS NOT NULL)
        OR
        (event_type NOT IN ('RECONCILED','OVERRUN') AND actual_credits IS NULL)
    )
);
CREATE INDEX provider_credit_reservation_period_idx
    ON provider_credit_reservation_events(
        provider, provider_account_ref, billing_period_start, billing_period_end, recorded_at
    );
CREATE INDEX provider_credit_reservation_run_idx
    ON provider_credit_reservation_events(run_key, recorded_at);
CREATE INDEX provider_credit_reservation_manifest_idx
    ON provider_credit_reservation_events(capture_manifest_id, request_key, attempt_number);

CREATE TRIGGER provider_credit_budget_snapshots_append_only
    BEFORE UPDATE OR DELETE ON provider_credit_budget_snapshots
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER provider_credit_reservation_events_append_only
    BEFORE UPDATE OR DELETE ON provider_credit_reservation_events
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

-- One transaction-scoped account/period lock serializes reservations even when
-- workers reference different budget snapshot rows for the same account/month.
CREATE OR REPLACE FUNCTION reserve_provider_credits(
    p_reservation_key TEXT,
    p_provider TEXT,
    p_provider_account_ref TEXT,
    p_billing_period_start DATE,
    p_billing_period_end DATE,
    p_run_key TEXT,
    p_capture_manifest_id BIGINT,
    p_request_key TEXT,
    p_attempt_number INTEGER,
    p_request_fingerprint CHAR(64),
    p_estimated_credits INTEGER,
    p_budget_snapshot_id BIGINT,
    p_actor TEXT,
    p_occurred_at TIMESTAMPTZ,
    p_evidence_sha256 CHAR(64),
    p_event_sha256 CHAR(64)
) RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    v_budget provider_credit_budget_snapshots%ROWTYPE;
    v_existing provider_credit_reservation_events%ROWTYPE;
    v_event_id BIGINT;
    v_month_used BIGINT;
    v_run_used BIGINT;
    v_request_count BIGINT;
    v_provider_used_since_snapshot BIGINT;
    v_month_capacity BIGINT;
    v_run_capacity BIGINT;
    v_provider_capacity BIGINT;
BEGIN
    IF COALESCE(p_reservation_key, '') = '' OR COALESCE(p_provider, '') = ''
       OR COALESCE(p_provider_account_ref, '') = '' OR COALESCE(p_run_key, '') = ''
       OR COALESCE(p_request_key, '') = '' OR COALESCE(p_actor, '') = ''
       OR p_capture_manifest_id IS NULL OR p_attempt_number IS NULL OR p_attempt_number < 1
       OR p_estimated_credits IS NULL OR p_estimated_credits < 0
       OR p_request_fingerprint !~ '^[0-9a-f]{64}$'
       OR p_evidence_sha256 !~ '^[0-9a-f]{64}       OR p_occurred_at IS NULL OR p_billing_period_start IS NULL
       OR p_billing_period_end IS NULL OR p_billing_period_end <= p_billing_period_start
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_INPUT_INVALID';
    END IF;

    -- Stable lock key prevents cross-snapshot concurrent overspend.
    PERFORM pg_advisory_xact_lock(hashtextextended(
        p_provider || '|' || p_provider_account_ref || '|'
        || p_billing_period_start::text || '|' || p_billing_period_end::text, 0
    ));

    SELECT * INTO v_existing
    FROM provider_credit_reservation_events
    WHERE reservation_key = p_reservation_key AND event_sequence = 1;

    IF FOUND THEN
        IF v_existing.event_type <> 'RESERVED'
           OR v_existing.provider <> p_provider
           OR v_existing.provider_account_ref <> p_provider_account_ref
           OR v_existing.billing_period_start <> p_billing_period_start
           OR v_existing.billing_period_end <> p_billing_period_end
           OR v_existing.run_key <> p_run_key
           OR v_existing.capture_manifest_id <> p_capture_manifest_id
           OR v_existing.request_key <> p_request_key
           OR v_existing.attempt_number <> p_attempt_number
           OR v_existing.request_fingerprint <> p_request_fingerprint
           OR v_existing.estimated_credits <> p_estimated_credits
           OR v_existing.budget_snapshot_id <> p_budget_snapshot_id
        THEN
            RAISE EXCEPTION 'CREDIT_RESERVATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.reservation_event_id;
    END IF;

    SELECT * INTO v_budget
    FROM provider_credit_budget_snapshots
    WHERE budget_snapshot_id = p_budget_snapshot_id
    FOR UPDATE;

    IF NOT FOUND
       OR v_budget.provider <> p_provider
       OR v_budget.provider_account_ref <> p_provider_account_ref
       OR v_budget.billing_period_start <> p_billing_period_start
       OR v_budget.billing_period_end <> p_billing_period_end
       OR p_occurred_at < v_budget.observed_at
    THEN
        RAISE EXCEPTION 'CREDIT_BUDGET_SNAPSHOT_MISMATCH_OR_STALE';
    END IF;

    -- Latest event per reservation is the authoritative ledger state.
    WITH latest AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_provider_account_ref
          AND billing_period_start = p_billing_period_start
          AND billing_period_end = p_billing_period_end
        ORDER BY reservation_key, event_sequence DESC
    )
    SELECT
        COALESCE(SUM(CASE
            WHEN event_type IN ('RECONCILED','OVERRUN') THEN actual_credits
            WHEN event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
                THEN reserved_credits
            ELSE 0 END), 0),
        COALESCE(SUM(CASE
            WHEN run_key = p_run_key AND event_type IN ('RECONCILED','OVERRUN')
                THEN actual_credits
            WHEN run_key = p_run_key
                 AND event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
                THEN reserved_credits
            ELSE 0 END), 0),
        COUNT(*) FILTER (WHERE event_type <> 'RELEASED')
    INTO v_month_used, v_run_used, v_request_count
    FROM latest;

    -- Provider remaining is a snapshot; subtract known/held usage recorded
    -- after its observation time. Unknown quota never enters this function.
    WITH latest AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_provider_account_ref
          AND billing_period_start = p_billing_period_start
          AND billing_period_end = p_billing_period_end
          AND recorded_at > v_budget.observed_at
        ORDER BY reservation_key, event_sequence DESC
    )
    SELECT COALESCE(SUM(CASE
        WHEN event_type IN ('RECONCILED','OVERRUN') THEN actual_credits
        WHEN event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
            THEN reserved_credits
        ELSE 0 END), 0)
    INTO v_provider_used_since_snapshot
    FROM latest;

    v_month_capacity := LEAST(v_budget.monthly_allowance, v_budget.monthly_hard_cap) - v_month_used;
    v_run_capacity := v_budget.per_run_hard_cap - v_run_used;
    v_provider_capacity := v_budget.provider_remaining - v_provider_used_since_snapshot;

    IF v_month_capacity < 0 OR v_run_capacity < 0 OR v_provider_capacity < 0
       OR v_request_count >= v_budget.request_count_cap
       OR p_estimated_credits > v_month_capacity
       OR p_estimated_credits > v_run_capacity
       OR p_estimated_credits > v_provider_capacity
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_CAPACITY_EXCEEDED';
    END IF;

    INSERT INTO provider_credit_reservation_events (
        reservation_key, event_sequence, event_type, provider, provider_account_ref,
        billing_period_start, billing_period_end, run_key, capture_manifest_id,
        request_key, attempt_number, request_fingerprint, estimated_credits,
        reserved_credits, actual_credits, budget_snapshot_id, reason_code,
        evidence_sha256, previous_event_sha256, event_sha256, actor, occurred_at
    ) VALUES (
        p_reservation_key, 1, 'RESERVED', p_provider, p_provider_account_ref,
        p_billing_period_start, p_billing_period_end, p_run_key, p_capture_manifest_id,
        p_request_key, p_attempt_number, p_request_fingerprint, p_estimated_credits,
        p_estimated_credits, NULL, p_budget_snapshot_id, 'ATOMIC_CREDIT_RESERVATION',
        p_evidence_sha256, NULL,
        p_event_sha256,
        p_actor, p_occurred_at
    ) RETURNING reservation_event_id INTO v_event_id;

    RETURN v_event_id;
END;
$function$;

REVOKE ALL ON FUNCTION reserve_provider_credits(
    TEXT,TEXT,TEXT,DATE,DATE,TEXT,BIGINT,TEXT,INTEGER,CHAR,INTEGER,BIGINT,TEXT,TIMESTAMPTZ,CHAR,CHAR
) FROM PUBLIC;

       OR p_event_sha256 !~ '^[0-9a-f]{64}       OR p_occurred_at IS NULL OR p_billing_period_start IS NULL
       OR p_billing_period_end IS NULL OR p_billing_period_end <= p_billing_period_start
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_INPUT_INVALID';
    END IF;

    -- Stable lock key prevents cross-snapshot concurrent overspend.
    PERFORM pg_advisory_xact_lock(hashtextextended(
        p_provider || '|' || p_provider_account_ref || '|'
        || p_billing_period_start::text || '|' || p_billing_period_end::text, 0
    ));

    SELECT * INTO v_existing
    FROM provider_credit_reservation_events
    WHERE reservation_key = p_reservation_key AND event_sequence = 1;

    IF FOUND THEN
        IF v_existing.event_type <> 'RESERVED'
           OR v_existing.provider <> p_provider
           OR v_existing.provider_account_ref <> p_provider_account_ref
           OR v_existing.billing_period_start <> p_billing_period_start
           OR v_existing.billing_period_end <> p_billing_period_end
           OR v_existing.run_key <> p_run_key
           OR v_existing.capture_manifest_id <> p_capture_manifest_id
           OR v_existing.request_key <> p_request_key
           OR v_existing.attempt_number <> p_attempt_number
           OR v_existing.request_fingerprint <> p_request_fingerprint
           OR v_existing.estimated_credits <> p_estimated_credits
           OR v_existing.budget_snapshot_id <> p_budget_snapshot_id
        THEN
            RAISE EXCEPTION 'CREDIT_RESERVATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.reservation_event_id;
    END IF;

    SELECT * INTO v_budget
    FROM provider_credit_budget_snapshots
    WHERE budget_snapshot_id = p_budget_snapshot_id
    FOR UPDATE;

    IF NOT FOUND
       OR v_budget.provider <> p_provider
       OR v_budget.provider_account_ref <> p_provider_account_ref
       OR v_budget.billing_period_start <> p_billing_period_start
       OR v_budget.billing_period_end <> p_billing_period_end
       OR p_occurred_at < v_budget.observed_at
    THEN
        RAISE EXCEPTION 'CREDIT_BUDGET_SNAPSHOT_MISMATCH_OR_STALE';
    END IF;

    -- Latest event per reservation is the authoritative ledger state.
    WITH latest AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_provider_account_ref
          AND billing_period_start = p_billing_period_start
          AND billing_period_end = p_billing_period_end
        ORDER BY reservation_key, event_sequence DESC
    )
    SELECT
        COALESCE(SUM(CASE
            WHEN event_type IN ('RECONCILED','OVERRUN') THEN actual_credits
            WHEN event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
                THEN reserved_credits
            ELSE 0 END), 0),
        COALESCE(SUM(CASE
            WHEN run_key = p_run_key AND event_type IN ('RECONCILED','OVERRUN')
                THEN actual_credits
            WHEN run_key = p_run_key
                 AND event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
                THEN reserved_credits
            ELSE 0 END), 0),
        COUNT(*) FILTER (WHERE event_type <> 'RELEASED')
    INTO v_month_used, v_run_used, v_request_count
    FROM latest;

    -- Provider remaining is a snapshot; subtract known/held usage recorded
    -- after its observation time. Unknown quota never enters this function.
    WITH latest AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_provider_account_ref
          AND billing_period_start = p_billing_period_start
          AND billing_period_end = p_billing_period_end
          AND recorded_at > v_budget.observed_at
        ORDER BY reservation_key, event_sequence DESC
    )
    SELECT COALESCE(SUM(CASE
        WHEN event_type IN ('RECONCILED','OVERRUN') THEN actual_credits
        WHEN event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
            THEN reserved_credits
        ELSE 0 END), 0)
    INTO v_provider_used_since_snapshot
    FROM latest;

    v_month_capacity := LEAST(v_budget.monthly_allowance, v_budget.monthly_hard_cap) - v_month_used;
    v_run_capacity := v_budget.per_run_hard_cap - v_run_used;
    v_provider_capacity := v_budget.provider_remaining - v_provider_used_since_snapshot;

    IF v_month_capacity < 0 OR v_run_capacity < 0 OR v_provider_capacity < 0
       OR v_request_count >= v_budget.request_count_cap
       OR p_estimated_credits > v_month_capacity
       OR p_estimated_credits > v_run_capacity
       OR p_estimated_credits > v_provider_capacity
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_CAPACITY_EXCEEDED';
    END IF;

    INSERT INTO provider_credit_reservation_events (
        reservation_key, event_sequence, event_type, provider, provider_account_ref,
        billing_period_start, billing_period_end, run_key, capture_manifest_id,
        request_key, attempt_number, request_fingerprint, estimated_credits,
        reserved_credits, actual_credits, budget_snapshot_id, reason_code,
        evidence_sha256, previous_event_sha256, event_sha256, actor, occurred_at
    ) VALUES (
        p_reservation_key, 1, 'RESERVED', p_provider, p_provider_account_ref,
        p_billing_period_start, p_billing_period_end, p_run_key, p_capture_manifest_id,
        p_request_key, p_attempt_number, p_request_fingerprint, p_estimated_credits,
        p_estimated_credits, NULL, p_budget_snapshot_id, 'ATOMIC_CREDIT_RESERVATION',
        p_evidence_sha256, NULL,
        encode(digest(
            p_reservation_key || '|' || p_request_fingerprint || '|' || p_estimated_credits::text
            || '|' || p_budget_snapshot_id::text || '|' || p_occurred_at::text, 'sha256'
        ), 'hex'),
        p_actor, p_occurred_at
    ) RETURNING reservation_event_id INTO v_event_id;

    RETURN v_event_id;
END;
$function$;

REVOKE ALL ON FUNCTION reserve_provider_credits(
    TEXT,TEXT,TEXT,DATE,DATE,TEXT,BIGINT,TEXT,INTEGER,CHAR,INTEGER,BIGINT,TEXT,TIMESTAMPTZ,CHAR
) FROM PUBLIC;

       OR p_occurred_at IS NULL OR p_billing_period_start IS NULL
       OR p_billing_period_end IS NULL OR p_billing_period_end <= p_billing_period_start
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_INPUT_INVALID';
    END IF;

    -- Stable lock key prevents cross-snapshot concurrent overspend.
    PERFORM pg_advisory_xact_lock(hashtextextended(
        p_provider || '|' || p_provider_account_ref || '|'
        || p_billing_period_start::text || '|' || p_billing_period_end::text, 0
    ));

    SELECT * INTO v_existing
    FROM provider_credit_reservation_events
    WHERE reservation_key = p_reservation_key AND event_sequence = 1;

    IF FOUND THEN
        IF v_existing.event_type <> 'RESERVED'
           OR v_existing.provider <> p_provider
           OR v_existing.provider_account_ref <> p_provider_account_ref
           OR v_existing.billing_period_start <> p_billing_period_start
           OR v_existing.billing_period_end <> p_billing_period_end
           OR v_existing.run_key <> p_run_key
           OR v_existing.capture_manifest_id <> p_capture_manifest_id
           OR v_existing.request_key <> p_request_key
           OR v_existing.attempt_number <> p_attempt_number
           OR v_existing.request_fingerprint <> p_request_fingerprint
           OR v_existing.estimated_credits <> p_estimated_credits
           OR v_existing.budget_snapshot_id <> p_budget_snapshot_id
        THEN
            RAISE EXCEPTION 'CREDIT_RESERVATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.reservation_event_id;
    END IF;

    SELECT * INTO v_budget
    FROM provider_credit_budget_snapshots
    WHERE budget_snapshot_id = p_budget_snapshot_id
    FOR UPDATE;

    IF NOT FOUND
       OR v_budget.provider <> p_provider
       OR v_budget.provider_account_ref <> p_provider_account_ref
       OR v_budget.billing_period_start <> p_billing_period_start
       OR v_budget.billing_period_end <> p_billing_period_end
       OR p_occurred_at < v_budget.observed_at
    THEN
        RAISE EXCEPTION 'CREDIT_BUDGET_SNAPSHOT_MISMATCH_OR_STALE';
    END IF;

    -- Latest event per reservation is the authoritative ledger state.
    WITH latest AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_provider_account_ref
          AND billing_period_start = p_billing_period_start
          AND billing_period_end = p_billing_period_end
        ORDER BY reservation_key, event_sequence DESC
    )
    SELECT
        COALESCE(SUM(CASE
            WHEN event_type IN ('RECONCILED','OVERRUN') THEN actual_credits
            WHEN event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
                THEN reserved_credits
            ELSE 0 END), 0),
        COALESCE(SUM(CASE
            WHEN run_key = p_run_key AND event_type IN ('RECONCILED','OVERRUN')
                THEN actual_credits
            WHEN run_key = p_run_key
                 AND event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
                THEN reserved_credits
            ELSE 0 END), 0),
        COUNT(*) FILTER (WHERE event_type <> 'RELEASED')
    INTO v_month_used, v_run_used, v_request_count
    FROM latest;

    -- Provider remaining is a snapshot; subtract known/held usage recorded
    -- after its observation time. Unknown quota never enters this function.
    WITH latest AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_provider_account_ref
          AND billing_period_start = p_billing_period_start
          AND billing_period_end = p_billing_period_end
          AND recorded_at > v_budget.observed_at
        ORDER BY reservation_key, event_sequence DESC
    )
    SELECT COALESCE(SUM(CASE
        WHEN event_type IN ('RECONCILED','OVERRUN') THEN actual_credits
        WHEN event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
            THEN reserved_credits
        ELSE 0 END), 0)
    INTO v_provider_used_since_snapshot
    FROM latest;

    v_month_capacity := LEAST(v_budget.monthly_allowance, v_budget.monthly_hard_cap) - v_month_used;
    v_run_capacity := v_budget.per_run_hard_cap - v_run_used;
    v_provider_capacity := v_budget.provider_remaining - v_provider_used_since_snapshot;

    IF v_month_capacity < 0 OR v_run_capacity < 0 OR v_provider_capacity < 0
       OR v_request_count >= v_budget.request_count_cap
       OR p_estimated_credits > v_month_capacity
       OR p_estimated_credits > v_run_capacity
       OR p_estimated_credits > v_provider_capacity
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_CAPACITY_EXCEEDED';
    END IF;

    INSERT INTO provider_credit_reservation_events (
        reservation_key, event_sequence, event_type, provider, provider_account_ref,
        billing_period_start, billing_period_end, run_key, capture_manifest_id,
        request_key, attempt_number, request_fingerprint, estimated_credits,
        reserved_credits, actual_credits, budget_snapshot_id, reason_code,
        evidence_sha256, previous_event_sha256, event_sha256, actor, occurred_at
    ) VALUES (
        p_reservation_key, 1, 'RESERVED', p_provider, p_provider_account_ref,
        p_billing_period_start, p_billing_period_end, p_run_key, p_capture_manifest_id,
        p_request_key, p_attempt_number, p_request_fingerprint, p_estimated_credits,
        p_estimated_credits, NULL, p_budget_snapshot_id, 'ATOMIC_CREDIT_RESERVATION',
        p_evidence_sha256, NULL,
        encode(digest(
            p_reservation_key || '|' || p_request_fingerprint || '|' || p_estimated_credits::text
            || '|' || p_budget_snapshot_id::text || '|' || p_occurred_at::text, 'sha256'
        ), 'hex'),
        p_actor, p_occurred_at
    ) RETURNING reservation_event_id INTO v_event_id;

    RETURN v_event_id;
END;
$function$;

REVOKE ALL ON FUNCTION reserve_provider_credits(
    TEXT,TEXT,TEXT,DATE,DATE,TEXT,BIGINT,TEXT,INTEGER,CHAR,INTEGER,BIGINT,TEXT,TIMESTAMPTZ,CHAR
) FROM PUBLIC;
