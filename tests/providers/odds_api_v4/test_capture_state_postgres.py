from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import psycopg
import pytest

from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.providers.odds_api_v4.state_machine import advance_state


MIGRATION_7 = Path("db/migrations/0007_provider_capture_state_events.sql").read_text()
DATABASE_URL = os.environ["DATABASE_URL"]
NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def setup_db():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("""
            CREATE TABLE provider_capture_requests (
                capture_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                request_key TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                UNIQUE(request_key, attempt_number)
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
        request_id = conn.execute("""
            INSERT INTO provider_capture_requests(request_key,attempt_number)
            VALUES ('request-1',1) RETURNING capture_request_id
        """).fetchone()[0]
    return request_id


def event(*, current, target, sequence, previous=None, at=None, request="request-1"):
    result = advance_state(
        request_id=request,
        current_state=current,
        target_state=target,
        sequence=sequence,
        occurred_at=at or NOW + timedelta(seconds=sequence),
        actor="test",
        reason_code=f"TEST_{target}",
        evidence_sha256="a" * 64,
        previous_event=previous,
    )
    assert result.allowed, result.reason_code
    return result.event


def store():
    return PostgresHistoryStore(
        lambda: psycopg.connect(DATABASE_URL),
        allow_writes=True,
        expected_database="veltrix_reservation_test",
    )


def test_state_events_persist_in_order_and_idempotent_replay_returns_same_id():
    request_id = setup_db()
    first = event(current="PLANNED", target="PREFLIGHT_APPROVED", sequence=1)
    second = event(
        current="PREFLIGHT_APPROVED", target="CREDIT_RESERVED",
        sequence=2, previous=first,
    )
    writer = store()
    first_id = writer.append_capture_state_event(request_id, first)
    assert writer.append_capture_state_event(request_id, first) == first_id
    second_id = writer.append_capture_state_event(request_id, second)
    assert second_id > first_id
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute("""
            SELECT event_sequence,from_state,to_state,previous_event_sha256,event_sha256
            FROM provider_capture_state_events
            ORDER BY event_sequence
        """).fetchall()
        assert rows == [
            (1, "PLANNED", "PREFLIGHT_APPROVED", None, first.event_sha256),
            (2, "PREFLIGHT_APPROVED", "CREDIT_RESERVED",
             first.event_sha256, second.event_sha256),
        ]


def test_database_rejects_out_of_order_event_then_accepts_correct_chain():
    request_id = setup_db()
    first = event(current="PLANNED", target="PREFLIGHT_APPROVED", sequence=1)
    second = event(
        current="PREFLIGHT_APPROVED", target="CREDIT_RESERVED",
        sequence=2, previous=first,
    )
    writer = store()
    with pytest.raises(psycopg.Error, match="CAPTURE_STATE_INITIAL_EVENT_INVALID"):
        writer.append_capture_state_event(request_id, second)
    writer.append_capture_state_event(request_id, first)
    writer.append_capture_state_event(request_id, second)


def test_terminal_state_and_illegal_transition_are_rejected():
    request_id = setup_db()
    first = event(current="PLANNED", target="BLOCKED", sequence=1)
    writer = store()
    writer.append_capture_state_event(request_id, first)
    attempted = advance_state(
        request_id="request-1", current_state="BLOCKED",
        target_state="PREFLIGHT_APPROVED", sequence=2,
        occurred_at=NOW + timedelta(seconds=3), actor="test",
        reason_code="ILLEGAL", evidence_sha256="b" * 64,
        previous_event=first,
    )
    assert not attempted.allowed
    assert attempted.reason_code == "TRANSITION_NOT_ALLOWED"


def test_event_hash_and_request_identity_are_verified_before_database_write():
    from dataclasses import replace

    request_id = setup_db()
    first = event(current="PLANNED", target="PREFLIGHT_APPROVED", sequence=1)
    writer = store()
    with pytest.raises(ValueError, match="CAPTURE_STATE_EVENT_HASH_INVALID"):
        writer.append_capture_state_event(request_id, replace(first, reason_code="tampered"))
    wrong_request = event(
        current="PLANNED", target="PREFLIGHT_APPROVED", sequence=1,
        request="different-request",
    )
    with pytest.raises(ValueError, match="CAPTURE_STATE_REQUEST_IDENTITY_MISMATCH"):
        writer.append_capture_state_event(request_id, wrong_request)
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_capture_state_events").fetchone()[0] == 0


def test_capture_state_event_history_is_append_only():
    request_id = setup_db()
    first = event(current="PLANNED", target="PREFLIGHT_APPROVED", sequence=1)
    store().append_capture_state_event(request_id, first)
    with psycopg.connect(DATABASE_URL) as conn:
        with pytest.raises(psycopg.Error, match="IMMUTABLE_HISTORY_MUTATION_REJECTED"):
            conn.execute(
                "UPDATE provider_capture_state_events SET reason_code='rewritten'"
            )
        conn.rollback()
        with pytest.raises(psycopg.Error, match="IMMUTABLE_HISTORY_MUTATION_REJECTED"):
            conn.execute("DELETE FROM provider_capture_state_events")
        conn.rollback()

def test_concurrent_exact_event_replays_serialize_to_one_ledger_row():
    request_id = setup_db()
    first = event(current="PLANNED", target="PREFLIGHT_APPROVED", sequence=1)
    def append_once(_):
        return store().append_capture_state_event(request_id, first)

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(append_once, range(8)))
    assert len(set(ids)) == 1
    with psycopg.connect(DATABASE_URL) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM provider_capture_state_events"
        ).fetchone()[0] == 1
