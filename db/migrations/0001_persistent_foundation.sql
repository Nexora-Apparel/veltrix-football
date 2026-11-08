CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    checksum CHAR(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE provider_accounts (
    provider TEXT PRIMARY KEY,
    plan_code TEXT,
    entitlement_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
        CHECK (entitlement_status IN ('UNVERIFIED','ACTIVE','SUSPENDED','EXPIRED')),
    checked_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE countries (
    country_code CHAR(2) PRIMARY KEY CHECK (country_code ~ '^[A-Z]{2}$'),
    country_name TEXT NOT NULL,
    source_provider TEXT NOT NULL,
    source_country_id TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (source_provider, source_country_id)
);

CREATE TABLE competitions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_competition_id TEXT NOT NULL,
    country_code CHAR(2) REFERENCES countries(country_code),
    name TEXT NOT NULL,
    season TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (provider, provider_competition_id)
);

CREATE TABLE teams (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_team_id TEXT NOT NULL,
    name TEXT NOT NULL,
    country_code CHAR(2) REFERENCES countries(country_code),
    observed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (provider, provider_team_id)
);

CREATE TABLE fixtures (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_fixture_id TEXT NOT NULL,
    competition_id BIGINT REFERENCES competitions(id),
    home_team_id BIGINT NOT NULL REFERENCES teams(id),
    away_team_id BIGINT NOT NULL REFERENCES teams(id),
    kickoff_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN
        ('SCHEDULED','LIVE','FINISHED','POSTPONED','CANCELLED','ABANDONED','UNKNOWN')),
    source_payload_sha256 CHAR(64) NOT NULL
        CHECK (source_payload_sha256 ~ '^[0-9a-f]{64}$'),
    retrieved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, provider_fixture_id),
    CHECK (home_team_id <> away_team_id)
);

CREATE TABLE fixture_results (
    fixture_id BIGINT PRIMARY KEY REFERENCES fixtures(id) ON DELETE RESTRICT,
    home_score SMALLINT NOT NULL CHECK (home_score >= 0),
    away_score SMALLINT NOT NULL CHECK (away_score >= 0),
    result_source TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    CHECK (result_source <> '')
);

CREATE TABLE source_observations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    provider_entity_id TEXT NOT NULL,
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    retrieved_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE (provider, endpoint, entity_type, provider_entity_id, payload_sha256)
);

CREATE TABLE import_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    import_type TEXT NOT NULL,
    boundary_start TIMESTAMPTZ NOT NULL,
    boundary_end TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PLANNED','RUNNING','COMPLETED','FAILED','PAUSED')),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CHECK (boundary_end > boundary_start)
);

CREATE TABLE import_checkpoints (
    import_run_id BIGINT NOT NULL REFERENCES import_runs(id) ON DELETE RESTRICT,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    cursor_value TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
    records_seen INTEGER NOT NULL DEFAULT 0 CHECK (records_seen >= 0),
    records_inserted INTEGER NOT NULL DEFAULT 0 CHECK (records_inserted >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (import_run_id, window_start, window_end),
    CHECK (window_end > window_start)
);

CREATE TABLE reconciliation_audits (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manifest_sha256 CHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    expected_migrations INTEGER NOT NULL CHECK (expected_migrations >= 0),
    applied_migrations INTEGER NOT NULL CHECK (applied_migrations >= 0),
    status TEXT NOT NULL CHECK (status IN ('PASS','FAIL')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX fixtures_kickoff_idx ON fixtures(kickoff_at);
CREATE INDEX fixtures_competition_kickoff_idx ON fixtures(competition_id, kickoff_at);
CREATE INDEX fixtures_home_kickoff_idx ON fixtures(home_team_id, kickoff_at);
CREATE INDEX fixtures_away_kickoff_idx ON fixtures(away_team_id, kickoff_at);
CREATE INDEX source_observations_lookup_idx ON source_observations(provider, entity_type, provider_entity_id, retrieved_at DESC);
CREATE INDEX import_checkpoints_status_idx ON import_checkpoints(import_run_id, status);
