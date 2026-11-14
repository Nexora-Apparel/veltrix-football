-- Phase 5 append-only prospective paper ledger.
-- Additive only. Intended for the dedicated Neon staging database first.
-- Event hashes and previous-event hashes are computed by the application ledger.
-- No historical prediction backfill is permitted.

CREATE TABLE paper_ledger_events (
    ledger_id TEXT NOT NULL CHECK (length(btrim(ledger_id)) > 0),
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    event_type TEXT NOT NULL CHECK (
        event_type IN ('PREDICTION', 'SHADOW_PREDICTION', 'SETTLEMENT')
    ),
    fixture_id TEXT NOT NULL CHECK (length(btrim(fixture_id)) > 0),
    model_version TEXT NOT NULL CHECK (length(btrim(model_version)) > 0),
    recorded_at TEXT NOT NULL CHECK (length(btrim(recorded_at)) > 0),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    previous_event_sha256 CHAR(64) NOT NULL
        CHECK (previous_event_sha256 ~ '^[0-9a-f]{64}$'),
    event_sha256 CHAR(64) NOT NULL
        CHECK (event_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ledger_id, sequence),
    UNIQUE (ledger_id, event_sha256)
);

-- One prediction per fixture/model and one settlement per fixture/model.
-- A new model version is required for a materially new model build.
CREATE UNIQUE INDEX paper_ledger_prediction_unique
    ON paper_ledger_events (ledger_id, fixture_id, model_version)
    WHERE event_type IN ('PREDICTION', 'SHADOW_PREDICTION');

CREATE UNIQUE INDEX paper_ledger_settlement_unique
    ON paper_ledger_events (ledger_id, fixture_id, model_version)
    WHERE event_type = 'SETTLEMENT';

CREATE OR REPLACE FUNCTION reject_paper_ledger_row_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'PAPER_LEDGER_APPEND_ONLY';
END;
$$;

CREATE TRIGGER paper_ledger_events_append_only
    BEFORE UPDATE OR DELETE ON paper_ledger_events
    FOR EACH ROW EXECUTE FUNCTION reject_paper_ledger_row_mutation();

CREATE TRIGGER paper_ledger_events_no_truncate
    BEFORE TRUNCATE ON paper_ledger_events
    FOR EACH STATEMENT EXECUTE FUNCTION reject_paper_ledger_row_mutation();

REVOKE UPDATE, DELETE, TRUNCATE ON paper_ledger_events FROM PUBLIC;
