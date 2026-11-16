from concurrent.futures import ThreadPoolExecutor
import os
from urllib.parse import urlsplit, urlunsplit
import uuid

import psycopg
import pytest

from scripts.db_migrate import migrate
from veltrix_v2.reporting.delivery import DeliveryReceipt
from veltrix_v2.reporting.postgres_delivery_store import PostgresTelegramDeliveryStore
from veltrix_v2.reporting.report_identity import (
    REPORT_SCHEMA, create_report_identity, delivery_idempotency_key,
    delivery_idempotency_key_fields,
)


def test_postgres_delivery_claim_is_atomic_terminal_and_destination_bound(monkeypatch):
    base_dsn = os.environ["DATABASE_URL"]
    parsed = urlsplit(base_dsn)
    admin_dsn = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", "", ""))
    database_name = f"veltrix_delivery_{uuid.uuid4().hex[:12]}"
    test_dsn = urlunsplit((parsed.scheme, parsed.netloc, f"/{database_name}", "", ""))
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{database_name}"')
    try:
        monkeypatch.setenv("VELTRIX_EXPECTED_DATABASE", database_name)
        migrate(test_dsn, dry_run=False)
        store = PostgresTelegramDeliveryStore(lambda: psycopg.connect(test_dsn))
        identity = create_report_identity({
            "schema": REPORT_SCHEMA,
            "report_id": "postgres-delivery-integration",
            "as_of_date": "2026-11-14",
            "predictions": [],
        })
        destination = "telegram:integration-chat"
        key = delivery_idempotency_key(identity, destination)

        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(
                lambda _: store.claim(key, identity.report_id, identity.report_sha256, destination),
                range(8),
            ))
        assert sum(claims) == 1
        with pytest.raises(ValueError, match="REPORT_BINDING_MISMATCH"):
            store.claim("a" * 64, identity.report_id, identity.report_sha256, destination)
        with pytest.raises(ValueError, match="CLAIM_NOT_ACTIVE"):
            store.mark_sent(key, DeliveryReceipt("telegram:wrong-chat", ("9999",)))

        store.mark_sent(key, DeliveryReceipt(destination, ("1001", "1002")))
        assert not store.claim(key, identity.report_id, identity.report_sha256, destination)
        with psycopg.connect(test_dsn) as connection:
            row = connection.execute(
                """
                SELECT state, telegram_message_ids, destination_sha256
                FROM telegram_delivery_claims WHERE idempotency_key=%s
                """,
                (key,),
            ).fetchone()
            assert row[0] == "SENT"
            assert row[1] == ["1001", "1002"]

        unknown_key = delivery_idempotency_key_fields(
            "unknown-report", "c" * 64, destination
        )
        assert store.claim(unknown_key, "unknown-report", "c" * 64, destination)
        store.mark_unknown(unknown_key, "TimeoutError")
        assert not store.claim(unknown_key, "unknown-report", "c" * 64, destination)
        with psycopg.connect(test_dsn) as connection:
            assert connection.execute(
                "SELECT state FROM telegram_delivery_claims WHERE idempotency_key=%s",
                (unknown_key,),
            ).fetchone()[0] == "OUTCOME_UNKNOWN"

        stale_key = "d" * 64
        with psycopg.connect(test_dsn) as connection:
            connection.execute(
                """
                INSERT INTO telegram_delivery_claims (
                    idempotency_key, report_id, report_sha256, destination_sha256,
                    claimed_at, updated_at
                ) VALUES (%s, %s, %s, %s, NOW() - INTERVAL '10 minutes',
                          NOW() - INTERVAL '10 minutes')
                """,
                (stale_key, "stale-report", "e" * 64, "f" * 64),
            )
        assert store.mark_stale_claim_unknown(stale_key, minimum_age_seconds=300)
        assert not store.mark_stale_claim_unknown(stale_key, minimum_age_seconds=300)
        fresh_key = delivery_idempotency_key_fields(
            "fresh-report", "8" * 64, destination
        )
        assert store.claim(fresh_key, "fresh-report", "8" * 64, destination)
        assert not store.mark_stale_claim_unknown(fresh_key, minimum_age_seconds=300)
        with pytest.raises(ValueError, match="MINIMUM_AGE_OUT_OF_RANGE"):
            store.mark_stale_claim_unknown(fresh_key, minimum_age_seconds=30)
        with psycopg.connect(test_dsn) as connection:
            assert connection.execute(
                "SELECT state FROM telegram_delivery_claims WHERE idempotency_key=%s",
                (stale_key,),
            ).fetchone()[0] == "OUTCOME_UNKNOWN"
            assert connection.execute(
                "SELECT state FROM telegram_delivery_claims WHERE idempotency_key=%s",
                (fresh_key,),
            ).fetchone()[0] == "CLAIMED"

        with psycopg.connect(test_dsn) as connection:
            with pytest.raises(psycopg.Error):
                connection.execute(
                    "UPDATE telegram_delivery_claims SET report_id='rewritten' WHERE idempotency_key=%s",
                    (key,),
                )
            connection.rollback()
            with pytest.raises(psycopg.Error):
                connection.execute(
                    "DELETE FROM telegram_delivery_claims WHERE idempotency_key=%s",
                    (key,),
                )
            connection.rollback()
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (database_name,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
