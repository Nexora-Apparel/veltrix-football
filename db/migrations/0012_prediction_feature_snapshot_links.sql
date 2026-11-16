-- Additive, append-only provenance bridge from a prospective V2 prediction
-- ledger event to the exact PIT feature snapshot and eligibility evidence.
-- Existing paper-ledger events and feature snapshots are never updated.

CREATE TABLE prediction_feature_snapshot_links (
    ledger_id TEXT NOT NULL CHECK (length(btrim(ledger_id)) > 0),
    prediction_sequence BIGINT NOT NULL CHECK (prediction_sequence > 0),
    prediction_event_sha256 CHAR(64) NOT NULL
        CHECK (prediction_event_sha256 ~ '^[0-9a-f]{64}$'),
    feature_snapshot_id BIGINT NOT NULL
        REFERENCES feature_snapshots(feature_snapshot_id) ON DELETE RESTRICT,
    eligibility_event_id BIGINT NOT NULL
        REFERENCES feature_snapshot_eligibility_events(eligibility_event_id) ON DELETE RESTRICT,
    feature_set_sha256 CHAR(64) NOT NULL
        CHECK (feature_set_sha256 ~ '^[0-9a-f]{64}$'),
    eligibility_evidence_sha256 CHAR(64) NOT NULL
        CHECK (eligibility_evidence_sha256 ~ '^[0-9a-f]{64}$'),
    forecast_evidence_sha256 CHAR(64) NOT NULL
        CHECK (forecast_evidence_sha256 ~ '^[0-9a-f]{64}$'),
    model_artifact_sha256 CHAR(64) NOT NULL
        CHECK (model_artifact_sha256 ~ '^[0-9a-f]{64}$'),
    forecast_cutoff_at TIMESTAMPTZ NOT NULL,
    feature_snapshot_cutoff_at TIMESTAMPTZ NOT NULL,
    artifact_run_id BIGINT NOT NULL CHECK (artifact_run_id > 0),
    artifact_summary_sha256 CHAR(64) NOT NULL
        CHECK (artifact_summary_sha256 ~ '^[0-9a-f]{64}$'),
    link_sha256 CHAR(64) NOT NULL
        CHECK (link_sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ledger_id, prediction_sequence),
    UNIQUE (prediction_event_sha256),
    UNIQUE (feature_snapshot_id),
    UNIQUE (link_sha256),
    FOREIGN KEY (ledger_id, prediction_sequence)
        REFERENCES paper_ledger_events(ledger_id, sequence) ON DELETE RESTRICT,
    CHECK (feature_snapshot_cutoff_at <= forecast_cutoff_at),
    CHECK (forecast_cutoff_at <= recorded_at)
);

CREATE INDEX prediction_feature_snapshot_links_eligibility_idx
    ON prediction_feature_snapshot_links (eligibility_event_id);

CREATE OR REPLACE FUNCTION validate_prediction_feature_snapshot_link()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $prediction_feature_link$
DECLARE
    prediction paper_ledger_events%ROWTYPE;
    snapshot feature_snapshots%ROWTYPE;
    eligibility feature_snapshot_eligibility_events%ROWTYPE;
    canonical_fixture_id BIGINT;
BEGIN
    SELECT * INTO prediction
    FROM paper_ledger_events
    WHERE ledger_id = NEW.ledger_id
      AND sequence = NEW.prediction_sequence;

    IF NOT FOUND
       OR prediction.event_type <> 'PREDICTION'
       OR prediction.model_version <> 'veltrix-openplay-xg-poisson-v1'
       OR prediction.event_sha256 <> NEW.prediction_event_sha256
       OR prediction.payload->>'evidence_sha256' IS DISTINCT FROM NEW.forecast_evidence_sha256
    THEN
        RAISE EXCEPTION 'V2_PREDICTION_EVENT_EVIDENCE_LINK_INVALID';
    END IF;

    SELECT f.id INTO canonical_fixture_id
    FROM fixtures f
    WHERE f.provider = '5DollarFootballAPI'
      AND f.provider_fixture_id::text = split_part(prediction.fixture_id, ':', 2)
      AND prediction.fixture_id LIKE '5dollarfootballapi:%';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'V2_PREDICTION_CANONICAL_FIXTURE_NOT_RESOLVED';
    END IF;

    SELECT * INTO snapshot
    FROM feature_snapshots
    WHERE feature_snapshot_id = NEW.feature_snapshot_id;

    IF NOT FOUND
       OR snapshot.fixture_id <> canonical_fixture_id
       OR snapshot.feature_set_sha256 <> NEW.feature_set_sha256
       OR snapshot.prediction_cutoff_at <> NEW.feature_snapshot_cutoff_at
       OR snapshot.prediction_cutoff_at > NEW.forecast_cutoff_at
       OR NEW.forecast_cutoff_at > prediction.created_at
    THEN
        RAISE EXCEPTION 'V2_PREDICTION_FEATURE_SNAPSHOT_LINK_INVALID';
    END IF;

    SELECT * INTO eligibility
    FROM feature_snapshot_eligibility_events
    WHERE eligibility_event_id = NEW.eligibility_event_id;

    IF NOT FOUND
       OR eligibility.feature_snapshot_id <> NEW.feature_snapshot_id
       OR eligibility.eligibility_status <> 'ELIGIBLE'
       OR eligibility.evidence_sha256 <> NEW.eligibility_evidence_sha256
    THEN
        RAISE EXCEPTION 'V2_PREDICTION_FEATURE_ELIGIBILITY_LINK_INVALID';
    END IF;

    IF NEW.recorded_at < prediction.created_at THEN
        RAISE EXCEPTION 'V2_PREDICTION_FEATURE_LINK_RECORDED_BEFORE_PREDICTION';
    END IF;

    RETURN NEW;
END;
$prediction_feature_link$;

CREATE TRIGGER prediction_feature_snapshot_links_validate
    BEFORE INSERT ON prediction_feature_snapshot_links
    FOR EACH ROW EXECUTE FUNCTION validate_prediction_feature_snapshot_link();

CREATE OR REPLACE FUNCTION reject_prediction_feature_snapshot_link_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $prediction_feature_link_immutable$
BEGIN
    RAISE EXCEPTION 'PREDICTION_FEATURE_SNAPSHOT_LINKS_APPEND_ONLY';
END;
$prediction_feature_link_immutable$;

CREATE TRIGGER prediction_feature_snapshot_links_no_update
    BEFORE UPDATE OR DELETE ON prediction_feature_snapshot_links
    FOR EACH ROW EXECUTE FUNCTION reject_prediction_feature_snapshot_link_mutation();

CREATE TRIGGER prediction_feature_snapshot_links_no_truncate
    BEFORE TRUNCATE ON prediction_feature_snapshot_links
    FOR EACH STATEMENT EXECUTE FUNCTION reject_prediction_feature_snapshot_link_mutation();

REVOKE UPDATE, DELETE, TRUNCATE ON prediction_feature_snapshot_links FROM PUBLIC;
