from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import psycopg
import pytest

from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.providers.odds_api_v4.orchestrator import (
    CaptureRequest, FixtureBoundary, build_manifest,
)


MIGRATION_7 = Path("db/migrations/0007_provider_capture_state_events.sql").read_text()
DATABASE_URL = os.environ["DATABASE_URL"]
NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def setup_db():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("""
            CREATE TABLE capture_manifests (
                capture_manifest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                manifest_key TEXT NOT NULL UNIQUE,
                manifest_sha256 CHAR(64) NOT NULL,
                capture_scope JSONB NOT NULL,
                requests_planned INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE provider_responses (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                request_id TEXT NOT NULL,
                request_params JSONB NOT NULL,
                http_status INTEGER NOT NULL,
                response_sha256 CHAR(64) NOT NULL,
                raw_body BYTEA NOT NULL,
                response_headers JSONB NOT NULL,
                quota_limit INTEGER,
                quota_remaining INTEGER,
                quota_reset_at TIMESTAMPTZ,
                fetched_at TIMESTAMPTZ NOT NULL,
                UNIQUE (id,provider,source_id)
            )
        """)
        conn.execute("""
            CREATE TABLE provider_capture_requests (
                capture_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                capture_manifest_id BIGINT NOT NULL REFERENCES capture_manifests(capture_manifest_id),
                provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                request_key TEXT NOT NULL,
                request_fingerprint CHAR(64) NOT NULL,
                attempt_number INTEGER NOT NULL,
                requested_at TIMESTAMPTZ NOT NULL,
                response_id BIGINT,
                outcome TEXT NOT NULL,
                error_code TEXT,
                UNIQUE(capture_manifest_id,request_key,attempt_number),
                FOREIGN KEY(response_id,provider,source_id)
                    REFERENCES provider_responses(id,provider,source_id),
                CHECK (
                    (outcome='RESPONSE' AND response_id IS NOT NULL)
                    OR (outcome<>'RESPONSE' AND response_id IS NULL)
                )
            )
        """)
        conn.execute("""
            CREATE FUNCTION reject_immutable_history_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'IMMUTABLE_HISTORY_MUTATION_REJECTED';
            END;
            $$
        """)
        conn.execute(MIGRATION_7)


def manifest():
    request = CaptureRequest(
        request_id="request-1", run_id="run-1", provider="the_odds_api",
        api_version="v4", endpoint_class="bulk_odds", sport_key="soccer_epl",
        competition_keys=("EPL",),
        fixture_boundaries=(FixtureBoundary(
            "fixture-1","event-1",NOW,NOW+timedelta(hours=2)
        ),),
        markets=("h2h",), regions=("uk",),
        prediction_use="derived_features", expected_terms_version="terms-2026-01",
        rights_evaluated_at=NOW, created_at=NOW, max_attempts=2, timeout_seconds=10,
    )
    return build_manifest(request)


def store():
    return PostgresHistoryStore(
        lambda: psycopg.connect(DATABASE_URL),
        allow_writes=True,
        expected_database="veltrix_reservation_test",
    )


def add_response(request_id, fetched_at):
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute("""
            INSERT INTO provider_responses(
                provider,source_id,endpoint,request_id,request_params,http_status,
                response_sha256,raw_body,response_headers,fetched_at
            ) VALUES (
                'the_odds_api','odds_api_v4','/v4/sports',%s,'{}'::jsonb,200,
                repeat('a',64),%s,'{}'::jsonb,%s
            ) RETURNING id
        """, (request_id,b'{"data":[]}',fetched_at)).fetchone()[0]


def test_manifest_persistence_is_idempotent_and_binds_canonical_scope():
    setup_db()
    m = manifest()
    writer = store()
    first = writer.persist_capture_manifest(m)
    assert writer.persist_capture_manifest(m) == first
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT manifest_sha256,capture_scope,requests_planned FROM capture_manifests WHERE capture_manifest_id=%s",
            (first,),
        ).fetchone()
        assert row[0] == m.manifest_sha256
        assert row[1]["request_fingerprint"] == m.request_fingerprint
        assert row[1]["markets"] == ["h2h"]
        assert row[2] == 1


def test_completed_response_attempt_persists_idempotently_and_rejects_conflict():
    setup_db()
    m = manifest()
    writer = store()
    manifest_id = writer.persist_capture_manifest(m)
    response_id = add_response(m.request_id,NOW+timedelta(seconds=2))
    args = dict(
        capture_manifest_id=manifest_id,manifest=m,
        endpoint="https://api.the-odds-api.com/v4/sports/soccer_epl/odds?regions=uk&markets=h2h",
        attempt_number=1,requested_at=NOW+timedelta(seconds=1),
        outcome="RESPONSE",response_id=response_id,
    )
    first = writer.persist_capture_request(**args)
    assert writer.persist_capture_request(**args) == first
    with pytest.raises(ValueError,match="CAPTURE_REQUEST_IDEMPOTENCY_CONFLICT"):
        writer.persist_capture_request(**{**args,"outcome":"TIMEOUT","response_id":None,"error_code":"timeout"})


def test_capture_attempt_requires_manifest_and_response_provenance():
    setup_db()
    m = manifest()
    writer = store()
    manifest_id = writer.persist_capture_manifest(m)
    endpoint="https://api.the-odds-api.com/v4/sports/soccer_epl/odds?regions=uk&markets=h2h"
    with pytest.raises(ValueError,match="CAPTURE_REQUEST_RESPONSE_ID_REQUIRED"):
        writer.persist_capture_request(
            capture_manifest_id=manifest_id,manifest=m,endpoint=endpoint,
            attempt_number=1,requested_at=NOW+timedelta(seconds=1),outcome="RESPONSE",
        )
    wrong_id = add_response("another-request",NOW+timedelta(seconds=2))
    with pytest.raises(ValueError,match="CAPTURE_REQUEST_RESPONSE_PROVENANCE_MISMATCH"):
        writer.persist_capture_request(
            capture_manifest_id=manifest_id,manifest=m,endpoint=endpoint,
            attempt_number=1,requested_at=NOW+timedelta(seconds=1),
            outcome="RESPONSE",response_id=wrong_id,
        )


def test_retry_attempt_is_blocked_until_previous_attempt_is_committed():
    setup_db()
    m = manifest()
    writer = store()
    manifest_id = writer.persist_capture_manifest(m)
    endpoint="https://api.the-odds-api.com/v4/sports/soccer_epl/odds?regions=uk&markets=h2h"
    writer.persist_capture_request(
        capture_manifest_id=manifest_id,manifest=m,endpoint=endpoint,
        attempt_number=1,requested_at=NOW+timedelta(seconds=1),
        outcome="TIMEOUT",error_code="timeout",
    )
    with pytest.raises(ValueError,match="CAPTURE_REQUEST_PREVIOUS_ATTEMPT_NOT_RECONCILED"):
        writer.persist_capture_request(
            capture_manifest_id=manifest_id,manifest=m,endpoint=endpoint,
            attempt_number=2,requested_at=NOW+timedelta(seconds=5),
            outcome="TIMEOUT",error_code="second-timeout",
        )

def test_concurrent_manifest_replays_return_one_canonical_record():
    setup_db()
    m = manifest()
    def persist_once(_):
        return store().persist_capture_manifest(m)

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(persist_once, range(8)))
    assert len(set(ids)) == 1
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute("SELECT COUNT(*) FROM capture_manifests").fetchone()[0] == 1
