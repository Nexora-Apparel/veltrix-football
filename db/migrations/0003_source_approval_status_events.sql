-- Append-only source-rights status events.
-- A rights decision can be revoked without mutating the original approval evidence.

CREATE TABLE source_approval_status_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    approval_id TEXT NOT NULL REFERENCES source_approvals(approval_id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('APPROVED','REVOKED')),
    evidence_uri TEXT NOT NULL CHECK (evidence_uri <> ''),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    effective_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason_code TEXT NOT NULL CHECK (reason_code <> ''),
    UNIQUE(approval_id,status,evidence_sha256)
);
CREATE INDEX source_approval_status_latest_idx
    ON source_approval_status_events(approval_id,effective_at DESC,event_id DESC);

CREATE OR REPLACE FUNCTION reject_immutable_history_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'IMMUTABLE_HISTORY_RECORD: % is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER source_approval_status_events_append_only
    BEFORE UPDATE OR DELETE ON source_approval_status_events
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();
