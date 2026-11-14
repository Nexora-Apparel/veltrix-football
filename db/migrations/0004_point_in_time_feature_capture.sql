-- Phase 4 point-in-time capture schema.
-- Additive only. Never backfills historical publication/recording timestamps.
-- Existing Phase 3 observations remain ineligible unless independently re-captured
-- with trusted source publication evidence and separately validated.

ALTER TABLE source_observations
    ADD COLUMN source_published_at TIMESTAMPTZ,
    ADD COLUMN source_effective_at TIMESTAMPTZ,
    ADD COLUMN recorded_at TIMESTAMPTZ,
    ADD COLUMN source_timestamp_raw TEXT,
    ADD COLUMN source_timestamp_basis TEXT NOT NULL DEFAULT 'unknown'
        CHECK (source_timestamp_basis IN (
            'provider_timestamp',
            'archival_snapshot_timestamp',
            'documented_guarantee',
            'unknown'
        ));

ALTER TABLE source_observations
    ALTER COLUMN recorded_at SET DEFAULT NOW();

ALTER TABLE source_observations
    ADD CONSTRAINT source_observations_recorded_at_new_rows_check
    CHECK (recorded_at IS NOT NULL) NOT VALID;

-- Composite target for provider/source-consistent response linkage.
CREATE UNIQUE INDEX provider_responses_id_provider_source_uq
    ON provider_responses(id, provider, source_id);

CREATE TABLE capture_manifests (
    capture_manifest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manifest_key TEXT NOT NULL UNIQUE CHECK (manifest_key <> ''),
    manifest_sha256 CHAR(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    capture_scope JSONB NOT NULL CHECK (jsonb_typeof(capture_scope) = 'object'),
    requests_planned INTEGER NOT NULL CHECK (requests_planned >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE capture_manifest_events (
    capture_manifest_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    capture_manifest_id BIGINT NOT NULL
        REFERENCES capture_manifests(capture_manifest_id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('PLANNED','RUNNING','COMPLETED','FAILED','PARTIAL')),
    event_at TIMESTAMPTZ NOT NULL,
    reason_code TEXT NOT NULL CHECK (reason_code <> ''),
    evidence_sha256 CHAR(64)
        CHECK (evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'),
    coverage_summary JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(coverage_summary) = 'object'),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX capture_manifest_events_latest_idx
    ON capture_manifest_events(capture_manifest_id, event_at DESC, capture_manifest_event_id DESC);

CREATE TABLE provider_capture_requests (
    capture_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    capture_manifest_id BIGINT NOT NULL
        REFERENCES capture_manifests(capture_manifest_id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK (provider <> ''),
    source_id TEXT NOT NULL CHECK (source_id <> ''),
    endpoint TEXT NOT NULL CHECK (endpoint <> ''),
    request_key TEXT NOT NULL CHECK (request_key <> ''),
    request_fingerprint CHAR(64) NOT NULL
        CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    requested_at TIMESTAMPTZ NOT NULL,
    response_id BIGINT,
    outcome TEXT NOT NULL CHECK (outcome IN (
        'RESPONSE','TIMEOUT','NETWORK_ERROR','RATE_LIMITED','CANCELLED'
    )),
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (capture_manifest_id, request_key, attempt_number),
    FOREIGN KEY (response_id, provider, source_id)
        REFERENCES provider_responses(id, provider, source_id) ON DELETE RESTRICT,
    CHECK (
        (outcome = 'RESPONSE' AND response_id IS NOT NULL)
        OR
        (outcome <> 'RESPONSE' AND response_id IS NULL)
    )
);
CREATE INDEX provider_capture_requests_provider_time_idx
    ON provider_capture_requests(provider, source_id, requested_at DESC);
CREATE INDEX provider_capture_requests_manifest_outcome_idx
    ON provider_capture_requests(capture_manifest_id, outcome);

CREATE TABLE entity_crosswalk_versions (
    crosswalk_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('TEAM','COMPETITION','FIXTURE','PLAYER','VENUE')),
    provider TEXT NOT NULL CHECK (provider <> ''),
    source_id TEXT NOT NULL CHECK (source_id <> ''),
    provider_entity_id TEXT NOT NULL CHECK (provider_entity_id <> ''),
    canonical_entity_key TEXT NOT NULL CHECK (canonical_entity_key <> ''),
    mapping_version INTEGER NOT NULL CHECK (mapping_version > 0),
    mapping_status TEXT NOT NULL CHECK (mapping_status IN ('PENDING','RESOLVED','REJECTED','SUPERSEDED')),
    mapping_method TEXT NOT NULL CHECK (mapping_method <> ''),
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    reviewer_id TEXT,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    evidence_observation_id BIGINT
        REFERENCES source_observations(id) ON DELETE RESTRICT,
    decision_reason TEXT NOT NULL CHECK (decision_reason <> ''),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, source_id, entity_type, provider_entity_id, mapping_version),
    CHECK (valid_until IS NULL OR valid_until > valid_from),
    CHECK (
        mapping_status <> 'RESOLVED'
        OR (
            evidence_observation_id IS NOT NULL
            AND (
                (mapping_method = 'EXACT_PROVIDER_ID' AND reviewer_id IS NULL)
                OR
                (mapping_method <> 'EXACT_PROVIDER_ID' AND reviewer_id IS NOT NULL AND reviewer_id <> '')
            )
        )
    )
);
CREATE INDEX entity_crosswalk_canonical_idx
    ON entity_crosswalk_versions(entity_type, canonical_entity_key, recorded_at DESC);
CREATE INDEX entity_crosswalk_provider_entity_idx
    ON entity_crosswalk_versions(provider, source_id, entity_type, provider_entity_id, mapping_version DESC);

-- Serialize overlapping resolved-identity checks per provider entity. This closes
-- the concurrent-insert race that a plain NOT EXISTS check would leave open.
CREATE OR REPLACE FUNCTION reject_overlapping_resolved_crosswalk()
RETURNS trigger LANGUAGE plpgsql AS $func$
BEGIN
    IF NEW.mapping_status = 'RESOLVED' THEN
        PERFORM pg_advisory_xact_lock(
            hashtextextended(
                jsonb_build_array(
                    NEW.provider, NEW.source_id, NEW.entity_type, NEW.provider_entity_id
                )::text,
                0
            )
        );

        IF EXISTS (
            SELECT 1
            FROM entity_crosswalk_versions existing
            WHERE existing.provider = NEW.provider
              AND existing.source_id = NEW.source_id
              AND existing.entity_type = NEW.entity_type
              AND existing.provider_entity_id = NEW.provider_entity_id
              AND existing.mapping_status = 'RESOLVED'
              AND existing.valid_from < COALESCE(NEW.valid_until, 'infinity'::timestamptz)
              AND COALESCE(existing.valid_until, 'infinity'::timestamptz) > NEW.valid_from
        ) THEN
            RAISE EXCEPTION 'CROSSWALK_RESOLVED_VALIDITY_OVERLAP';
        END IF;
    END IF;
    RETURN NEW;
END;
$func$;

CREATE TRIGGER entity_crosswalk_no_resolved_overlap
    BEFORE INSERT ON entity_crosswalk_versions
    FOR EACH ROW EXECUTE FUNCTION reject_overlapping_resolved_crosswalk();

CREATE TABLE feature_snapshots (
    feature_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_key TEXT NOT NULL UNIQUE CHECK (snapshot_key <> ''),
    fixture_id BIGINT NOT NULL REFERENCES fixtures(id) ON DELETE RESTRICT,
    prediction_cutoff_at TIMESTAMPTZ NOT NULL,
    feature_schema_version TEXT NOT NULL CHECK (feature_schema_version <> ''),
    model_build_id TEXT NOT NULL CHECK (model_build_id <> ''),
    feature_set_sha256 CHAR(64) NOT NULL CHECK (feature_set_sha256 ~ '^[0-9a-f]{64}$'),
    selector_version TEXT NOT NULL CHECK (selector_version <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        -- Snapshot identity includes the immutable model and exact feature payload.
    UNIQUE (fixture_id, prediction_cutoff_at, feature_schema_version,
            model_build_id, selector_version, feature_set_sha256)
);
CREATE INDEX feature_snapshots_fixture_cutoff_idx
    ON feature_snapshots(fixture_id, prediction_cutoff_at DESC);

CREATE TABLE feature_snapshot_eligibility_events (
    eligibility_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feature_snapshot_id BIGINT NOT NULL
        REFERENCES feature_snapshots(feature_snapshot_id) ON DELETE RESTRICT,
    eligibility_status TEXT NOT NULL CHECK (eligibility_status IN ('PENDING','ELIGIBLE','INELIGIBLE')),
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(reason_codes) = 'array'),
    evidence_sha256 CHAR(64) NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX feature_snapshot_eligibility_latest_idx
    ON feature_snapshot_eligibility_events(feature_snapshot_id, recorded_at DESC, eligibility_event_id DESC);

CREATE TABLE feature_snapshot_links (
    feature_snapshot_link_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feature_snapshot_id BIGINT NOT NULL
        REFERENCES feature_snapshots(feature_snapshot_id) ON DELETE RESTRICT,
    feature_key TEXT NOT NULL CHECK (feature_key <> ''),
    feature_status TEXT NOT NULL CHECK (feature_status IN ('PRESENT','MISSING','REJECTED')),
    feature_value JSONB,
    source_observation_id BIGINT
        REFERENCES source_observations(id) ON DELETE RESTRICT,
    crosswalk_version_id BIGINT
        REFERENCES entity_crosswalk_versions(crosswalk_version_id) ON DELETE RESTRICT,
    source_published_at TIMESTAMPTZ,
    source_effective_at TIMESTAMPTZ,
    retrieved_at TIMESTAMPTZ,
    rights_approval_id TEXT
        REFERENCES source_approvals(approval_id) ON DELETE RESTRICT,
    eligibility_reason_code TEXT NOT NULL CHECK (eligibility_reason_code <> ''),
    value_sha256 CHAR(64)
        CHECK (value_sha256 IS NULL OR value_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (feature_snapshot_id, feature_key),
    CHECK (
        (
            feature_status = 'PRESENT'
            AND feature_value IS NOT NULL
            AND source_observation_id IS NOT NULL
            AND source_published_at IS NOT NULL
            AND retrieved_at IS NOT NULL
            AND rights_approval_id IS NOT NULL
            AND value_sha256 IS NOT NULL
        )
        OR
        (
            feature_status IN ('MISSING','REJECTED')
            AND feature_value IS NULL
            AND value_sha256 IS NULL
        )
    )
);
CREATE INDEX feature_snapshot_links_observation_idx
    ON feature_snapshot_links(source_observation_id);
CREATE INDEX feature_snapshot_links_rights_idx
    ON feature_snapshot_links(rights_approval_id);
CREATE INDEX feature_snapshot_links_status_idx
    ON feature_snapshot_links(feature_snapshot_id, feature_status);

-- Every new evidence relation is append-only. The existing function was
-- installed in migration 0002 and retained in 0003.
CREATE TRIGGER capture_manifests_append_only
    BEFORE UPDATE OR DELETE ON capture_manifests
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER capture_manifest_events_append_only
    BEFORE UPDATE OR DELETE ON capture_manifest_events
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER provider_capture_requests_append_only
    BEFORE UPDATE OR DELETE ON provider_capture_requests
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER entity_crosswalk_versions_append_only
    BEFORE UPDATE OR DELETE ON entity_crosswalk_versions
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER feature_snapshots_append_only
    BEFORE UPDATE OR DELETE ON feature_snapshots
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER feature_snapshot_eligibility_events_append_only
    BEFORE UPDATE OR DELETE ON feature_snapshot_eligibility_events
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();

CREATE TRIGGER feature_snapshot_links_append_only
    BEFORE UPDATE OR DELETE ON feature_snapshot_links
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();
