from datetime import datetime, timezone
import os

import psycopg
import pytest

from tests.veltrix_v2.test_provider_evidence_capture import (
    approval, capture, capture_provider_result_evidence,
)
from veltrix_v2.data.evidence_persistence import persist_provider_evidence_report


DATABASE_URL = os.environ["DATABASE_URL"]
HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"


def setup_db():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("""
            CREATE TABLE source_approvals (
                approval_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                source_id TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE provider_responses (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                request_id TEXT NOT NULL,
                request_params JSONB NOT NULL DEFAULT '{}'::jsonb,
                http_status SMALLINT NOT NULL,
                response_sha256 CHAR(64) NOT NULL,
                raw_body BYTEA NOT NULL,
                response_headers JSONB NOT NULL DEFAULT '{}'::jsonb,
                fetched_at TIMESTAMPTZ NOT NULL,
                UNIQUE(provider, source_id, request_id, response_sha256),
                UNIQUE(id, provider, source_id)
            )
        """)
        conn.execute("""
            CREATE TABLE capture_manifests (
                capture_manifest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                manifest_key TEXT NOT NULL UNIQUE,
                manifest_sha256 CHAR(64) NOT NULL,
                capture_scope JSONB NOT NULL,
                requests_planned INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE capture_manifest_events (
                capture_manifest_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                capture_manifest_id BIGINT NOT NULL REFERENCES capture_manifests,
                status TEXT NOT NULL,
                event_at TIMESTAMPTZ NOT NULL,
                reason_code TEXT NOT NULL,
                evidence_sha256 CHAR(64),
                coverage_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE provider_capture_requests (
                capture_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                capture_manifest_id BIGINT NOT NULL REFERENCES capture_manifests,
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
                UNIQUE(capture_manifest_id, request_key, attempt_number),
                FOREIGN KEY(response_id, provider, source_id)
                    REFERENCES provider_responses(id, provider, source_id)
            )
        """)
        conn.execute("""
            CREATE TABLE source_observations (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                provider_entity_id TEXT NOT NULL,
                data_type TEXT NOT NULL,
                payload_sha256 CHAR(64) NOT NULL,
                retrieved_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL,
                source_event_time TIMESTAMPTZ,
                available_at TIMESTAMPTZ,
                availability_basis TEXT NOT NULL,
                rights_approval_id TEXT REFERENCES source_approvals(approval_id),
                provider_response_id BIGINT REFERENCES provider_responses(id),
                point_in_time_certifiable BOOLEAN NOT NULL DEFAULT FALSE,
                source_published_at TIMESTAMPTZ,
                source_effective_at TIMESTAMPTZ,
                recorded_at TIMESTAMPTZ,
                source_timestamp_raw TEXT,
                source_timestamp_basis TEXT NOT NULL DEFAULT 'unknown',
                UNIQUE(provider, endpoint, entity_type, provider_entity_id, payload_sha256)
            )
        """)
        a = approval()
        conn.execute(
            "INSERT INTO source_approvals(approval_id,provider,source_id) VALUES (%s,%s,%s)",
            (a.approval_id, a.provider, a.source_id),
        )


def persist(connection, report, rows):
    return persist_provider_evidence_report(
        connection, report, rows,
        write_enabled=True,
        environment="staging",
        database_name="veltrix_football_staging",
        host=HOST,
        role="neondb_owner",
    )


def test_evidence_persistence_writes_exact_raw_bytes_and_manifest_links_idempotently():
    setup_db()
    row = capture()
    report = capture_provider_result_evidence([row])
    with psycopg.connect(DATABASE_URL) as conn:
        first = persist(conn, report, [row])
    with psycopg.connect(DATABASE_URL) as conn:
        second = persist(conn, report, [row])
    assert first == second
    with psycopg.connect(DATABASE_URL) as conn:
        raw = conn.execute(
            "SELECT raw_body,response_sha256 FROM provider_responses"
        ).fetchone()
        assert raw[0] == row.raw_response
        assert raw[1] == report.observations[0].raw_response_sha256
        manifest = conn.execute(
            "SELECT manifest_sha256 FROM capture_manifests"
        ).fetchone()
        assert manifest[0] == report.manifest.manifest_sha256
        observation = conn.execute("""
            SELECT point_in_time_certifiable,payload->>'manifest_sha256',
                   payload->>'item_evidence_sha256',provider_response_id
            FROM source_observations
        """).fetchone()
        assert observation[0] is True
        assert observation[1] == report.manifest.manifest_sha256
        assert observation[2] == report.manifest.item_evidence_sha256[0]
        assert observation[3] == first["provider_response_id"]
        assert conn.execute("SELECT COUNT(*) FROM capture_manifest_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM provider_capture_requests").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0] == 1


def test_evidence_persistence_rolls_back_when_approval_is_missing():
    setup_db()
    row = capture()
    report = capture_provider_result_evidence([row])
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DELETE FROM source_approvals")
    with psycopg.connect(DATABASE_URL) as conn:
        with pytest.raises(ValueError, match="STAGING_SOURCE_APPROVAL_NOT_FOUND"):
            persist(conn, report, [row])
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute("SELECT COUNT(*) FROM capture_manifests").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM provider_responses").fetchone()[0] == 0
