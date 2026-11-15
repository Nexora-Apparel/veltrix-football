-- Staging-only, idempotent backfill of 5Dollar's latest pre-match 1X2 stage.
-- Source run: 43768424133. This is NOT a final closing-odds observation.
-- For scheduled fixtures the provider's "closing" field is the latest pre-match
-- price so far; no provider update timestamp is included in this fixture response.
-- Preserve the collector observation time, but fail closed for PIT certification.

WITH raw AS (
    SELECT
        pr.*,
        convert_from(pr.raw_body, 'UTF8')::jsonb->'data' AS fixture
    FROM provider_responses pr
    WHERE pr.request_id LIKE '%43768424133%'
      AND pr.provider = '5DollarFootballAPI'
      AND pr.source_id = '5dollarfootballapi'
      AND pr.http_status = 200
),
candidates AS (
    SELECT
        pr.id AS provider_response_id,
        pr.provider,
        pr.source_id,
        pr.endpoint,
        pr.response_sha256,
        pr.request_id,
        pr.fetched_at,
        pr.fixture,
        pr.fixture->>'id' AS provider_fixture_id,
        (pr.fixture->>'kickoff_utc')::timestamptz AS kickoff_at,
        pr.fixture->'odds'->'1x2'->'closing' AS closing,
        e.fixture_id AS ledger_fixture_id,
        e.event_sha256 AS source_prediction_event_sha256,
        e.model_version AS source_prediction_model_version,
        e.payload AS prediction_payload,
        open.id AS opening_quote_observation_id,
        open.source_timestamp_raw AS opening_source_timestamp_raw,
        open.available_at AS opening_quote_available_at,
        open.payload_sha256 AS opening_quote_payload_sha256,
        open.payload AS opening_quote_payload,
        ht.id AS canonical_home_team_id,
        at.id AS canonical_away_team_id,
        comp.id AS canonical_competition_id,
        hx.crosswalk_version_id AS home_team_crosswalk_version_id,
        hx.evidence_observation_id AS home_team_evidence_observation_id,
        ax.crosswalk_version_id AS away_team_crosswalk_version_id,
        ax.evidence_observation_id AS away_team_evidence_observation_id,
        cx.crosswalk_version_id AS competition_crosswalk_version_id,
        cx.evidence_observation_id AS competition_evidence_observation_id
    FROM raw pr
    JOIN paper_ledger_events e
      ON e.payload->>'target_source_fixture_id' = pr.fixture->>'id'
     AND e.ledger_id = 'veltrix-v2-prospective-observed'
     AND e.event_type = 'SHADOW_PREDICTION'
     AND e.payload->>'target_provider' = '5DollarFootballAPI'
     AND e.payload->>'target_source_id' = '5dollarfootballapi'
     AND e.payload->>'evidence_class' = 'PROSPECTIVE_OBSERVED_ONLY'
     AND e.payload->>'point_in_time_certifiable' = 'false'
    JOIN source_observations open
      ON open.provider_response_id = pr.id
     AND open.provider = pr.provider
     AND open.source_id = pr.source_id
     AND open.entity_type = 'odds_opening_quote'
     AND open.provider_entity_id = pr.fixture->>'id'
    JOIN teams ht
      ON ht.id = (e.payload->>'home_team_id')::bigint
     AND ht.provider = '5DollarFootballAPI'
    JOIN teams at
      ON at.id = (e.payload->>'away_team_id')::bigint
     AND at.provider = '5DollarFootballAPI'
    JOIN competitions comp
      ON comp.id = (e.payload->>'competition_id')::bigint
     AND comp.provider = '5DollarFootballAPI'
     AND comp.provider_competition_id = e.payload->>'target_provider_competition_id'
    JOIN entity_crosswalk_versions hx
      ON hx.entity_type = 'TEAM'
     AND hx.provider = '5DollarFootballAPI'
     AND hx.source_id = '5dollarfootballapi'
     AND hx.provider_entity_id = ht.provider_team_id
     AND hx.canonical_entity_key = ht.id::text
     AND hx.mapping_status = 'RESOLVED'
     AND hx.valid_from <= now()
     AND (hx.valid_until IS NULL OR hx.valid_until > now())
    JOIN entity_crosswalk_versions ax
      ON ax.entity_type = 'TEAM'
     AND ax.provider = '5DollarFootballAPI'
     AND ax.source_id = '5dollarfootballapi'
     AND ax.provider_entity_id = at.provider_team_id
     AND ax.canonical_entity_key = at.id::text
     AND ax.mapping_status = 'RESOLVED'
     AND ax.valid_from <= now()
     AND (ax.valid_until IS NULL OR ax.valid_until > now())
    JOIN entity_crosswalk_versions cx
      ON cx.entity_type = 'COMPETITION'
     AND cx.provider = '5DollarFootballAPI'
     AND cx.source_id = '5dollarfootballapi'
     AND cx.provider_entity_id = comp.provider_competition_id
     AND cx.canonical_entity_key = comp.id::text
     AND cx.mapping_status = 'RESOLVED'
     AND cx.valid_from <= now()
     AND (cx.valid_until IS NULL OR cx.valid_until > now())
    WHERE pr.fixture->>'status' = 'scheduled'
      AND pr.fixture->'teams'->'home'->>'id' = ht.provider_team_id
      AND pr.fixture->'teams'->'away'->>'id' = at.provider_team_id
      AND pr.fixture->'league'->>'id' = comp.provider_competition_id
      AND (pr.fixture->>'kickoff_utc')::timestamptz = (e.payload->>'kickoff_at')::timestamptz
      AND (pr.fixture->>'kickoff_utc')::timestamptz > pr.fetched_at
      AND pr.fixture->'odds'->'1x2'->'closing'->>'home' IS NOT NULL
      AND pr.fixture->'odds'->'1x2'->'closing'->>'draw' IS NOT NULL
      AND pr.fixture->'odds'->'1x2'->'closing'->>'away' IS NOT NULL
      AND NOT (pr.fixture->'odds'->'1x2'->'closing' ? 'updated_at')
      AND NOT EXISTS (
          SELECT 1
          FROM source_observations latest
          WHERE latest.provider = pr.provider
            AND latest.endpoint = pr.endpoint
            AND latest.entity_type = 'odds_latest_prematch_snapshot'
            AND latest.provider_entity_id = pr.fixture->>'id'
            AND latest.provider_response_id = pr.id
      )
),
payloads AS (
    SELECT
        c.*,
        jsonb_build_object(
            'provider_fixture_id', c.provider_fixture_id,
            'canonical_fixture_id', NULL,
            'prospective_ledger_fixture_id', c.ledger_fixture_id,
            'canonical_home_team_id', c.canonical_home_team_id,
            'canonical_away_team_id', c.canonical_away_team_id,
            'canonical_competition_id', c.canonical_competition_id,
            'kickoff_at', c.kickoff_at,
            'market', '1x2',
            'bookmaker', 'bet365',
            'quote_stage', 'LATEST_PREMATCH_PRICE_AS_OF_RETRIEVAL',
            'provider_field', 'odds.1x2.closing',
            'provider_stage_semantics',
                'For a scheduled fixture, closing is the latest pre-match price so far; it is not the final close until kickoff.',
            'provider_update_timestamp_available', false,
            'provider_updated_at', NULL,
            'collector_observed_at', c.fetched_at,
            'availability_basis', 'collector_first_observed_v1',
            'source_timestamp_basis', 'unknown',
            'point_in_time_certifiable', false,
            'home', c.closing->'home',
            'draw', c.closing->'draw',
            'away', c.closing->'away',
            'opening_quote_observation_id', c.opening_quote_observation_id,
            'opening_quote_source_timestamp_raw', c.opening_source_timestamp_raw,
            'opening_quote_available_at', c.opening_quote_available_at,
            'opening_quote_payload_sha256', c.opening_quote_payload_sha256,
            'source_prediction_event_sha256', c.source_prediction_event_sha256,
            'source_prediction_model_version', c.source_prediction_model_version,
            'source_prediction_evidence_class', c.prediction_payload->>'evidence_class',
            'source_prediction_point_in_time_certifiable', false,
            'source_prediction_cutoff_at', c.prediction_payload->>'prediction_cutoff_at',
            'captured_after_associated_prediction_cutoff',
                c.fetched_at > (c.prediction_payload->>'prediction_cutoff_at')::timestamptz,
            'market_selection_eligible', false,
            'clv_eligible', false,
            'final_close_observed', false,
            'original_target_response_sha256', c.prediction_payload->>'target_response_sha256',
            'original_target_manifest_sha256', c.prediction_payload->>'target_capture_manifest_sha256',
            'current_fixture_snapshot_response_sha256',
                c.opening_quote_payload->>'current_fixture_snapshot_response_sha256',
            'current_fixture_snapshot_request_id',
                c.opening_quote_payload->>'current_fixture_snapshot_request_id',
            'home_team_crosswalk_version_id', c.home_team_crosswalk_version_id,
            'home_team_evidence_observation_id', c.home_team_evidence_observation_id,
            'away_team_crosswalk_version_id', c.away_team_crosswalk_version_id,
            'away_team_evidence_observation_id', c.away_team_evidence_observation_id,
            'competition_crosswalk_version_id', c.competition_crosswalk_version_id,
            'competition_evidence_observation_id', c.competition_evidence_observation_id,
            'provider_response_id', c.provider_response_id,
            'provider_response_sha256', c.response_sha256,
            'provider_request_id', c.request_id
        ) AS observation_payload
    FROM candidates c
),
prepared AS (
    SELECT
        p.*,
        encode(sha256(convert_to(p.observation_payload::text, 'UTF8')), 'hex') AS observation_payload_sha256
    FROM payloads p
)
INSERT INTO source_observations (
    provider, endpoint, entity_type, provider_entity_id, payload_sha256,
    retrieved_at, payload, source_id, data_type, season_key, source_event_time,
    available_at, availability_basis, rights_approval_id, schema_version,
    provider_response_id, point_in_time_certifiable, source_published_at,
    source_effective_at, recorded_at, source_timestamp_raw, source_timestamp_basis
)
SELECT
    provider,
    endpoint,
    'odds_latest_prematch_snapshot',
    provider_fixture_id,
    observation_payload_sha256,
    fetched_at,
    observation_payload,
    source_id,
    'odds_quote',
    NULL,
    kickoff_at,
    fetched_at,
    'collector_first_observed_v1',
    'approval-5dollar-community-odds-quote-noncommercial-2026-11-15',
    '5dollar-latest-prematch-v1',
    provider_response_id,
    false,
    NULL,
    NULL,
    now(),
    NULL,
    'unknown'
FROM prepared
ON CONFLICT (provider, endpoint, entity_type, provider_entity_id, payload_sha256) DO NOTHING
RETURNING id, provider_entity_id, provider_response_id, retrieved_at, payload_sha256;
