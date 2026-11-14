-- Durable at-most-once Telegram report delivery claims.
-- Claims are created before network dispatch. Terminal outcomes are never retried automatically.

CREATE TABLE telegram_delivery_claims (
    idempotency_key CHAR(64) PRIMARY KEY
        CHECK (idempotency_key ~ '^[0-9a-f]{64}$'),
    report_id TEXT NOT NULL CHECK (length(btrim(report_id)) > 0),
    report_sha256 CHAR(64) NOT NULL CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    destination_sha256 CHAR(64) NOT NULL CHECK (destination_sha256 ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL DEFAULT 'CLAIMED'
        CHECK (state IN ('CLAIMED', 'SENT', 'OUTCOME_UNKNOWN')),
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    telegram_message_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(telegram_message_ids) = 'array'),
    reason_code TEXT,
    CHECK (
        (state = 'CLAIMED' AND telegram_message_ids = '[]'::jsonb AND reason_code IS NULL)
        OR
        (state = 'SENT' AND jsonb_array_length(telegram_message_ids) > 0 AND reason_code IS NULL)
        OR
        (state = 'OUTCOME_UNKNOWN' AND telegram_message_ids = '[]'::jsonb
            AND reason_code IS NOT NULL AND length(btrim(reason_code)) > 0)
    )
);

CREATE OR REPLACE FUNCTION validate_telegram_delivery_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'TELEGRAM_DELIVERY_CLAIMS_APPEND_ONLY';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'CLAIMED' OR NEW.telegram_message_ids <> '[]'::jsonb
           OR NEW.reason_code IS NOT NULL THEN
            RAISE EXCEPTION 'TELEGRAM_DELIVERY_INITIAL_STATE_INVALID';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.state <> 'CLAIMED'
           OR NEW.state NOT IN ('SENT', 'OUTCOME_UNKNOWN')
           OR NEW.idempotency_key <> OLD.idempotency_key
           OR NEW.report_id <> OLD.report_id
           OR NEW.report_sha256 <> OLD.report_sha256
           OR NEW.destination_sha256 <> OLD.destination_sha256
           OR NEW.claimed_at <> OLD.claimed_at
           OR NEW.updated_at < OLD.claimed_at THEN
            RAISE EXCEPTION 'TELEGRAM_DELIVERY_TRANSITION_INVALID';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER telegram_delivery_claims_transition
    BEFORE INSERT OR UPDATE ON telegram_delivery_claims
    FOR EACH ROW EXECUTE FUNCTION validate_telegram_delivery_transition();

CREATE TRIGGER telegram_delivery_claims_no_delete
    BEFORE DELETE ON telegram_delivery_claims
    FOR EACH ROW EXECUTE FUNCTION validate_telegram_delivery_transition();

CREATE TRIGGER telegram_delivery_claims_no_truncate
    BEFORE TRUNCATE ON telegram_delivery_claims
    FOR EACH STATEMENT EXECUTE FUNCTION validate_telegram_delivery_transition();

REVOKE UPDATE, DELETE, TRUNCATE ON telegram_delivery_claims FROM PUBLIC;
