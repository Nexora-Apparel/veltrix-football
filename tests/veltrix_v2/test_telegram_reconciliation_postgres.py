from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from urllib.parse import urlsplit, urlunsplit
import uuid

import psycopg
import pytest

from scripts.db_migrate import migrate
from veltrix_v2.reporting.reconciliation import PostgresTelegramReconciliationStore


def test_postgres_reconciliation_is_claim_bound_append_only_and_supersedable(monkeypatch):
    base_dsn = os.environ["DATABASE_URL"]
    parsed = urlsplit(base_dsn)
    admin_dsn = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", "", ""))
    database_name = f"veltrix_reconcile_{uuid.uuid4().hex[:12]}"
    test_dsn = urlunsplit((parsed.scheme, parsed.netloc, f"/{database_name}", "", ""))
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{database_name}"')
    try:
        monkeypatch.setenv("VELTRIX_EXPECTED_DATABASE", database_name)
        migrate(test_dsn, dry_run=False)
        key = "a" * 64
        report_id = "reconciliation-integration-report"
        report_hash = "b" * 64
        destination_hash = hashlib.sha256(b"telegram:integration").hexdigest()
        with psycopg.connect(test_dsn) as connection:
            connection.execute(
                """
                INSERT INTO telegram_delivery_claims (
                    idempotency_key, report_id, report_sha256, destination_sha256
                ) VALUES (%s, %s, %s, %s)
                """,
                (key, report_id, report_hash, destination_hash),
            )
            connection.execute(
                """
                UPDATE telegram_delivery_claims
                SET state='OUTCOME_UNKNOWN', updated_at=NOW(), reason_code='TimeoutError'
                WHERE idempotency_key=%s
                """,
                (key,),
            )

        evidence = b"immutable telegram evidence"
        evidence_hash = hashlib.sha256(evidence).hexdigest()
        store = PostgresTelegramReconciliationStore(
            lambda: psycopg.connect(test_dsn),
            lambda uri: evidence if uri == "s3://veltrix-audit/telegram/integration.json" else b"",
        )
        now = datetime.now(timezone.utc)
        first_id = str(uuid.uuid4())
        base_event = {
            "reconciliation_id": first_id,
            "idempotency_key": key,
            "report_id": report_id,
            "report_sha256": report_hash,
            "destination_sha256": destination_hash,
            "outcome": "CONFIRMED_SENT",
            "telegram_message_ids": ["tg-message-1"],
            "evidence_uri": "s3://veltrix-audit/telegram/integration.json",
            "evidence_sha256": evidence_hash,
            "evidence_kind": "telegram_export_json",
            "operator_id": "github:operator",
            "reviewer_id": None,
            "observed_at": now.isoformat(),
            "recorded_at": now.isoformat(),
            "reason_code": "OPERATOR_EVIDENCE_CONFIRMED",
        }
        assert store.record(base_event) == first_id
        with psycopg.connect(test_dsn) as connection:
            row = connection.execute(
                """
                SELECT outcome, telegram_message_ids, report_id, destination_sha256
                FROM telegram_delivery_reconciliations
                WHERE reconciliation_id=%s
                """,
                (first_id,),
            ).fetchone()
            assert row == ("CONFIRMED_SENT", ["tg-message-1"], report_id, destination_hash)
            with pytest.raises(psycopg.Error):
                connection.execute(
                    """
                    UPDATE telegram_delivery_reconciliations
                    SET outcome='INCONCLUSIVE'
                    WHERE reconciliation_id=%s
                    """,
                    (first_id,),
                )
            connection.rollback()
            with pytest.raises(psycopg.Error):
                connection.execute(
                    "DELETE FROM telegram_delivery_reconciliations WHERE reconciliation_id=%s",
                    (first_id,),
                )
            connection.rollback()

        corrected = {
            **base_event,
            "reconciliation_id": str(uuid.uuid4()),
            "outcome": "INCONCLUSIVE",
            "telegram_message_ids": [],
            "reason_code": "SUPERSEDING_REVIEW_INCONCLUSIVE",
            "supersedes_reconciliation_id": first_id,
        }
        assert store.record(corrected) == corrected["reconciliation_id"]
        with psycopg.connect(test_dsn) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM telegram_delivery_reconciliations WHERE idempotency_key=%s",
                (key,),
            ).fetchone()[0] == 2
            assert connection.execute(
                "SELECT state FROM telegram_delivery_claims WHERE idempotency_key=%s",
                (key,),
            ).fetchone()[0] == "OUTCOME_UNKNOWN"
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (database_name,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
