-- Append-only evidence for manual reconciliation of uncertain Telegram deliveries.
CREATE TABLE telegram_delivery_reconciliations (
    reconciliation_id UUID PRIMARY KEY,
    idempotency_key CHAR(64) NOT NULL
        REFERENCES telegram_delivery_claims(idempotency_key),
    report_id TEXT NOT NULL CHECK (length(btrim(report_id)) > 0),
    report_sha256 CHAR(64) NOT NULL CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    destination_sha256 CHAR(64) NOT NULL CHECK (destination_sha256 ~ '^[0-9a-f]{64}$'),
    outcome TEXT NOT NULL CHECK (outcome IN ('CONFIRMED_SENT', 'CONFIRMED_NOT_SENT', 'INCONCLUSIVE')),
    telegram_message_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(telegram_message_ids) = 'array'),
    evidence_uri TEXT NOT NULL CHECK (length(btrim(evidence_uri)) > 0),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    evidence_kind TEXT NOT NULL CHECK (length(btrim(evidence_kind)) > 0),
    operator_id TEXT NOT NULL CHECK (length(btrim(operator_id)) > 0),
    reviewer_id TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    reason_code TEXT NOT NULL CHECK (length(btrim(reason_code)) > 0),
    supersedes_reconciliation_id UUID
        REFERENCES telegram_delivery_reconciliations(reconciliation_id),
    CHECK (recorded_at >= observed_at),
    CHECK (
        (outcome = 'CONFIRMED_SENT' AND jsonb_array_length(telegram_message_ids) > 0)
        OR
        (outcome <> 'CONFIRMED_SENT' AND telegram_message_ids = '[]'::jsonb)
    ),
    CHECK (
        outcome <> 'CONFIRMED_NOT_SENT'
        OR (reviewer_id IS NOT NULL AND length(btrim(reviewer_id)) > 0
            AND reviewer_id <> operator_id)
    ),
    CHECK (reviewer_id IS NULL OR reviewer_id <> operator_id)
);

CREATE UNIQUE INDEX telegram_delivery_reconciliation_root_unique
    ON telegram_delivery_reconciliations(idempotency_key)
    WHERE supersedes_reconciliation_id IS NULL;

CREATE UNIQUE INDEX telegram_delivery_reconciliation_successor_unique
    ON telegram_delivery_reconciliations(supersedes_reconciliation_id)
    WHERE supersedes_reconciliation_id IS NOT NULL;

CREATE OR REPLACE FUNCTION validate_telegram_delivery_reconciliation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    claim_row RECORD;
    parent_row RECORD;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE', 'TRUNCATE') THEN
        RAISE EXCEPTION 'TELEGRAM_DELIVERY_RECONCILIATION_APPEND_ONLY';
    END IF;

    SELECT idempotency_key, report_id, report_sha256, destination_sha256, state
      INTO claim_row
      FROM telegram_delivery_claims
     WHERE idempotency_key = NEW.idempotency_key
     FOR KEY SHARE;

    IF NOT FOUND OR claim_row.state <> 'OUTCOME_UNKNOWN' THEN
        RAISE EXCEPTION 'TELEGRAM_RECONCILIATION_REQUIRES_UNKNOWN_CLAIM';
    END IF;
    IF NEW.report_id <> claim_row.report_id
       OR NEW.report_sha256 <> claim_row.report_sha256
       OR NEW.destination_sha256 <> claim_row.destination_sha256 THEN
        RAISE EXCEPTION 'TELEGRAM_RECONCILIATION_CLAIM_BINDING_MISMATCH';
    END IF;

    IF NEW.supersedes_reconciliation_id IS NULL THEN
        IF EXISTS (
            SELECT 1 FROM telegram_delivery_reconciliations
             WHERE idempotency_key = NEW.idempotency_key
        ) THEN
            RAISE EXCEPTION 'TELEGRAM_RECONCILIATION_ALREADY_RECORDED';
        END IF;
    ELSE
        SELECT reconciliation_id, idempotency_key
          INTO parent_row
          FROM telegram_delivery_reconciliations
         WHERE reconciliation_id = NEW.supersedes_reconciliation_id
         FOR KEY SHARE;
        IF NOT FOUND OR parent_row.idempotency_key <> NEW.idempotency_key THEN
            RAISE EXCEPTION 'TELEGRAM_RECONCILIATION_SUPERSESSION_MISMATCH';
        END IF;
        IF EXISTS (
            SELECT 1 FROM telegram_delivery_reconciliations
             WHERE supersedes_reconciliation_id = NEW.supersedes_reconciliation_id
        ) THEN
            RAISE EXCEPTION 'TELEGRAM_RECONCILIATION_PARENT_ALREADY_SUPERSEDED';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER telegram_delivery_reconciliations_insert_guard
    BEFORE INSERT ON telegram_delivery_reconciliations
    FOR EACH ROW EXECUTE FUNCTION validate_telegram_delivery_reconciliation();

CREATE TRIGGER telegram_delivery_reconciliations_no_update
    BEFORE UPDATE ON telegram_delivery_reconciliations
    FOR EACH ROW EXECUTE FUNCTION validate_telegram_delivery_reconciliation();

CREATE TRIGGER telegram_delivery_reconciliations_no_delete
    BEFORE DELETE ON telegram_delivery_reconciliations
    FOR EACH ROW EXECUTE FUNCTION validate_telegram_delivery_reconciliation();

CREATE TRIGGER telegram_delivery_reconciliations_no_truncate
    BEFORE TRUNCATE ON telegram_delivery_reconciliations
    FOR EACH STATEMENT EXECUTE FUNCTION validate_telegram_delivery_reconciliation();

REVOKE UPDATE, DELETE, TRUNCATE ON telegram_delivery_reconciliations FROM PUBLIC;
