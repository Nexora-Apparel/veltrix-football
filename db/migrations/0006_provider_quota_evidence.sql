-- Phase 4.5 durable quota evidence; reuses immutable provider_responses raw bytes.
-- Additive only. No provider calls or migration execution are performed by this file.

CREATE UNIQUE INDEX provider_credit_reservation_event_identity_uq
ON provider_credit_reservation_events(reservation_event_id, reservation_key);

CREATE TABLE provider_quota_snapshots (
    quota_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider <> ''),
    source_id TEXT NOT NULL CHECK (source_id <> ''),
    provider_account_ref TEXT NOT NULL CHECK (provider_account_ref <> ''),
    billing_period_start DATE NOT NULL,
    billing_period_end DATE NOT NULL,
    provider_response_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    raw_quota_headers JSONB NOT NULL CHECK (
        jsonb_typeof(raw_quota_headers) = 'object'
        AND raw_quota_headers - ARRAY[
            'x-requests-used','x-requests-remaining','x-requests-last'
        ] = '{}'::jsonb
        AND (raw_quota_headers -> 'x-requests-used' IS NULL
             OR jsonb_typeof(raw_quota_headers -> 'x-requests-used') = 'string')
        AND (raw_quota_headers -> 'x-requests-remaining' IS NULL
             OR jsonb_typeof(raw_quota_headers -> 'x-requests-remaining') = 'string')
        AND (raw_quota_headers -> 'x-requests-last' IS NULL
             OR jsonb_typeof(raw_quota_headers -> 'x-requests-last') = 'string')
    ),
    requests_used INTEGER CHECK (requests_used IS NULL OR requests_used >= 0),
    requests_remaining INTEGER CHECK (requests_remaining IS NULL OR requests_remaining >= 0),
    requests_last INTEGER CHECK (requests_last IS NULL OR requests_last >= 0),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (billing_period_end > billing_period_start),
    UNIQUE (provider_response_id),
    UNIQUE (
        quota_snapshot_id, provider, source_id, provider_account_ref,
        billing_period_start, billing_period_end
    ),
    FOREIGN KEY (provider_response_id, provider, source_id)
        REFERENCES provider_responses(id, provider, source_id) ON DELETE RESTRICT
);

CREATE INDEX provider_quota_snapshot_account_idx
ON provider_quota_snapshots(
    provider, provider_account_ref, billing_period_start, billing_period_end, observed_at DESC
);

CREATE TABLE provider_quota_reconciliation_events (
    quota_reconciliation_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reservation_event_id BIGINT NOT NULL,
    reservation_key TEXT NOT NULL CHECK (reservation_key <> ''),
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    provider TEXT NOT NULL CHECK (provider <> ''),
    source_id TEXT NOT NULL CHECK (source_id <> ''),
    provider_account_ref TEXT NOT NULL CHECK (provider_account_ref <> ''),
    billing_period_start DATE NOT NULL,
    billing_period_end DATE NOT NULL,
    before_snapshot_id BIGINT NOT NULL,
    after_snapshot_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('UNKNOWN','RECONCILED','OVERRUN')),
    actual_credits INTEGER CHECK (actual_credits IS NULL OR actual_credits >= 0),
    releasable_credits INTEGER CHECK (releasable_credits IS NULL OR releasable_credits >= 0),
    reason_code TEXT NOT NULL CHECK (reason_code <> ''),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    previous_event_sha256 CHAR(64)
        CHECK (previous_event_sha256 IS NULL OR previous_event_sha256 ~ '^[0-9a-f]{64}$'),
    event_sha256 CHAR(64) NOT NULL CHECK (event_sha256 ~ '^[0-9a-f]{64}$'),
    actor TEXT NOT NULL CHECK (actor <> ''),
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (reservation_key, event_sequence),
    FOREIGN KEY (reservation_event_id, reservation_key)
        REFERENCES provider_credit_reservation_events(reservation_event_id, reservation_key)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        before_snapshot_id, provider, source_id, provider_account_ref,
        billing_period_start, billing_period_end
    ) REFERENCES provider_quota_snapshots(
        quota_snapshot_id, provider, source_id, provider_account_ref,
        billing_period_start, billing_period_end
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        after_snapshot_id, provider, source_id, provider_account_ref,
        billing_period_start, billing_period_end
    ) REFERENCES provider_quota_snapshots(
        quota_snapshot_id, provider, source_id, provider_account_ref,
        billing_period_start, billing_period_end
    ) ON DELETE RESTRICT,
    CHECK (billing_period_end > billing_period_start),
    CHECK (
        (status = 'UNKNOWN' AND actual_credits IS NULL AND releasable_credits IS NULL)
        OR
        (status = 'RECONCILED' AND actual_credits IS NOT NULL AND releasable_credits IS NOT NULL)
        OR
        (status = 'OVERRUN' AND actual_credits IS NOT NULL AND releasable_credits = 0)
    )
);

CREATE INDEX provider_quota_reconciliation_reservation_idx
ON provider_quota_reconciliation_events(reservation_key, event_sequence DESC);

CREATE OR REPLACE FUNCTION validate_provider_quota_reconciliation_event()
RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE
    r provider_credit_reservation_events%ROWTYPE;
    before_q provider_quota_snapshots%ROWTYPE;
    after_q provider_quota_snapshots%ROWTYPE;
    prior provider_quota_reconciliation_events%ROWTYPE;
    expected_sequence INTEGER;
BEGIN
    SELECT * INTO r
    FROM provider_credit_reservation_events
    WHERE reservation_event_id = NEW.reservation_event_id
      AND reservation_key = NEW.reservation_key;

    IF NOT FOUND OR r.event_sequence <> 1 OR r.event_type <> 'RESERVED'
       OR r.provider <> NEW.provider
       OR r.provider_account_ref <> NEW.provider_account_ref
       OR r.billing_period_start <> NEW.billing_period_start
       OR r.billing_period_end <> NEW.billing_period_end
    THEN
        RAISE EXCEPTION 'QUOTA_RECONCILIATION_RESERVATION_SCOPE_MISMATCH';
    END IF;

    SELECT * INTO before_q FROM provider_quota_snapshots
    WHERE quota_snapshot_id = NEW.before_snapshot_id;
    SELECT * INTO after_q FROM provider_quota_snapshots
    WHERE quota_snapshot_id = NEW.after_snapshot_id;

    IF before_q.provider <> NEW.provider OR after_q.provider <> NEW.provider
       OR before_q.source_id <> NEW.source_id OR after_q.source_id <> NEW.source_id
       OR before_q.provider_account_ref <> NEW.provider_account_ref
       OR after_q.provider_account_ref <> NEW.provider_account_ref
       OR before_q.billing_period_start <> NEW.billing_period_start
       OR after_q.billing_period_start <> NEW.billing_period_start
       OR before_q.billing_period_end <> NEW.billing_period_end
       OR after_q.billing_period_end <> NEW.billing_period_end
       OR after_q.observed_at <= before_q.observed_at
    THEN
        RAISE EXCEPTION 'QUOTA_RECONCILIATION_SNAPSHOT_SCOPE_OR_TIME_INVALID';
    END IF;

    IF NEW.status = 'UNKNOWN' THEN
        IF NEW.actual_credits IS NOT NULL OR NEW.releasable_credits IS NOT NULL THEN
            RAISE EXCEPTION 'QUOTA_UNKNOWN_CANNOT_INFER_CREDITS';
        END IF;
    ELSE
        IF before_q.requests_used IS NULL OR before_q.requests_remaining IS NULL
           OR after_q.requests_used IS NULL OR after_q.requests_remaining IS NULL
           OR after_q.requests_last IS NULL
           OR after_q.requests_used - before_q.requests_used
                IS DISTINCT FROM before_q.requests_remaining - after_q.requests_remaining
           OR after_q.requests_used - before_q.requests_used
                IS DISTINCT FROM after_q.requests_last
        THEN
            RAISE EXCEPTION 'QUOTA_COUNTER_DELTA_NOT_EXACT';
        END IF;

        IF NEW.actual_credits <> after_q.requests_last THEN
            RAISE EXCEPTION 'QUOTA_ACTUAL_CREDITS_DO_NOT_MATCH_LAST_REQUEST';
        END IF;

        IF NEW.status = 'RECONCILED'
           AND (NEW.actual_credits > r.reserved_credits
                OR NEW.releasable_credits <> r.reserved_credits - NEW.actual_credits)
        THEN
            RAISE EXCEPTION 'QUOTA_RECONCILED_AMOUNT_INVALID';
        END IF;

        IF NEW.status = 'OVERRUN'
           AND (NEW.actual_credits <= r.reserved_credits OR NEW.releasable_credits <> 0)
        THEN
            RAISE EXCEPTION 'QUOTA_OVERRUN_AMOUNT_INVALID';
        END IF;
    END IF;

    SELECT * INTO prior
    FROM provider_quota_reconciliation_events
    WHERE reservation_key = NEW.reservation_key
    ORDER BY event_sequence DESC
    LIMIT 1;

    IF NOT FOUND THEN
        IF NEW.event_sequence <> 1 OR NEW.previous_event_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'QUOTA_RECONCILIATION_INITIAL_SEQUENCE_INVALID';
        END IF;
    ELSE
        expected_sequence := prior.event_sequence + 1;
        IF prior.status <> 'UNKNOWN'
           OR NEW.event_sequence <> expected_sequence
           OR NEW.previous_event_sha256 IS DISTINCT FROM prior.event_sha256
           OR NEW.occurred_at < prior.occurred_at
        THEN
            RAISE EXCEPTION 'QUOTA_RECONCILIATION_EVENT_CHAIN_INVALID';
        END IF;
    END IF;

    RETURN NEW;
END;
$function$;

CREATE TRIGGER provider_quota_reconciliation_validate
BEFORE INSERT ON provider_quota_reconciliation_events
FOR EACH ROW EXECUTE FUNCTION validate_provider_quota_reconciliation_event();

CREATE TRIGGER provider_quota_snapshots_append_only
BEFORE UPDATE OR DELETE ON provider_quota_snapshots
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER provider_quota_reconciliation_events_append_only
BEFORE UPDATE OR DELETE ON provider_quota_reconciliation_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();
