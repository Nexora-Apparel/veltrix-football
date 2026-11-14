-- Provider-neutral, append-only prospective prediction/evaluation ledger.
-- Separate schema/version stream: does not depend on Odds API migrations 0005-0007.
CREATE SCHEMA IF NOT EXISTS veltrix_eval;

CREATE TABLE IF NOT EXISTS veltrix_eval.schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum_sha256 CHAR(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS veltrix_eval.capture_runs (
    capture_run_id UUID PRIMARY KEY,
    provider TEXT NOT NULL CHECK (length(trim(provider)) > 0),
    source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count >= 0),
    request_budget INTEGER NOT NULL CHECK (request_budget > 0),
    provider_scope JSONB NOT NULL CHECK (jsonb_typeof(provider_scope) = 'object'),
    attribution JSONB NOT NULL CHECK (jsonb_typeof(attribution) = 'object'),
    status TEXT NOT NULL CHECK (status IN ('COMPLETED', 'PARTIAL', 'FAILED')),
    report_sha256 CHAR(64) NOT NULL CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    paid_requests INTEGER NOT NULL DEFAULT 0 CHECK (paid_requests = 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (completed_at >= started_at),
    CHECK (created_at >= completed_at),
    CHECK (request_count <= request_budget)
);

CREATE TABLE IF NOT EXISTS veltrix_eval.fixture_snapshots (
    snapshot_id UUID PRIMARY KEY,
    capture_run_id UUID NOT NULL REFERENCES veltrix_eval.capture_runs(capture_run_id),
    provider TEXT NOT NULL CHECK (length(trim(provider)) > 0),
    source_id TEXT NOT NULL CHECK (length(trim(source_id)) > 0),
    provider_fixture_id TEXT NOT NULL CHECK (length(trim(provider_fixture_id)) > 0),
    provider_competition_id TEXT NOT NULL CHECK (length(trim(provider_competition_id)) > 0),
    provider_home_team_id TEXT NOT NULL CHECK (length(trim(provider_home_team_id)) > 0),
    provider_away_team_id TEXT NOT NULL CHECK (length(trim(provider_away_team_id)) > 0),
    competition_name TEXT NOT NULL,
    home_team_name TEXT NOT NULL,
    away_team_name TEXT NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    source_status TEXT NOT NULL CHECK (source_status IN ('SCHEDULED', 'FINISHED', 'POSTPONED', 'CANCELLED', 'UNKNOWN')),
    home_goals INTEGER CHECK (home_goals IS NULL OR home_goals >= 0),
    away_goals INTEGER CHECK (away_goals IS NULL OR away_goals >= 0),
    retrieved_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ,
    availability_basis TEXT NOT NULL CHECK (length(trim(availability_basis)) > 0),
    point_in_time_certifiable BOOLEAN NOT NULL DEFAULT FALSE,
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    rights_approval_id TEXT NOT NULL CHECK (length(trim(rights_approval_id)) > 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK ((source_status = 'FINISHED') = (home_goals IS NOT NULL AND away_goals IS NOT NULL)),
    CHECK (source_status <> 'FINISHED' OR available_at IS NOT NULL),
    CHECK (source_status <> 'SCHEDULED' OR available_at IS NULL),
    CHECK (available_at IS NULL OR available_at >= kickoff_at),
    CHECK (source_status <> 'FINISHED' OR available_at <= retrieved_at),
    CHECK (NOT point_in_time_certifiable OR (source_status = 'FINISHED' AND available_at IS NOT NULL AND available_at <= retrieved_at)),
    CHECK (created_at >= retrieved_at),
    CHECK (provider_home_team_id <> provider_away_team_id),
    UNIQUE (capture_run_id, provider, source_id, provider_fixture_id, payload_sha256)
);

CREATE INDEX IF NOT EXISTS fixture_snapshots_lookup_idx
    ON veltrix_eval.fixture_snapshots (source_id, provider_competition_id, kickoff_at);
CREATE INDEX IF NOT EXISTS fixture_snapshots_provider_fixture_idx
    ON veltrix_eval.fixture_snapshots (provider, provider_fixture_id, retrieved_at DESC);

CREATE TABLE IF NOT EXISTS veltrix_eval.prediction_batches (
    batch_id UUID PRIMARY KEY,
    cutoff_at TIMESTAMPTZ NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL CHECK (length(trim(model_version)) > 0),
    model_config JSONB NOT NULL CHECK (jsonb_typeof(model_config) = 'object'),
    model_config_sha256 CHAR(64) NOT NULL CHECK (model_config_sha256 ~ '^[0-9a-f]{64}$'),
    source_manifest_sha256 CHAR(64) NOT NULL CHECK (source_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    requested_target_count INTEGER NOT NULL CHECK (requested_target_count >= 0),
    forecast_count INTEGER NOT NULL CHECK (forecast_count BETWEEN 0 AND 25),
    publication_locked BOOLEAN NOT NULL DEFAULT TRUE CHECK (publication_locked = TRUE),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (generated_at >= cutoff_at),
    CHECK (created_at >= generated_at)
);

CREATE TABLE IF NOT EXISTS veltrix_eval.prediction_records (
    prediction_id UUID PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES veltrix_eval.prediction_batches(batch_id),
    target_snapshot_id UUID NOT NULL REFERENCES veltrix_eval.fixture_snapshots(snapshot_id),
    fixture_id TEXT NOT NULL CHECK (length(trim(fixture_id)) > 0),
    competition_id TEXT NOT NULL CHECK (length(trim(competition_id)) > 0),
    home_team_id TEXT NOT NULL CHECK (length(trim(home_team_id)) > 0),
    away_team_id TEXT NOT NULL CHECK (length(trim(away_team_id)) > 0),
    kickoff_at TIMESTAMPTZ NOT NULL,
    target_retrieved_at TIMESTAMPTZ NOT NULL,
    cutoff_at TIMESTAMPTZ NOT NULL,
    expected_home_goals NUMERIC(9,6) NOT NULL CHECK (expected_home_goals > 0),
    expected_away_goals NUMERIC(9,6) NOT NULL CHECK (expected_away_goals > 0),
    home_win NUMERIC(10,9) NOT NULL CHECK (home_win BETWEEN 0 AND 1),
    draw NUMERIC(10,9) NOT NULL CHECK (draw BETWEEN 0 AND 1),
    away_win NUMERIC(10,9) NOT NULL CHECK (away_win BETWEEN 0 AND 1),
    btts_yes NUMERIC(10,9) NOT NULL CHECK (btts_yes BETWEEN 0 AND 1),
    over_2_5 NUMERIC(10,9) NOT NULL CHECK (over_2_5 BETWEEN 0 AND 1),
    evidence_match_count INTEGER NOT NULL CHECK (evidence_match_count >= 0),
    home_team_match_count INTEGER NOT NULL CHECK (home_team_match_count >= 0),
    away_team_match_count INTEGER NOT NULL CHECK (away_team_match_count >= 0),
    sample_floor_met BOOLEAN NOT NULL,
    publishable BOOLEAN NOT NULL DEFAULT FALSE CHECK (publishable = FALSE),
    publication_reason TEXT NOT NULL CHECK (length(trim(publication_reason)) > 0),
    model_version TEXT NOT NULL CHECK (length(trim(model_version)) > 0),
    model_config_sha256 CHAR(64) NOT NULL CHECK (model_config_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (kickoff_at > cutoff_at),
    CHECK (target_retrieved_at <= cutoff_at),
    CHECK (home_team_id <> away_team_id),
    CHECK (created_at >= cutoff_at),
    CHECK (abs((home_win + draw + away_win) - 1.0) <= 0.00001),
    UNIQUE (batch_id, fixture_id)
);

CREATE INDEX IF NOT EXISTS prediction_records_fixture_idx
    ON veltrix_eval.prediction_records (fixture_id, cutoff_at);
CREATE INDEX IF NOT EXISTS prediction_records_batch_idx
    ON veltrix_eval.prediction_records (batch_id);

CREATE TABLE IF NOT EXISTS veltrix_eval.result_settlements (
    settlement_id UUID PRIMARY KEY,
    prediction_id UUID NOT NULL REFERENCES veltrix_eval.prediction_records(prediction_id),
    settlement_revision INTEGER NOT NULL CHECK (settlement_revision >= 1),
    result_provider TEXT NOT NULL CHECK (length(trim(result_provider)) > 0),
    result_source_id TEXT NOT NULL CHECK (length(trim(result_source_id)) > 0),
    provider_fixture_id TEXT NOT NULL CHECK (length(trim(provider_fixture_id)) > 0),
    home_goals INTEGER NOT NULL CHECK (home_goals >= 0),
    away_goals INTEGER NOT NULL CHECK (away_goals >= 0),
    result_available_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    settled_at TIMESTAMPTZ NOT NULL,
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (result_available_at <= recorded_at),
    CHECK (settled_at <= recorded_at),
    CHECK (created_at >= recorded_at),
    UNIQUE (prediction_id, settlement_revision)
);

CREATE INDEX IF NOT EXISTS result_settlements_prediction_idx
    ON veltrix_eval.result_settlements (prediction_id, settlement_revision DESC);

CREATE TABLE IF NOT EXISTS veltrix_eval.evaluation_runs (
    evaluation_id UUID PRIMARY KEY,
    model_version TEXT NOT NULL CHECK (length(trim(model_version)) > 0),
    model_config_sha256 CHAR(64) NOT NULL CHECK (model_config_sha256 ~ '^[0-9a-f]{64}$'),
    evaluation_as_of TIMESTAMPTZ NOT NULL,
    dataset_manifest_sha256 CHAR(64) NOT NULL CHECK (dataset_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    eligible_fixture_count INTEGER NOT NULL CHECK (eligible_fixture_count >= 0),
    scored_fixture_count INTEGER NOT NULL CHECK (scored_fixture_count >= 0),
    brier_score NUMERIC(12,9) CHECK (brier_score BETWEEN 0 AND 1),
    log_loss NUMERIC(12,9) CHECK (log_loss >= 0),
    baseline_brier_score NUMERIC(12,9) CHECK (baseline_brier_score BETWEEN 0 AND 1),
    baseline_log_loss NUMERIC(12,9) CHECK (baseline_log_loss >= 0),
    metrics JSONB NOT NULL CHECK (jsonb_typeof(metrics) = 'object'),
    publication_locked BOOLEAN NOT NULL DEFAULT TRUE CHECK (publication_locked = TRUE),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (scored_fixture_count <= eligible_fixture_count),
    CHECK (created_at >= evaluation_as_of)
);

CREATE OR REPLACE FUNCTION veltrix_eval.validate_fixture_snapshot_capture()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $
DECLARE
    capture_provider TEXT;
    capture_source_id TEXT;
BEGIN
    SELECT provider, source_id INTO capture_provider, capture_source_id
    FROM veltrix_eval.capture_runs
    WHERE capture_run_id = NEW.capture_run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'CAPTURE_RUN_NOT_FOUND' USING ERRCODE = '23503';
    END IF;
    IF NEW.provider <> capture_provider OR NEW.source_id <> capture_source_id THEN
        RAISE EXCEPTION 'FIXTURE_CAPTURE_SOURCE_MISMATCH' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$;

CREATE OR REPLACE FUNCTION veltrix_eval.validate_prediction_target_snapshot()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $
DECLARE
    target_snapshot veltrix_eval.fixture_snapshots%ROWTYPE;
    batch_row veltrix_eval.prediction_batches%ROWTYPE;
BEGIN
    SELECT * INTO target_snapshot
    FROM veltrix_eval.fixture_snapshots
    WHERE snapshot_id = NEW.target_snapshot_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'TARGET_SNAPSHOT_NOT_FOUND' USING ERRCODE = '23503';
    END IF;
    IF target_snapshot.source_status <> 'SCHEDULED' THEN
        RAISE EXCEPTION 'PREDICTION_TARGET_NOT_SCHEDULED' USING ERRCODE = '23514';
    END IF;
    IF NEW.fixture_id <> target_snapshot.source_id || ':' || target_snapshot.provider_fixture_id
       OR NEW.competition_id <> target_snapshot.source_id || ':' || target_snapshot.provider_competition_id
       OR NEW.home_team_id <> target_snapshot.source_id || ':' || target_snapshot.provider_home_team_id
       OR NEW.away_team_id <> target_snapshot.source_id || ':' || target_snapshot.provider_away_team_id
       OR NEW.kickoff_at <> target_snapshot.kickoff_at
       OR NEW.target_retrieved_at <> target_snapshot.retrieved_at THEN
        RAISE EXCEPTION 'PREDICTION_TARGET_IDENTITY_MISMATCH' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO batch_row
    FROM veltrix_eval.prediction_batches
    WHERE batch_id = NEW.batch_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PREDICTION_BATCH_NOT_FOUND' USING ERRCODE = '23503';
    END IF;
    IF NEW.cutoff_at <> batch_row.cutoff_at
       OR NEW.model_version <> batch_row.model_version
       OR NEW.model_config_sha256 <> batch_row.model_config_sha256 THEN
        RAISE EXCEPTION 'PREDICTION_BATCH_CONFIGURATION_MISMATCH' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$;

CREATE OR REPLACE FUNCTION veltrix_eval.reject_append_only_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'APPEND_ONLY_TABLE: %.%', TG_TABLE_SCHEMA, TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'schema_migrations',
        'capture_runs',
        'fixture_snapshots',
        'prediction_batches',
        'prediction_records',
        'result_settlements',
        'evaluation_runs'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS append_only_guard ON veltrix_eval.%I', table_name);
        EXECUTE format(
            'CREATE TRIGGER append_only_guard BEFORE UPDATE OR DELETE ON veltrix_eval.%I '
            'FOR EACH ROW EXECUTE FUNCTION veltrix_eval.reject_append_only_mutation()',
            table_name
        );
    END LOOP;
END;
$$;

DROP TRIGGER IF EXISTS fixture_capture_consistency ON veltrix_eval.fixture_snapshots;
CREATE TRIGGER fixture_capture_consistency
BEFORE INSERT ON veltrix_eval.fixture_snapshots
FOR EACH ROW EXECUTE FUNCTION veltrix_eval.validate_fixture_snapshot_capture();

DROP TRIGGER IF EXISTS prediction_target_consistency ON veltrix_eval.prediction_records;
CREATE TRIGGER prediction_target_consistency
BEFORE INSERT ON veltrix_eval.prediction_records
FOR EACH ROW EXECUTE FUNCTION veltrix_eval.validate_prediction_target_snapshot();
