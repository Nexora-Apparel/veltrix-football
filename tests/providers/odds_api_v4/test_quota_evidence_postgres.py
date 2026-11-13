from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import psycopg
import pytest


MIGRATION_5 = Path("db/migrations/0005_provider_credit_reservation_ledger.sql").read_text()
MIGRATION_6 = Path("db/migrations/0006_provider_quota_evidence.sql").read_text()
DATABASE_URL = os.environ["DATABASE_URL"]


def setup_db():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("""
            CREATE TABLE capture_manifests (
                capture_manifest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
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
                UNIQUE (id, provider, source_id),
                UNIQUE (provider, source_id, request_id, response_sha256)
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
        conn.execute(MIGRATION_5)
        conn.execute(MIGRATION_6)
        manifest = conn.execute(
            "INSERT INTO capture_manifests DEFAULT VALUES RETURNING capture_manifest_id"
        ).fetchone()[0]
        now = datetime.now(timezone.utc)
        budget = conn.execute("""
            INSERT INTO provider_credit_budget_snapshots (
                provider, provider_account_ref, billing_period_start, billing_period_end,
                monthly_allowance, provider_remaining, monthly_hard_cap, per_run_hard_cap,
                request_count_cap, observed_at, valid_until, evidence_uri, evidence_sha256,
                terms_version, terms_acceptance_evidence_uri,
                terms_acceptance_evidence_sha256, rights_approval_ids
            ) VALUES (
                'the_odds_api','account-1',DATE '2026-11-01',DATE '2026-12-01',
                100,100,100,50,100,%s,%s,'test://quota',repeat('a',64),
                'terms-v1','test://terms',repeat('b',64),'["approval-1"]'::jsonb
            ) RETURNING budget_snapshot_id
        """, (now - timedelta(seconds=1), now + timedelta(minutes=10))).fetchone()[0]
        reservation_event_id = conn.execute("""
            SELECT reserve_provider_credits(
                'reservation-1','the_odds_api','account-1',
                DATE '2026-11-01',DATE '2026-12-01','run-1',%s,
                'request-1',1,%s,5,%s,'test',%s,%s,%s
            )
        """, (manifest, "c" * 64, budget, now, "d" * 64, "e" * 64)).fetchone()[0]
    return now, reservation_event_id


def add_response_and_snapshot(conn, *, now, request_id, used, remaining, last,
                              account="account-1", raw_headers=None):
    response_id = conn.execute("""
        INSERT INTO provider_responses(
            provider,source_id,endpoint,request_id,request_params,http_status,
            response_sha256,raw_body,response_headers,fetched_at
        )
        VALUES (
            'the_odds_api','odds_api_v4','/v4/sports',%s,'{}'::jsonb,200,
            %s,%s,'{}'::jsonb,%s
        )
        RETURNING id
    """, (request_id, "f" * 64, request_id.encode(), now)).fetchone()[0]
    headers = raw_headers or {
        "x-requests-used": str(used),
        "x-requests-remaining": str(remaining),
        "x-requests-last": str(last),
    }
    snapshot_id = conn.execute("""
        INSERT INTO provider_quota_snapshots (
            provider,source_id,provider_account_ref,billing_period_start,billing_period_end,
            provider_response_id,observed_at,raw_quota_headers,
            requests_used,requests_remaining,requests_last,evidence_sha256
        ) VALUES (
            'the_odds_api','odds_api_v4',%s,DATE '2026-11-01',DATE '2026-12-01',
            %s,%s,%s::jsonb,%s,%s,%s,%s
        ) RETURNING quota_snapshot_id
    """, (
        account, response_id, now, __import__("json").dumps(headers),
        used, remaining, last, "1" * 64,
    )).fetchone()[0]
    return snapshot_id


def add_event(conn, *, reservation_event_id, before_id, after_id, status,
              actual=None, releasable=None, sequence=1, previous=None,
              event_hash="2" * 64, now):
    return conn.execute("""
        INSERT INTO provider_quota_reconciliation_events (
            reservation_event_id,reservation_key,event_sequence,provider,source_id,
            provider_account_ref,billing_period_start,billing_period_end,
            before_snapshot_id,after_snapshot_id,status,actual_credits,releasable_credits,
            reason_code,evidence_sha256,previous_event_sha256,event_sha256,actor,occurred_at
        ) VALUES (
            %s,'reservation-1',%s,'the_odds_api','odds_api_v4','account-1',
            DATE '2026-11-01',DATE '2026-12-01',%s,%s,%s,%s,%s,
            'TEST_EVIDENCE',repeat('3',64),%s,%s,'test',%s
        ) RETURNING quota_reconciliation_event_id
    """, (reservation_event_id, sequence, before_id, after_id, status,
          actual, releasable, previous, event_hash, now)).fetchone()[0]


def test_quota_snapshots_link_exact_response_and_reconciliation():
    now, reservation = setup_db()
    with psycopg.connect(DATABASE_URL) as conn:
        before = add_response_and_snapshot(
            conn, now=now, request_id="before", used=100, remaining=900, last=1
        )
        after = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=5), request_id="after",
            used=103, remaining=897, last=3
        )
        add_event(conn, reservation_event_id=reservation, before_id=before,
                  after_id=after, status="RECONCILED", actual=3, releasable=2,
                  now=now + timedelta(seconds=6))
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM provider_quota_reconciliation_events"
        ).fetchone()[0]
        assert count == 1


def test_unknown_can_be_resolved_later_but_terminal_state_cannot_be_rewritten():
    now, reservation = setup_db()
    with psycopg.connect(DATABASE_URL) as conn:
        before = add_response_and_snapshot(
            conn, now=now, request_id="before", used=None, remaining=900, last=None
        )
        uncertain = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=5), request_id="uncertain",
            used=None, remaining=897, last=None
        )
        first = add_event(conn, reservation_event_id=reservation, before_id=before,
                          after_id=uncertain, status="UNKNOWN",
                          now=now + timedelta(seconds=6))
        known_before = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=8), request_id="known-before",
            used=100, remaining=900, last=0
        )
        after = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=10), request_id="reconciled",
            used=103, remaining=897, last=3
        )
        add_event(conn, reservation_event_id=reservation, before_id=known_before,
                  after_id=after, status="RECONCILED", actual=3, releasable=2,
                  sequence=2, previous="2" * 64, event_hash="4" * 64,
                  now=now + timedelta(seconds=11))
        conn.commit()
        assert first is not None
        with pytest.raises(psycopg.Error, match="EVENT_CHAIN_INVALID"):
            add_event(conn, reservation_event_id=reservation, before_id=before,
                      after_id=after, status="UNKNOWN", sequence=3,
                      previous="4" * 64, event_hash="5" * 64,
                      now=now + timedelta(seconds=12))
        conn.rollback()


def test_overrun_and_cross_account_or_raw_header_injection_are_rejected():
    now, reservation = setup_db()
    with psycopg.connect(DATABASE_URL) as conn:
        before = add_response_and_snapshot(
            conn, now=now, request_id="before", used=100, remaining=900, last=1
        )
        over = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=5), request_id="over",
            used=106, remaining=894, last=6
        )
        add_event(conn, reservation_event_id=reservation, before_id=before,
                  after_id=over, status="OVERRUN", actual=6, releasable=0,
                  now=now + timedelta(seconds=6))
        conn.commit()
        wrong_account = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=8), request_id="wrong-account",
            used=110, remaining=890, last=4, account="other"
        )
        with pytest.raises(psycopg.Error, match="SNAPSHOT_SCOPE_OR_TIME_INVALID"):
            add_event(conn, reservation_event_id=reservation, before_id=before,
                      after_id=wrong_account, status="UNKNOWN",
                      now=now + timedelta(seconds=9))
        conn.rollback()

    now, reservation = setup_db()
    with psycopg.connect(DATABASE_URL) as conn:
        with pytest.raises(psycopg.Error, match="check constraint"):
            add_response_and_snapshot(
                conn, now=now, request_id="bad-header", used=1, remaining=99, last=1,
                raw_headers={"x-api-key": "must-not-be-stored"}
            )
        conn.rollback()


def test_snapshot_and_reconciliation_evidence_are_append_only():
    now, reservation = setup_db()
    with psycopg.connect(DATABASE_URL) as conn:
        before = add_response_and_snapshot(
            conn, now=now, request_id="before", used=100, remaining=900, last=1
        )
        after = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=5), request_id="after",
            used=103, remaining=897, last=3
        )
        add_event(conn, reservation_event_id=reservation, before_id=before,
                  after_id=after, status="RECONCILED", actual=3, releasable=2,
                  now=now + timedelta(seconds=6))
        conn.commit()
        with pytest.raises(psycopg.Error, match="IMMUTABLE_HISTORY_MUTATION_REJECTED"):
            conn.execute("UPDATE provider_quota_snapshots SET requests_used=999")
        conn.rollback()

def test_reconciled_actual_must_match_provider_last_request_cost():
    now, reservation = setup_db()
    with psycopg.connect(DATABASE_URL) as conn:
        before = add_response_and_snapshot(
            conn, now=now, request_id="before", used=100, remaining=900, last=1
        )
        after = add_response_and_snapshot(
            conn, now=now + timedelta(seconds=5), request_id="after",
            used=103, remaining=897, last=3
        )
        with pytest.raises(psycopg.Error, match="ACTUAL_CREDITS_DO_NOT_MATCH_LAST_REQUEST"):
            add_event(conn, reservation_event_id=reservation, before_id=before,
                      after_id=after, status="RECONCILED", actual=4, releasable=1,
                      now=now + timedelta(seconds=6))
        conn.rollback()


def test_quota_header_values_must_remain_raw_strings():
    now, _ = setup_db()
    with psycopg.connect(DATABASE_URL) as conn:
        with pytest.raises(psycopg.Error, match="check constraint"):
            add_response_and_snapshot(
                conn, now=now, request_id="numeric-header",
                used=100, remaining=900, last=0,
                raw_headers={
                    "x-requests-used": 100,
                    "x-requests-remaining": "900",
                    "x-requests-last": "0",
                }
            )
        conn.rollback()

