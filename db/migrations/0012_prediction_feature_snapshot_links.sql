-- Append-only provenance bridge from each V2 PIT prediction to the exact
-- feature snapshot, latest eligible admission event and canonical/provider IDs.
-- Existing prediction events and feature snapshots are never updated.

CREATE TABLE prediction_feature_snapshot_links (
    ledger_id TEXT NOT NULL CHECK (length(btrim(ledger_id)) > 0),
    prediction_sequence BIGINT NOT NULL CHECK (prediction_sequence > 0),
    prediction_event_sha256 CHAR(64) NOT NULL CHECK (length(prediction_event_sha256) = 64),
    feature_snapshot_id BIGINT NOT NULL
        REFERENCES feature_snapshots(feature_snapshot_id) ON DELETE RESTRICT,
    eligibility_event_id BIGINT NOT NULL
        REFERENCES feature_snapshot_eligibility_events(eligibility_event_id) ON DELETE RESTRICT,
    canonical_competition_id BIGINT NOT NULL REFERENCES competitions(id) ON DELETE RESTRICT,
    canonical_home_team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
    canonical_away_team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
    provider_competition_id TEXT NOT NULL CHECK (length(btrim(provider_competition_id)) > 0),
    provider_home_team_id TEXT NOT NULL CHECK (length(btrim(provider_home_team_id)) > 0),
    provider_away_team_id TEXT NOT NULL CHECK (length(btrim(provider_away_team_id)) > 0),
    feature_set_sha256 CHAR(64) NOT NULL CHECK (length(feature_set_sha256) = 64),
    eligibility_evidence_sha256 CHAR(64) NOT NULL CHECK (length(eligibility_evidence_sha256) = 64),
    forecast_evidence_sha256 CHAR(64) NOT NULL CHECK (length(forecast_evidence_sha256) = 64),
    model_artifact_sha256 CHAR(64) NOT NULL CHECK (length(model_artifact_sha256) = 64),
    forecast_cutoff_at TIMESTAMPTZ NOT NULL,
    feature_snapshot_cutoff_at TIMESTAMPTZ NOT NULL,
    artifact_run_id BIGINT NOT NULL CHECK (artifact_run_id > 0),
    forecast_summary_sha256 CHAR(64) NOT NULL CHECK (length(forecast_summary_sha256) = 64),
    feature_admission_summary_sha256 CHAR(64) NOT NULL
        CHECK (length(feature_admission_summary_sha256) = 64),
    link_sha256 CHAR(64) NOT NULL CHECK (length(link_sha256) = 64),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ledger_id, prediction_sequence),
    UNIQUE (prediction_event_sha256),
    UNIQUE (feature_snapshot_id),
    UNIQUE (link_sha256),
    FOREIGN KEY (ledger_id, prediction_sequence)
        REFERENCES paper_ledger_events(ledger_id, sequence) ON DELETE RESTRICT,
    CHECK (canonical_home_team_id <> canonical_away_team_id),
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
    fixture fixtures%ROWTYPE;
    competition_provider_id TEXT;
    home_provider_id TEXT;
    away_provider_id TEXT;
BEGIN
    SELECT * INTO prediction
    FROM paper_ledger_events
    WHERE ledger_id = NEW.ledger_id AND sequence = NEW.prediction_sequence;

    IF NOT FOUND
       OR prediction.event_type <> 'PREDICTION'
       OR prediction.model_version <> 'veltrix-openplay-xg-poisson-v1'
       OR prediction.event_sha256 <> NEW.prediction_event_sha256
       OR prediction.payload->>'evidence_sha256' IS DISTINCT FROM NEW.forecast_evidence_sha256
       OR prediction.payload->>'evidence_class' IS DISTINCT FROM 'PIT_CERTIFIED'
    THEN
        RAISE EXCEPTION 'V2_PREDICTION_EVENT_EVIDENCE_LINK_INVALID';
    END IF;

    SELECT * INTO fixture
    FROM fixtures f
    WHERE f.provider = '5DollarFootballAPI'
      AND f.provider_fixture_id = split_part(prediction.fixture_id, ':', 2)
      AND prediction.fixture_id LIKE '5dollarfootballapi:%';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'V2_PREDICTION_CANONICAL_FIXTURE_NOT_RESOLVED';
    END IF;

    SELECT provider_competition_id INTO competition_provider_id
    FROM competitions WHERE id = fixture.competition_id AND provider = fixture.provider;
    SELECT provider_team_id INTO home_provider_id
    FROM teams WHERE id = fixture.home_team_id AND provider = fixture.provider;
    SELECT provider_team_id INTO away_provider_id
    FROM teams WHERE id = fixture.away_team_id AND provider = fixture.provider;

    IF fixture.competition_id IS DISTINCT FROM NEW.canonical_competition_id
       OR fixture.home_team_id IS DISTINCT FROM NEW.canonical_home_team_id
       OR fixture.away_team_id IS DISTINCT FROM NEW.canonical_away_team_id
       OR competition_provider_id IS DISTINCT FROM NEW.provider_competition_id
       OR home_provider_id IS DISTINCT FROM NEW.provider_home_team_id
       OR away_provider_id IS DISTINCT FROM NEW.provider_away_team_id
       OR prediction.payload->>'competition_id' IS DISTINCT FROM NEW.canonical_competition_id::text
       OR prediction.payload->>'home_team_id' IS DISTINCT FROM NEW.canonical_home_team_id::text
       OR prediction.payload->>'away_team_id' IS DISTINCT FROM NEW.canonical_away_team_id::text
       OR prediction.payload->>'target_provider_competition_id' IS DISTINCT FROM NEW.provider_competition_id
    THEN
        RAISE EXCEPTION 'V2_PREDICTION_CANONICAL_OR_PROVIDER_IDENTITY_MISMATCH';
    END IF;

    SELECT * INTO snapshot
    FROM feature_snapshots WHERE feature_snapshot_id = NEW.feature_snapshot_id;

    IF NOT FOUND
       OR snapshot.fixture_id <> fixture.id
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
       OR eligibility.recorded_at > NEW.forecast_cutoff_at
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
