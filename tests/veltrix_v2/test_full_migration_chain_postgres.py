from urllib.parse import urlsplit, urlunsplit
import os
import uuid

import psycopg

from scripts.db_migrate import load_manifest, migrate


def test_complete_schema_migration_chain_on_clean_postgres16_plus(monkeypatch):
    base_dsn = os.environ["DATABASE_URL"]
    parsed = urlsplit(base_dsn)
    admin_dsn = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", "", ""))
    database_name = f"veltrix_migration_{uuid.uuid4().hex[:12]}"
    test_dsn = urlunsplit((
        parsed.scheme, parsed.netloc, f"/{database_name}", "", ""
    ))

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{database_name}"')

    try:
        monkeypatch.setenv("VELTRIX_EXPECTED_DATABASE", database_name)
        dry = migrate(test_dsn, dry_run=True)
        assert dry["applied"] == []
        assert dry["pending"] == [entry[0] for entry in load_manifest()]

        applied = migrate(test_dsn, dry_run=False)
        assert applied["applied_now"] == len(load_manifest())
        with psycopg.connect(test_dsn) as connection:
            versions = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
            assert [row[0] for row in versions] == [
                entry[0] for entry in load_manifest()
            ]
            assert connection.execute(
                "SELECT to_regclass('public.paper_ledger_events') IS NOT NULL"
            ).fetchone()[0]
            assert connection.execute(
                "SELECT COUNT(*) FROM paper_ledger_events"
            ).fetchone()[0] == 0
            assert connection.execute(
                """
                SELECT COUNT(*) FROM pg_trigger
                WHERE tgrelid='public.paper_ledger_events'::regclass
                  AND NOT tgisinternal
                """
            ).fetchone()[0] == 3
            assert connection.execute(
                "SELECT to_regclass('public.provider_credit_reservation_events') IS NOT NULL"
            ).fetchone()[0]
            assert connection.execute(
                "SELECT to_regclass('public.provider_quota_snapshots') IS NOT NULL"
            ).fetchone()[0]
            assert connection.execute(
                "SELECT to_regclass('public.provider_capture_state_events') IS NOT NULL"
            ).fetchone()[0]
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                (database_name,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
