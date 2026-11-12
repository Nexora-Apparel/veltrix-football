-- Additive Phase 2 history provenance. Never applies provider data or changes existing rows.

CREATE TABLE source_approvals (
    approval_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    source_id TEXT NOT NULL,
    competition_scope TEXT NOT NULL,
    data_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('APPROVED','PROVISIONAL','REVOKED')),
    rights_basis TEXT CHECK (rights_basis IN ('TERMS','WRITTEN_PERMISSION','OPEN_LICENSE','CONTRACT')),
    terms_url TEXT,
    terms_version TEXT,
    evidence_uri TEXT,
    evidence_sha256 CHAR(64) CHECK (evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'),
    reviewed_at TIMESTAMPTZ,
    reviewer_id TEXT,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    permitted_uses JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(permitted_uses) = 'array'),
    commercial_use_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    attribution_required BOOLEAN NOT NULL DEFAULT FALSE,
    attribution_text TEXT,
    attribution_url TEXT,
    raw_redistribution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (valid_until IS NULL OR valid_until > valid_from),
    CHECK (
        status <> 'APPROVED'
        OR (
            rights_basis IS NOT NULL
            AND terms_url IS NOT NULL AND terms_url <> ''
            AND terms_version IS NOT NULL AND terms_version <> ''
            AND evidence_uri IS NOT NULL AND evidence_uri <> ''
            AND evidence_sha256 IS NOT NULL
            AND reviewed_at IS NOT NULL
            AND reviewer_id IS NOT NULL AND reviewer_id <> ''
            AND jsonb_array_length(permitted_uses) > 0
        )
    ),
    CHECK (
        NOT attribution_required
        OR (
            attribution_text IS NOT NULL AND attribution_text <> ''
            AND attribution_url IS NOT NULL AND attribution_url <> ''
        )
    )
);
CREATE UNIQUE INDEX source_approvals_version_idx
    ON source_approvals(provider, source_id, competition_scope, data_type, terms_version, evidence_sha256);

CREATE TABLE provider_responses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    source_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    http_status SMALLINT NOT NULL CHECK (http_status BETWEEN 100 AND 599),
    response_sha256 CHAR(64) NOT NULL CHECK (response_sha256 ~ '^[0-9a-f]{64}$'),
    raw_body BYTEA NOT NULL CHECK (octet_length(raw_body) > 0),
    response_headers JSONB NOT NULL DEFAULT '{}'::jsonb,
    quota_limit INTEGER CHECK (quota_limit IS NULL OR quota_limit >= 0),
    quota_remaining INTEGER CHECK (quota_remaining IS NULL OR quota_remaining >= 0),
    quota_reset_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL,
    UNIQUE(provider, source_id, request_id, response_sha256)
);
CREATE INDEX provider_responses_provider_time_idx
    ON provider_responses(provider, fetched_at DESC);

CREATE TABLE provider_entitlement_observations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    source_id TEXT NOT NULL,
    plan_code TEXT NOT NULL,
    entitlement_status TEXT NOT NULL,
    country_pack_code TEXT,
    competition_ids JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(competition_ids) = 'array'),
    rate_limit_hour INTEGER CHECK (rate_limit_hour IS NULL OR rate_limit_hour >= 0),
    rate_limit_minute INTEGER CHECK (rate_limit_minute IS NULL OR rate_limit_minute >= 0),
    quota_remaining INTEGER CHECK (quota_remaining IS NULL OR quota_remaining >= 0),
    provider_response_id BIGINT REFERENCES provider_responses(id) ON DELETE RESTRICT,
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    checked_at TIMESTAMPTZ NOT NULL,
    UNIQUE(provider, source_id, checked_at, evidence_sha256)
);
CREATE INDEX provider_entitlement_history_idx
    ON provider_entitlement_observations(provider, checked_at DESC);

ALTER TABLE source_observations
    ADD COLUMN source_id TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN data_type TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN season_key TEXT,
    ADD COLUMN source_event_time TIMESTAMPTZ,
    ADD COLUMN available_at TIMESTAMPTZ,
    ADD COLUMN availability_basis TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN rights_approval_id TEXT REFERENCES source_approvals(approval_id) ON DELETE RESTRICT,
    ADD COLUMN schema_version TEXT NOT NULL DEFAULT 'v1',
    ADD COLUMN provider_response_id BIGINT REFERENCES provider_responses(id) ON DELETE RESTRICT,
    ADD COLUMN point_in_time_certifiable BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX source_observations_source_lookup_idx
    ON source_observations(provider, source_id, data_type, entity_type, provider_entity_id, retrieved_at DESC);

ALTER TABLE fixtures
    ADD COLUMN season_key TEXT,
    ADD COLUMN source_observation_id BIGINT REFERENCES source_observations(id) ON DELETE RESTRICT;
CREATE INDEX fixtures_provider_kickoff_idx ON fixtures(provider, kickoff_at);

ALTER TABLE fixture_results
    ADD COLUMN source_observation_id BIGINT REFERENCES source_observations(id) ON DELETE RESTRICT,
    ADD COLUMN available_at TIMESTAMPTZ,
    ADD COLUMN availability_basis TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN rights_approval_id TEXT REFERENCES source_approvals(approval_id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX fixture_results_source_observation_idx
    ON fixture_results(source_observation_id) WHERE source_observation_id IS NOT NULL;

CREATE TABLE fixture_result_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fixture_id BIGINT NOT NULL REFERENCES fixtures(id) ON DELETE RESTRICT,
    source_observation_id BIGINT NOT NULL UNIQUE REFERENCES source_observations(id) ON DELETE RESTRICT,
    home_score SMALLINT NOT NULL CHECK (home_score >= 0),
    away_score SMALLINT NOT NULL CHECK (away_score >= 0),
    available_at TIMESTAMPTZ,
    availability_basis TEXT NOT NULL,
    rights_approval_id TEXT NOT NULL REFERENCES source_approvals(approval_id) ON DELETE RESTRICT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX fixture_result_versions_fixture_time_idx
    ON fixture_result_versions(fixture_id, recorded_at DESC);

ALTER TABLE import_runs
    ADD COLUMN importer_version TEXT,
    ADD COLUMN manifest_sha256 CHAR(64) CHECK (manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN request_budget INTEGER NOT NULL DEFAULT 0 CHECK (request_budget >= 0),
    ADD COLUMN requests_used INTEGER NOT NULL DEFAULT 0 CHECK (requests_used >= 0),
    ADD COLUMN records_seen INTEGER NOT NULL DEFAULT 0 CHECK (records_seen >= 0),
    ADD COLUMN records_inserted INTEGER NOT NULL DEFAULT 0 CHECK (records_inserted >= 0),
    ADD COLUMN records_rejected INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
    ADD COLUMN records_quarantined INTEGER NOT NULL DEFAULT 0 CHECK (records_quarantined >= 0),
    ADD COLUMN rights_approval_id TEXT REFERENCES source_approvals(approval_id) ON DELETE RESTRICT,
    ADD COLUMN reason_code TEXT,
    ADD CONSTRAINT import_runs_requests_within_budget_check CHECK (requests_used <= request_budget),
    ADD CONSTRAINT import_runs_terminal_count_check CHECK (
        records_seen >= records_inserted + records_rejected + records_quarantined
    );

ALTER TABLE import_checkpoints
    ADD COLUMN records_rejected INTEGER NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
    ADD COLUMN records_quarantined INTEGER NOT NULL DEFAULT 0 CHECK (records_quarantined >= 0),
    ADD COLUMN requests_used INTEGER NOT NULL DEFAULT 0 CHECK (requests_used >= 0),
    ADD COLUMN response_sha256 CHAR(64) CHECK (response_sha256 IS NULL OR response_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN last_error_code TEXT,
    ADD CONSTRAINT import_checkpoints_terminal_count_check CHECK (
        records_seen >= records_inserted + records_rejected + records_quarantined
    );

CREATE TABLE sync_watermarks (
    provider TEXT NOT NULL,
    data_class TEXT NOT NULL,
    scope TEXT NOT NULL,
    cursor_value TEXT,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(provider, data_class, scope)
);

CREATE TABLE ingestion_quarantine (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    source_id TEXT NOT NULL,
    provider_entity_id TEXT NOT NULL,
    source_observation_id BIGINT REFERENCES source_observations(id) ON DELETE RESTRICT,
    import_run_id BIGINT REFERENCES import_runs(id) ON DELETE RESTRICT,
    reason_code TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution_evidence TEXT
);
CREATE INDEX ingestion_quarantine_open_idx
    ON ingestion_quarantine(provider, created_at DESC) WHERE resolved_at IS NULL;

CREATE OR REPLACE FUNCTION reject_immutable_history_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'IMMUTABLE_HISTORY_RECORD: % is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER source_observations_append_only
    BEFORE UPDATE OR DELETE ON source_observations
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER provider_responses_append_only
    BEFORE UPDATE OR DELETE ON provider_responses
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER source_approvals_append_only
    BEFORE UPDATE OR DELETE ON source_approvals
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER provider_entitlement_append_only
    BEFORE UPDATE OR DELETE ON provider_entitlement_observations
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER fixture_result_versions_append_only
    BEFORE UPDATE OR DELETE ON fixture_result_versions
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();
