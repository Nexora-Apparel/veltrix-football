from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import psycopg
import pytest


MIGRATION = Path("db/migrations/0005_provider_credit_reservation_ledger.sql").read_text()
DATABASE_URL = os.environ["DATABASE_URL"]


def fresh_database(*, per_run_cap=50, monthly_cap=100, remaining=100):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("""
            CREATE TABLE capture_manifests (
                capture_manifest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
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
        conn.execute(MIGRATION)
        manifest_id = conn.execute(
            "INSERT INTO capture_manifests DEFAULT VALUES RETURNING capture_manifest_id"
        ).fetchone()[0]
        now = datetime.now(timezone.utc)
        budget_id = conn.execute("""
            INSERT INTO provider_credit_budget_snapshots (
                provider, provider_account_ref, billing_period_start, billing_period_end,
                monthly_allowance, provider_remaining, monthly_hard_cap, per_run_hard_cap,
                request_count_cap, observed_at, valid_until, evidence_uri, evidence_sha256,
                terms_version, terms_acceptance_evidence_uri,
                terms_acceptance_evidence_sha256, rights_approval_ids
            ) VALUES (
                'the_odds_api', 'test-account', DATE '2026-11-01', DATE '2026-12-01',
                100, %s, %s, %s, 100, %s, %s, 'test://quota-evidence', %s,
                'terms-test-v1', 'test://terms-acceptance', %s,
                '[ "approval-test" ]'::jsonb
            ) RETURNING budget_snapshot_id
        """, (
            remaining, monthly_cap, per_run_cap, now - timedelta(seconds=1),
            now + timedelta(minutes=10), "a" * 64, "c" * 64,
        )).fetchone()[0]
    return manifest_id, budget_id, now


def reserve(conn, *, key, manifest_id, budget_id, now, run="run-1",
            request=None, attempt=1, estimate=10, fingerprint=None):
    request = request or f"request-{key}"
    fingerprint = fingerprint or (str(key).encode().hex()[:64].ljust(64, "0"))
    return conn.execute("""
        SELECT reserve_provider_credits(
            %s, 'the_odds_api', 'test-account',
            DATE '2026-11-01', DATE '2026-12-01',
            %s, %s, %s, %s, %s, %s, %s,
            'postgres-test', %s, %s, %s
        )
    """, (
        str(key), run, manifest_id, request, attempt, fingerprint, estimate,
        budget_id, now, "b" * 64, "c" * 64,
    )).fetchone()[0]


def test_migration_reserves_and_replays_idempotently():
    manifest_id, budget_id, now = fresh_database()
    with psycopg.connect(DATABASE_URL) as conn:
        first = reserve(conn, key="reserve-one", manifest_id=manifest_id,
                        budget_id=budget_id, now=now)
        second = reserve(conn, key="reserve-one", manifest_id=manifest_id,
                         budget_id=budget_id, now=now)
        assert first == second
        conn.commit()
        with pytest.raises(psycopg.Error, match="IDEMPOTENCY_CONFLICT"):
            reserve(conn, key="reserve-one", manifest_id=manifest_id,
                    budget_id=budget_id, now=now, estimate=11)
        conn.rollback()


def test_append_only_event_lifecycle_and_zero_usage_release_guard():
    manifest_id, budget_id, now = fresh_database()
    with psycopg.connect(DATABASE_URL) as conn:
        reserve(conn, key="reserve-two", manifest_id=manifest_id,
                budget_id=budget_id, now=now)
        conn.commit()
        with pytest.raises(psycopg.Error, match="ZERO_USAGE_EVIDENCE"):
            conn.execute("""
                SELECT append_provider_credit_reservation_event(
                    'reserve-two','RELEASED',10,NULL,'NOT_PROVEN_ZERO',
                    %s,%s,'test',%s
                )
            """, ("d" * 64, "e" * 64, now + timedelta(seconds=1)))
        conn.rollback()
        conn.execute("""
            SELECT append_provider_credit_reservation_event(
                'reserve-two','DISPATCH_CONFIRMED',10,NULL,'DISPATCHED',
                %s,%s,'test',%s
            )
        """, ("d" * 64, "e" * 64, now + timedelta(seconds=1)))
        conn.execute("""
            SELECT append_provider_credit_reservation_event(
                'reserve-two','RECONCILED',10,7,'QUOTA_CONFIRMED',
                %s,%s,'test',%s
            )
        """, ("f" * 64, "1" * 64, now + timedelta(seconds=2)))
        conn.commit()
        with pytest.raises(psycopg.Error, match="IMMUTABLE_HISTORY_MUTATION_REJECTED"):
            conn.execute("UPDATE provider_credit_reservation_events SET reason_code='tamper'")
        conn.rollback()


def test_concurrent_reservations_cannot_exceed_per_run_cap():
    manifest_id, budget_id, now = fresh_database(per_run_cap=50)

    def worker(i):
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                value = reserve(conn, key=f"parallel-{i}", manifest_id=manifest_id,
                                budget_id=budget_id, now=now, estimate=10)
                conn.commit()
                return value
        except psycopg.Error:
            return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(worker, range(10)))
    assert sum(value is not None for value in results) == 5
    with psycopg.connect(DATABASE_URL) as conn:
        count = conn.execute("""
            SELECT COUNT(*) FROM provider_credit_reservation_events
            WHERE event_sequence=1 AND event_type='RESERVED'
        """).fetchone()[0]
        assert count == 5
