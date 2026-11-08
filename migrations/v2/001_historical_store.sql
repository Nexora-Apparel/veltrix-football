-- V2 historical store. PostgreSQL 14+. Apply only to a newly provisioned,
-- isolated V2 database after storage target and access policy are approved.
CREATE TABLE IF NOT EXISTS v2_source_records (
  source_record_id TEXT PRIMARY KEY, provider TEXT NOT NULL, source_id TEXT NOT NULL,
  provider_record_id TEXT NOT NULL, provider_fixture_id TEXT, provider_competition_id TEXT,
  provider_home_team_id TEXT, provider_away_team_id TEXT, data_class TEXT NOT NULL,
  raw_payload BYTEA NOT NULL, raw_payload_sha256 CHAR(64) NOT NULL, payload_reference TEXT NOT NULL,
  fetched_at_utc TIMESTAMPTZ NOT NULL, ingested_at_utc TIMESTAMPTZ NOT NULL,
  source_updated_at_utc TIMESTAMPTZ, ingestion_run_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE, rights_evidence JSONB NOT NULL,
  UNIQUE(provider,source_id,provider_record_id,data_class,raw_payload_sha256)
);
CREATE INDEX IF NOT EXISTS ix_v2_source_fixture ON v2_source_records(provider,source_id,provider_fixture_id);
CREATE INDEX IF NOT EXISTS ix_v2_source_competition_time ON v2_source_records(provider,provider_competition_id,fetched_at_utc);

CREATE TABLE IF NOT EXISTS v2_competition_mappings (
 provider TEXT NOT NULL,source_id TEXT NOT NULL,provider_competition_id TEXT NOT NULL,
 canonical_competition_id TEXT NOT NULL,squad_category TEXT NOT NULL,verification_state TEXT NOT NULL,
 mapping_version TEXT NOT NULL,evidence_ref TEXT NOT NULL,valid_from_utc TIMESTAMPTZ NOT NULL,
 valid_to_utc TIMESTAMPTZ,verified_at_utc TIMESTAMPTZ,
 PRIMARY KEY(provider,source_id,provider_competition_id,mapping_version)
);
CREATE TABLE IF NOT EXISTS v2_team_mappings (
 provider TEXT NOT NULL,source_id TEXT NOT NULL,provider_team_id TEXT NOT NULL,
 canonical_team_id TEXT NOT NULL,squad_category TEXT NOT NULL,verification_state TEXT NOT NULL,
 mapping_version TEXT NOT NULL,evidence_ref TEXT NOT NULL,valid_from_utc TIMESTAMPTZ NOT NULL,
 valid_to_utc TIMESTAMPTZ,verified_at_utc TIMESTAMPTZ,
 PRIMARY KEY(provider,source_id,provider_team_id,canonical_team_id,mapping_version)
);
CREATE INDEX IF NOT EXISTS ix_v2_team_mapping_lookup ON v2_team_mappings(provider,source_id,provider_team_id,valid_from_utc,valid_to_utc);

CREATE TABLE IF NOT EXISTS v2_canonical_fixtures (
 canonical_fixture_id TEXT PRIMARY KEY,canonical_competition_id TEXT NOT NULL,squad_category TEXT NOT NULL,
 canonical_home_team_id TEXT NOT NULL,canonical_away_team_id TEXT NOT NULL,
 kickoff_at_utc TIMESTAMPTZ NOT NULL,CHECK(canonical_home_team_id<>canonical_away_team_id)
);
CREATE TABLE IF NOT EXISTS v2_fixture_sources (
 provider TEXT NOT NULL,source_id TEXT NOT NULL,provider_fixture_id TEXT NOT NULL,
 provider_competition_id TEXT NOT NULL,provider_home_team_id TEXT NOT NULL,provider_away_team_id TEXT NOT NULL,
 canonical_fixture_id TEXT,source_record_id TEXT NOT NULL REFERENCES v2_source_records(source_record_id),
 identity_status TEXT NOT NULL,reason_code TEXT NOT NULL,evidence_refs JSONB NOT NULL,
 PRIMARY KEY(provider,source_id,provider_fixture_id,source_record_id),
 FOREIGN KEY(canonical_fixture_id) REFERENCES v2_canonical_fixtures(canonical_fixture_id)
);
CREATE TABLE IF NOT EXISTS v2_historical_matches (
 historical_match_id TEXT PRIMARY KEY,canonical_fixture_id TEXT NOT NULL REFERENCES v2_canonical_fixtures(canonical_fixture_id),
 home_goals INTEGER NOT NULL CHECK(home_goals>=0),away_goals INTEGER NOT NULL CHECK(away_goals>=0),
 imported_at_utc TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS v2_historical_match_sources (
 historical_match_id TEXT NOT NULL REFERENCES v2_historical_matches(historical_match_id),
 source_record_id TEXT NOT NULL REFERENCES v2_source_records(source_record_id),
 provider TEXT NOT NULL,source_id TEXT NOT NULL,provider_fixture_id TEXT NOT NULL,
 PRIMARY KEY(historical_match_id,source_record_id)
);
CREATE INDEX IF NOT EXISTS ix_v2_history_provider_fixture ON v2_historical_match_sources(provider,source_id,provider_fixture_id);

CREATE TABLE IF NOT EXISTS v2_identity_quarantine (
 quarantine_id TEXT PRIMARY KEY,provider TEXT NOT NULL,source_id TEXT NOT NULL,provider_fixture_id TEXT NOT NULL,
 source_record_id TEXT NOT NULL REFERENCES v2_source_records(source_record_id),status TEXT NOT NULL,reason_code TEXT NOT NULL,candidate_ids JSONB NOT NULL,
 created_at_utc TIMESTAMPTZ NOT NULL,resolved_at_utc TIMESTAMPTZ,resolution_evidence_ref TEXT
);
CREATE TABLE IF NOT EXISTS v2_sync_watermarks (
 provider TEXT NOT NULL,data_class TEXT NOT NULL,scope TEXT NOT NULL,cursor TEXT,
 version BIGINT NOT NULL CHECK(version>=0),updated_at_utc TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(provider,data_class,scope)
);
CREATE TABLE IF NOT EXISTS v2_ingestion_runs (
 ingestion_run_id TEXT PRIMARY KEY,provider TEXT NOT NULL,data_class TEXT NOT NULL,request_id TEXT NOT NULL,
 started_at_utc TIMESTAMPTZ NOT NULL,completed_at_utc TIMESTAMPTZ,
 fetched_count INTEGER NOT NULL DEFAULT 0,accepted_count INTEGER NOT NULL DEFAULT 0,
 rejected_count INTEGER NOT NULL DEFAULT 0,quota_units_consumed INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL,failure_reason_code TEXT
);
