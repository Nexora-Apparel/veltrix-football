from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import psycopg

from veltrix_v2.data.credit_reservations import (
    BudgetSnapshotEvidence,
    PostgresCreditReservationStore,
    ReservationEvent,
)
from veltrix_v2.providers.odds_api_v4.reservations import (
    ReservationBudget,
    ReservationRequest,
)
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



def test_postgres_store_adapter_persists_budget_reserves_and_reconciles():
    manifest_id, budget_id, now = fresh_database(remaining=100, per_run_cap=50)
    budget = ReservationBudget(
        provider="the_odds_api",
        account_ref="test-account",
        period_start=date(2026, 11, 1),
        period_end=date(2026, 12, 1),
        monthly_allowance=100,
        provider_remaining=100,
        monthly_hard_cap=100,
        per_run_hard_cap=50,
        request_count_cap=100,
        observed_at=now - timedelta(seconds=1),
        valid_until=now + timedelta(minutes=10),
        evidence_sha256="a" * 64,
    )
    store = PostgresCreditReservationStore(
        lambda: psycopg.connect(DATABASE_URL),
        allow_writes=True,
        expected_database="veltrix_reservation_test",
    )
    snapshot_id = store.persist_budget_snapshot(
        BudgetSnapshotEvidence(
            budget=budget,
            evidence_uri="test://quota-evidence",
            terms_version="terms-test-v1",
            terms_acceptance_evidence_uri="test://terms-acceptance",
            terms_acceptance_evidence_sha256="c" * 64,
            rights_approval_ids=("approval-test",),
        )
    )
    assert snapshot_id == budget_id

    request = ReservationRequest(
        reservation_key="adapter-run:adapter-request:1",
        provider="the_odds_api",
        account_ref="test-account",
        period_start=date(2026, 11, 1),
        period_end=date(2026, 12, 1),
        run_key="adapter-run",
        manifest_id=manifest_id,
        request_key="adapter-request",
        attempt_number=1,
        request_fingerprint="f" * 64,
        estimated_credits=10,
        requested_at=now,
    )
    reservation_id = store.reserve(
        request, budget, budget_snapshot_id=snapshot_id,
        actor="postgres-adapter-test", now=now,
    )
    assert reservation_id > 0

    dispatch_event_id = store.append_event(ReservationEvent(
        reservation_key=request.reservation_key,
        event_type="DISPATCH_CONFIRMED",
        reserved_credits=10,
        actual_credits=None,
        reason_code="DISPATCH_CONFIRMED",
        evidence_sha256="d" * 64,
        actor="postgres-adapter-test",
        occurred_at=now + timedelta(seconds=1),
    ))
    reconcile_event_id = store.append_event(ReservationEvent(
        reservation_key=request.reservation_key,
        event_type="RECONCILED",
        reserved_credits=10,
        actual_credits=7,
        reason_code="QUOTA_RECONCILED",
        evidence_sha256="e" * 64,
        actor="postgres-adapter-test",
        occurred_at=now + timedelta(seconds=2),
    ))
    assert dispatch_event_id > 0
    assert reconcile_event_id > 0

    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """SELECT event_sequence,event_type,reserved_credits,actual_credits
               FROM provider_credit_reservation_events
               WHERE reservation_key=%s ORDER BY event_sequence""",
            (request.reservation_key,),
        ).fetchall()
    assert rows == [
        (1, "RESERVED", 10, None),
        (2, "DISPATCH_CONFIRMED", 10, None),
        (3, "RECONCILED", 10, 7),
    ]
