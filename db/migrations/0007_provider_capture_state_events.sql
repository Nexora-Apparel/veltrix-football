-- Phase 4.8 append-only request-level capture state history.
-- Application generates canonical event hashes; the database enforces ordering,
-- legal transitions, previous-hash continuity and immutable storage.

CREATE TABLE provider_capture_state_events (
    capture_state_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    capture_request_id BIGINT NOT NULL
        REFERENCES provider_capture_requests(capture_request_id) ON DELETE RESTRICT,
    event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
    from_state TEXT NOT NULL CHECK (from_state IN (
        'PLANNED','BLOCKED','PREFLIGHT_APPROVED','CREDIT_RESERVED',
        'REQUEST_STARTED','RESPONSE_RECEIVED','OUTCOME_UNCERTAIN',
        'PROVIDER_REJECTED','PARSED','PARSE_REJECTED',
        'QUOTA_RECONCILED','COMMITTED'
    )),
    to_state TEXT NOT NULL CHECK (to_state IN (
        'PLANNED','BLOCKED','PREFLIGHT_APPROVED','CREDIT_RESERVED',
        'REQUEST_STARTED','RESPONSE_RECEIVED','OUTCOME_UNCERTAIN',
        'PROVIDER_REJECTED','PARSED','PARSE_REJECTED',
        'QUOTA_RECONCILED','COMMITTED'
    )),
    occurred_at TIMESTAMPTZ NOT NULL,
    actor TEXT NOT NULL CHECK (actor <> ''),
    reason_code TEXT NOT NULL CHECK (reason_code <> ''),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    previous_event_sha256 CHAR(64)
        CHECK (previous_event_sha256 IS NULL OR previous_event_sha256 ~ '^[0-9a-f]{64}$'),
    event_sha256 CHAR(64) NOT NULL CHECK (event_sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (capture_request_id, event_sequence)
);

CREATE INDEX provider_capture_state_events_latest_idx
ON provider_capture_state_events(capture_request_id, event_sequence DESC);

CREATE OR REPLACE FUNCTION validate_provider_capture_state_event()
RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE
    prior provider_capture_state_events%ROWTYPE;
    has_prior BOOLEAN := FALSE;
    allowed BOOLEAN := FALSE;
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended(NEW.capture_request_id::text, 0)
    );

    SELECT * INTO prior
    FROM provider_capture_state_events
    WHERE capture_request_id = NEW.capture_request_id
    ORDER BY event_sequence DESC
    LIMIT 1;
    has_prior := FOUND;

    IF NOT has_prior THEN
        IF NEW.event_sequence <> 1
           OR NEW.from_state <> 'PLANNED'
           OR NEW.previous_event_sha256 IS NOT NULL
        THEN
            RAISE EXCEPTION 'CAPTURE_STATE_INITIAL_EVENT_INVALID';
        END IF;
    ELSE
        IF prior.to_state IN ('BLOCKED','COMMITTED')
           OR NEW.event_sequence <> prior.event_sequence + 1
           OR NEW.from_state <> prior.to_state
           OR NEW.previous_event_sha256 IS DISTINCT FROM prior.event_sha256
           OR NEW.occurred_at < prior.occurred_at
        THEN
            RAISE EXCEPTION 'CAPTURE_STATE_EVENT_CHAIN_INVALID';
        END IF;
    END IF;

    allowed := CASE NEW.from_state
        WHEN 'PLANNED' THEN NEW.to_state IN ('BLOCKED','PREFLIGHT_APPROVED')
        WHEN 'PREFLIGHT_APPROVED' THEN NEW.to_state IN ('BLOCKED','CREDIT_RESERVED')
        WHEN 'CREDIT_RESERVED' THEN NEW.to_state IN ('BLOCKED','REQUEST_STARTED')
        WHEN 'REQUEST_STARTED' THEN NEW.to_state IN (
            'RESPONSE_RECEIVED','OUTCOME_UNCERTAIN','PROVIDER_REJECTED'
        )
        WHEN 'OUTCOME_UNCERTAIN' THEN NEW.to_state = 'QUOTA_RECONCILED'
        WHEN 'RESPONSE_RECEIVED' THEN NEW.to_state IN (
            'PARSED','PARSE_REJECTED','PROVIDER_REJECTED'
        )
        WHEN 'PROVIDER_REJECTED' THEN NEW.to_state = 'QUOTA_RECONCILED'
        WHEN 'PARSED' THEN NEW.to_state = 'QUOTA_RECONCILED'
        WHEN 'PARSE_REJECTED' THEN NEW.to_state = 'QUOTA_RECONCILED'
        WHEN 'QUOTA_RECONCILED' THEN NEW.to_state = 'COMMITTED'
        ELSE FALSE
    END;

    IF NOT allowed THEN
        RAISE EXCEPTION 'CAPTURE_STATE_TRANSITION_NOT_ALLOWED';
    END IF;

    RETURN NEW;
END;
$function$;

CREATE TRIGGER provider_capture_state_events_validate
BEFORE INSERT ON provider_capture_state_events
FOR EACH ROW EXECUTE FUNCTION validate_provider_capture_state_event();

CREATE TRIGGER provider_capture_state_events_append_only
BEFORE UPDATE OR DELETE ON provider_capture_state_events
FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();
