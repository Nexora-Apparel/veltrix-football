-- VELTRIX V2 Odds API quote evidence.
-- Additive, append-only. This migration is not applied by application startup.
-- Raw provider responses remain in provider_responses; this table links each
-- parsed bookmaker selection to exact response/request/fixture/rights evidence.

CREATE TABLE odds_quote_observations (
    odds_quote_observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_key CHAR(64) NOT NULL UNIQUE
        CHECK (observation_key ~ '^[0-9a-f]{64}$'),
    provider TEXT NOT NULL CHECK (provider = 'the_odds_api'),
    source_id TEXT NOT NULL CHECK (source_id = 'odds_api_v4'),
    sport_key TEXT NOT NULL CHECK (sport_key <> ''),
    provider_event_id TEXT NOT NULL CHECK (provider_event_id <> ''),
    fixture_id BIGINT NOT NULL REFERENCES fixtures(id) ON DELETE RESTRICT,
    crosswalk_version_id BIGINT NOT NULL
        REFERENCES entity_crosswalk_versions(crosswalk_version_id) ON DELETE RESTRICT,
    response_id BIGINT NOT NULL,
    capture_request_id BIGINT NOT NULL
        REFERENCES provider_capture_requests(capture_request_id) ON DELETE RESTRICT,
    bookmaker_key TEXT NOT NULL CHECK (bookmaker_key <> ''),
    bookmaker_title TEXT NOT NULL CHECK (bookmaker_title <> ''),
    market_key TEXT NOT NULL CHECK (market_key IN ('h2h','totals','btts')),
    selection_name TEXT NOT NULL CHECK (selection_name <> ''),
    selection_key TEXT NOT NULL CHECK (selection_key <> ''),
    line_point NUMERIC(12,4),
    decimal_price NUMERIC(12,6) NOT NULL CHECK (decimal_price > 1 AND decimal_price < 10000),
    source_timestamp_raw TEXT NOT NULL CHECK (source_timestamp_raw <> ''),
    source_published_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    response_sha256 CHAR(64) NOT NULL
        CHECK (response_sha256 ~ '^[0-9a-f]{64}$'),
    rights_approval_id TEXT NOT NULL
        REFERENCES source_approvals(approval_id) ON DELETE RESTRICT,
    rights_evidence_sha256 CHAR(64) NOT NULL
        CHECK (rights_evidence_sha256 ~ '^[0-9a-f]{64}$'),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (source_published_at <= retrieved_at),
    CHECK ((market_key = 'totals' AND line_point IS NOT NULL)
        OR (market_key <> 'totals' AND line_point IS NULL)),
    FOREIGN KEY (response_id, provider, source_id)
        REFERENCES provider_responses(id, provider, source_id) ON DELETE RESTRICT
);

CREATE INDEX odds_quote_fixture_market_time_idx
    ON odds_quote_observations(fixture_id, market_key, source_published_at DESC);
CREATE INDEX odds_quote_provider_event_idx
    ON odds_quote_observations(provider, source_id, provider_event_id, bookmaker_key, market_key);
CREATE INDEX odds_quote_response_idx
    ON odds_quote_observations(response_id, response_sha256);
CREATE INDEX odds_quote_rights_idx
    ON odds_quote_observations(rights_approval_id, recorded_at DESC);

-- Validate that the event crosswalk and request/response all describe the
-- same provider identity. These checks are repeated by the transactional writer.
CREATE OR REPLACE FUNCTION validate_odds_quote_observation_identity()
RETURNS trigger LANGUAGE plpgsql AS $func$
DECLARE
    mapped_fixture_id BIGINT;
    mapped_provider TEXT;
    mapped_source TEXT;
    mapped_event_id TEXT;
    mapped_entity_type TEXT;
    mapped_status TEXT;
    mapped_from TIMESTAMPTZ;
    mapped_until TIMESTAMPTZ;
    request_provider TEXT;
    request_source TEXT;
    request_response_id BIGINT;
    response_hash CHAR(64);
    response_provider TEXT;
    response_source TEXT;
BEGIN
    SELECT
        CASE WHEN ecv.canonical_entity_key ~ '^[0-9]+$'
             THEN ecv.canonical_entity_key::BIGINT ELSE NULL END,
        ecv.provider, ecv.source_id, ecv.provider_entity_id,
        ecv.entity_type, ecv.mapping_status, ecv.valid_from, ecv.valid_until
    INTO mapped_fixture_id, mapped_provider, mapped_source, mapped_event_id,
         mapped_entity_type, mapped_status, mapped_from, mapped_until
    FROM entity_crosswalk_versions ecv
    WHERE ecv.crosswalk_version_id = NEW.crosswalk_version_id;

    IF mapped_fixture_id IS NULL
       OR mapped_fixture_id <> NEW.fixture_id
       OR mapped_provider <> NEW.provider
       OR mapped_source <> NEW.source_id
       OR mapped_event_id <> NEW.provider_event_id
       OR mapped_entity_type <> 'FIXTURE'
       OR mapped_status <> 'RESOLVED'
       OR mapped_from > NEW.retrieved_at
       OR (mapped_until IS NOT NULL AND mapped_until <= NEW.retrieved_at) THEN
        RAISE EXCEPTION 'ODDS_QUOTE_FIXTURE_CROSSWALK_MISMATCH';
    END IF;

    SELECT provider, source_id, response_id
      INTO request_provider, request_source, request_response_id
    FROM provider_capture_requests
    WHERE capture_request_id = NEW.capture_request_id;

    IF request_provider <> NEW.provider OR request_source <> NEW.source_id
       OR request_response_id <> NEW.response_id THEN
        RAISE EXCEPTION 'ODDS_QUOTE_CAPTURE_REQUEST_MISMATCH';
    END IF;

    SELECT provider, source_id, response_sha256
      INTO response_provider, response_source, response_hash
    FROM provider_responses WHERE id = NEW.response_id;

    IF response_provider <> NEW.provider OR response_source <> NEW.source_id
       OR response_hash <> NEW.response_sha256 THEN
        RAISE EXCEPTION 'ODDS_QUOTE_RESPONSE_HASH_OR_PROVIDER_MISMATCH';
    END IF;

    RETURN NEW;
END;
$func$;

CREATE TRIGGER odds_quote_observation_identity_guard
    BEFORE INSERT ON odds_quote_observations
    FOR EACH ROW EXECUTE FUNCTION validate_odds_quote_observation_identity();

CREATE TRIGGER odds_quote_observations_append_only
    BEFORE UPDATE OR DELETE ON odds_quote_observations
    FOR EACH ROW EXECUTE FUNCTION reject_immutable_history_mutation();
