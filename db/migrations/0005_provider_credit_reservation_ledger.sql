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
    evidence_uri TEXT NOT NULL CHECK (evidence_uri <> ''),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    terms_version TEXT NOT NULL CHECK (terms_version <> ''),
    rights_approval_ids JSONB NOT NULL CHECK (
        jsonb_typeof(rights_approval_ids) = 'array'
        AND jsonb_array_length(rights_approval_ids) > 0
    ),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (billing_period_end > billing_period_start)
);

CREATE INDEX provider_credit_budget_scope_idx
ON provider_credit_budget_snapshots
(provider, provider_account_ref, billing_period_start, billing_period_end, observed_at DESC);

CREATE TABLE provider_credit_reservation_events (
    reservation_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reservation_key TEXT NOT NULL CHECK (reservation_key <> ''),
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN',
        'RECONCILED','RETAINED','RELEASED','OVERRUN'
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
ON provider_credit_reservation_events
(provider, provider_account_ref, billing_period_start, billing_period_end, recorded_at);

CREATE INDEX provider_credit_reservation_run_idx
ON provider_credit_reservation_events(run_key, recorded_at);

CREATE TRIGGER provider_credit_budget_snapshots_append_only
BEFORE UPDATE OR DELETE ON provider_credit_budget_snapshots
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER provider_credit_reservation_events_append_only
BEFORE UPDATE OR DELETE ON provider_credit_reservation_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

-- Serializes all reservations for an account and billing period, even when
-- callers hold different budget snapshot IDs.
CREATE OR REPLACE FUNCTION reserve_provider_credits(
    p_reservation_key TEXT,
    p_provider TEXT,
    p_account_ref TEXT,
    p_period_start DATE,
    p_period_end DATE,
    p_run_key TEXT,
    p_manifest_id BIGINT,
    p_request_key TEXT,
    p_attempt INTEGER,
    p_fingerprint CHAR(64),
    p_estimate INTEGER,
    p_budget_id BIGINT,
    p_actor TEXT,
    p_occurred_at TIMESTAMPTZ,
    p_evidence_hash CHAR(64),
    p_event_hash CHAR(64)
) RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    b provider_credit_budget_snapshots%ROWTYPE;
    prior provider_credit_reservation_events%ROWTYPE;
    event_id BIGINT;
    month_used BIGINT;
    run_used BIGINT;
    active_requests BIGINT;
    post_snapshot_used BIGINT;
BEGIN
    IF COALESCE(p_reservation_key, '') = ''
       OR COALESCE(p_provider, '') = ''
       OR COALESCE(p_account_ref, '') = ''
       OR COALESCE(p_run_key, '') = ''
       OR COALESCE(p_request_key, '') = ''
       OR COALESCE(p_actor, '') = ''
       OR p_manifest_id IS NULL OR p_manifest_id < 1
       OR p_attempt IS NULL OR p_attempt < 1
       OR p_estimate IS NULL OR p_estimate < 0
       OR p_fingerprint !~ '^[0-9a-f]{64}$'
       OR p_evidence_hash !~ '^[0-9a-f]{64}$'
       OR p_event_hash !~ '^[0-9a-f]{64}$'
       OR p_occurred_at IS NULL
       OR p_period_start IS NULL OR p_period_end IS NULL
       OR p_period_end <= p_period_start
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_INPUT_INVALID';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(
        p_provider || '|' || p_account_ref || '|'
        || p_period_start::text || '|' || p_period_end::text, 0
    ));

    SELECT * INTO prior
    FROM provider_credit_reservation_events
    WHERE reservation_key = p_reservation_key AND event_sequence = 1;

    IF FOUND THEN
        IF prior.event_type <> 'RESERVED'
           OR prior.provider <> p_provider
           OR prior.provider_account_ref <> p_account_ref
           OR prior.billing_period_start <> p_period_start
           OR prior.billing_period_end <> p_period_end
           OR prior.run_key <> p_run_key
           OR prior.capture_manifest_id <> p_manifest_id
           OR prior.request_key <> p_request_key
           OR prior.attempt_number <> p_attempt
           OR prior.request_fingerprint <> p_fingerprint
           OR prior.estimated_credits <> p_estimate
           OR prior.budget_snapshot_id <> p_budget_id
        THEN
            RAISE EXCEPTION 'CREDIT_RESERVATION_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN prior.reservation_event_id;
    END IF;

    SELECT * INTO b
    FROM provider_credit_budget_snapshots
    WHERE budget_snapshot_id = p_budget_id
    FOR UPDATE;

    IF NOT FOUND
       OR b.provider <> p_provider
       OR b.provider_account_ref <> p_account_ref
       OR b.billing_period_start <> p_period_start
       OR b.billing_period_end <> p_period_end
       OR p_occurred_at < b.observed_at
    THEN
        RAISE EXCEPTION 'CREDIT_BUDGET_SNAPSHOT_MISMATCH_OR_STALE';
    END IF;

    WITH latest AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_account_ref
          AND billing_period_start = p_period_start
          AND billing_period_end = p_period_end
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
    INTO month_used, run_used, active_requests
    FROM latest;

    WITH first_events AS (
        SELECT DISTINCT ON (reservation_key) *
        FROM provider_credit_reservation_events
        WHERE provider = p_provider
          AND provider_account_ref = p_account_ref
          AND billing_period_start = p_period_start
          AND billing_period_end = p_period_end
        ORDER BY reservation_key, event_sequence ASC
    ),
    eligible AS (
        SELECT reservation_key
        FROM first_events
        WHERE recorded_at > b.observed_at
    ),
    latest_after_snapshot AS (
        SELECT DISTINCT ON (e.reservation_key) e.*
        FROM provider_credit_reservation_events e
        JOIN eligible x USING (reservation_key)
        ORDER BY e.reservation_key, e.event_sequence DESC
    )
    SELECT COALESCE(SUM(CASE
        WHEN event_type IN ('RECONCILED','OVERRUN') THEN actual_credits
        WHEN event_type IN ('RESERVED','DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED')
            THEN reserved_credits
        ELSE 0 END), 0)
    INTO post_snapshot_used
    FROM latest_after_snapshot;

    IF LEAST(b.monthly_allowance, b.monthly_hard_cap) - month_used < p_estimate
       OR b.per_run_hard_cap - run_used < p_estimate
       OR b.provider_remaining - post_snapshot_used < p_estimate
       OR active_requests >= b.request_count_cap
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
        p_reservation_key, 1, 'RESERVED', p_provider, p_account_ref,
        p_period_start, p_period_end, p_run_key, p_manifest_id,
        p_request_key, p_attempt, p_fingerprint, p_estimate,
        p_estimate, NULL, p_budget_id, 'ATOMIC_CREDIT_RESERVATION',
        p_evidence_hash, NULL, p_event_hash, p_actor, p_occurred_at
    ) RETURNING reservation_event_id INTO event_id;

    RETURN event_id;
END;
$function$;

REVOKE ALL ON FUNCTION reserve_provider_credits(
    TEXT,TEXT,TEXT,DATE,DATE,TEXT,BIGINT,TEXT,INTEGER,CHAR,INTEGER,BIGINT,
    TEXT,TIMESTAMPTZ,CHAR,CHAR
) FROM PUBLIC;

-- Appends a reservation lifecycle event by copying immutable identity from the
-- first event. This is the only supported path for post-reservation transitions.
CREATE OR REPLACE FUNCTION append_provider_credit_reservation_event(
    p_reservation_key TEXT,
    p_event_type TEXT,
    p_reserved_credits INTEGER,
    p_actual_credits INTEGER,
    p_reason_code TEXT,
    p_evidence_hash CHAR(64),
    p_event_hash CHAR(64),
    p_actor TEXT,
    p_occurred_at TIMESTAMPTZ
) RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    prior provider_credit_reservation_events%ROWTYPE;
    initial provider_credit_reservation_events%ROWTYPE;
    next_sequence INTEGER;
    new_id BIGINT;
    allowed BOOLEAN := FALSE;
BEGIN
    IF COALESCE(p_reservation_key, '') = ''
       OR COALESCE(p_event_type, '') = ''
       OR COALESCE(p_reason_code, '') = ''
       OR COALESCE(p_actor, '') = ''
       OR p_reserved_credits IS NULL OR p_reserved_credits < 0
       OR p_evidence_hash !~ '^[0-9a-f]{64}$'
       OR p_event_hash !~ '^[0-9a-f]{64}$'
       OR p_occurred_at IS NULL
       OR (p_event_type IN ('RECONCILED','OVERRUN') AND (p_actual_credits IS NULL OR p_actual_credits < 0))
       OR (p_event_type NOT IN ('RECONCILED','OVERRUN') AND p_actual_credits IS NOT NULL)
    THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_EVENT_INPUT_INVALID';
    END IF;

    SELECT * INTO initial
    FROM provider_credit_reservation_events
    WHERE reservation_key = p_reservation_key AND event_sequence = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_NOT_FOUND';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(
        initial.provider || '|' || initial.provider_account_ref || '|'
        || initial.billing_period_start::text || '|' || initial.billing_period_end::text, 0
    ));

    SELECT * INTO prior
    FROM provider_credit_reservation_events
    WHERE reservation_key = p_reservation_key
    ORDER BY event_sequence DESC
    LIMIT 1;

    next_sequence := prior.event_sequence + 1;

    allowed := CASE prior.event_type
        WHEN 'RESERVED' THEN p_event_type IN (
            'DISPATCH_CONFIRMED','OUTCOME_UNCERTAIN','RETAINED','RELEASED'
        )
        WHEN 'DISPATCH_CONFIRMED' THEN p_event_type IN (
            'OUTCOME_UNCERTAIN','RECONCILED','RETAINED','RELEASED','OVERRUN'
        )
        WHEN 'OUTCOME_UNCERTAIN' THEN p_event_type IN (
            'RECONCILED','RETAINED','RELEASED','OVERRUN'
        )
        WHEN 'RETAINED' THEN p_event_type IN ('RECONCILED','RELEASED','OVERRUN')
        ELSE FALSE
    END;

    IF NOT allowed THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_TRANSITION_NOT_ALLOWED';
    END IF;

    IF p_occurred_at < prior.occurred_at THEN
        RAISE EXCEPTION 'CREDIT_RESERVATION_EVENT_TIME_NOT_MONOTONIC';
    END IF;

    INSERT INTO provider_credit_reservation_events (
        reservation_key, event_sequence, event_type, provider, provider_account_ref,
        billing_period_start, billing_period_end, run_key, capture_manifest_id,
        request_key, attempt_number, request_fingerprint, estimated_credits,
        reserved_credits, actual_credits, budget_snapshot_id, reason_code,
        evidence_sha256, previous_event_sha256, event_sha256, actor, occurred_at
    ) VALUES (
        prior.reservation_key, next_sequence, p_event_type, prior.provider,
        prior.provider_account_ref, prior.billing_period_start, prior.billing_period_end,
        prior.run_key, prior.capture_manifest_id, prior.request_key, prior.attempt_number,
        prior.request_fingerprint, prior.estimated_credits, p_reserved_credits,
        p_actual_credits, prior.budget_snapshot_id, p_reason_code, p_evidence_hash,
        prior.event_sha256, p_event_hash, p_actor, p_occurred_at
    ) RETURNING reservation_event_id INTO new_id;

    RETURN new_id;
END;
$function$;

REVOKE ALL ON FUNCTION append_provider_credit_reservation_event(
    TEXT,TEXT,INTEGER,INTEGER,TEXT,CHAR,CHAR,TEXT,TIMESTAMPTZ
) FROM PUBLIC;
