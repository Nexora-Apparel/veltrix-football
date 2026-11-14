from datetime import datetime, timezone
import os

import psycopg
import pytest

from tests.veltrix_v2.test_provider_evidence_capture import (
    approval, capture, capture_provider_result_evidence,
)
from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval
from veltrix_v2.data.evidence_persistence import (
    build_fixture_snapshot_manifest,
    persist_fixture_snapshot_response,
    persist_provider_evidence_report,
)


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
                   payload->>'item_evidence_sha256',provider_response_id,
                   payload->>'rights_approved',payload->>'rights_evaluated_at',
                   payload->>'rights_evidence_sha256'
            FROM source_observations
        """).fetchone()
        assert observation[0] is True
        assert observation[1] == report.manifest.manifest_sha256
        assert observation[2] == report.manifest.item_evidence_sha256[0]
        assert observation[3] == first["provider_response_id"]
        assert observation[4] == "true"
        assert observation[5] == report.observations[0].recorded_at
        assert observation[6] == report.observations[0].rights_evidence_sha256
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


SNAPSHOT_NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
SNAPSHOT_RAW = b'{"success":1,"data":[{"fixture_id":"f-1"},{"fixture_id":"f-2"}]}'


def snapshot_approval():
    return SourceApproval(
        approval_id="approval-5dollar-community-fixture-result-2026-11",
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        competition_scope="3118717965",
        data_type="fixture_result",
        status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset({
            DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE, DataUsePurpose.CACHE
        }),
        commercial_use_allowed=True,
        terms_url="https://provider.invalid/terms",
        terms_version="2026-11",
        evidence_uri="https://evidence.invalid/approval",
        evidence_sha256="a" * 64,
        rights_basis="TERMS",
        reviewed_at_utc=SNAPSHOT_NOW - timedelta(days=1),
        reviewer_id="reviewer-1",
        valid_from_utc=SNAPSHOT_NOW - timedelta(days=2),
    )


def snapshot_args():
    approval_record = snapshot_approval()
    return {
        "provider": "5DollarFootballAPI",
        "source_id": "5dollarfootballapi",
        "endpoint": "/v1/leagues/3118717965/fixtures",
        "request_id": "run-123-3118717965-scheduled-1",
        "request_params": {
            "start_time": 1794657600, "end_time": 1795867200,
            "status": "scheduled", "order": "asc", "page": 1, "per_page": 100,
        },
        "requested_at": SNAPSHOT_NOW - timedelta(seconds=3),
        "retrieved_at": SNAPSHOT_NOW - timedelta(seconds=2),
        "recorded_at": SNAPSHOT_NOW,
        "raw_response": SNAPSHOT_RAW,
        "response_headers": {
            "Content-Type": "application/json",
            "X-RateLimit-Remaining": "57",
            "Authorization": "must-not-be-stored",
        },
        "competition_id": "3118717965",
        "fixture_count": 2,
        "rights_approval": approval_record,
    }


def test_fixture_snapshot_manifest_is_deterministic_and_timestamp_bound():
    args = snapshot_args()
    first = build_fixture_snapshot_manifest(**{
        key: value for key, value in args.items()
        if key not in {"response_headers", "rights_approval"}
    }, rights_approval_id=args["rights_approval"].approval_id)
    second = build_fixture_snapshot_manifest(**{
        key: value for key, value in args.items()
        if key not in {"response_headers", "rights_approval"}
    }, rights_approval_id=args["rights_approval"].approval_id)
    assert first == second
    assert first["response_sha256"] == __import__("hashlib").sha256(SNAPSHOT_RAW).hexdigest()


def test_fixture_snapshot_persistence_retains_raw_target_response_and_manifest_idempotently():
    setup_db()
    args = snapshot_args()
    with psycopg.connect(DATABASE_URL) as connection:
        first = persist_fixture_snapshot_response(
            connection, **args,
            write_enabled=True, environment="staging",
            database_name="veltrix_football_staging", host=HOST,
            role="neondb_owner",
        )
    with psycopg.connect(DATABASE_URL) as connection:
        second = persist_fixture_snapshot_response(
            connection, **args,
            write_enabled=True, environment="staging",
            database_name="veltrix_football_staging", host=HOST,
            role="neondb_owner",
        )
    assert first == second
    with psycopg.connect(DATABASE_URL) as connection:
        response = connection.execute(
            "SELECT raw_body,response_sha256,request_params,response_headers FROM provider_responses"
        ).fetchone()
        assert response[0] == SNAPSHOT_RAW
        assert response[1] == first["response_sha256"]
        assert response[2]["status"] == "scheduled"
        assert "authorization" not in response[3]
        manifest = connection.execute(
            "SELECT manifest_sha256,capture_scope FROM capture_manifests"
        ).fetchone()
        assert manifest[0] == first["manifest_sha256"]
        assert manifest[1]["fixture_count"] == 2
        assert connection.execute("SELECT COUNT(*) FROM capture_manifest_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM provider_capture_requests").fetchone()[0] == 1


def test_fixture_snapshot_persistence_rejects_wrong_scope_and_disabled_write():
    setup_db()
    args = snapshot_args()
    wrong_scope = snapshot_approval()
    wrong_scope = SourceApproval(
        approval_id=wrong_scope.approval_id,
        provider=wrong_scope.provider,
        source_id=wrong_scope.source_id,
        competition_scope="different-competition",
        data_type=wrong_scope.data_type,
        status=wrong_scope.status,
        permitted_uses=wrong_scope.permitted_uses,
        commercial_use_allowed=wrong_scope.commercial_use_allowed,
        terms_url=wrong_scope.terms_url,
        terms_version=wrong_scope.terms_version,
        evidence_uri=wrong_scope.evidence_uri,
        evidence_sha256=wrong_scope.evidence_sha256,
        rights_basis=wrong_scope.rights_basis,
        reviewed_at_utc=wrong_scope.reviewed_at_utc,
        reviewer_id=wrong_scope.reviewer_id,
        valid_from_utc=wrong_scope.valid_from_utc,
    )
    args["rights_approval"] = wrong_scope
    with psycopg.connect(DATABASE_URL) as connection:
        with pytest.raises(PermissionError, match="FIXTURE_SNAPSHOT_SOURCE_RIGHTS_SCOPE_INVALID"):
            persist_fixture_snapshot_response(
                connection, **args,
                write_enabled=True, environment="staging",
                database_name="veltrix_football_staging", host=HOST,
                role="neondb_owner",
            )
    args["rights_approval"] = snapshot_approval()
    with psycopg.connect(DATABASE_URL) as connection:
        with pytest.raises(PermissionError, match="FIXTURE_SNAPSHOT_PERSISTENCE_WRITE_GUARD_DISABLED"):
            persist_fixture_snapshot_response(
                connection, **args,
                write_enabled=False, environment="staging",
                database_name="veltrix_football_staging", host=HOST,
                role="neondb_owner",
            )
