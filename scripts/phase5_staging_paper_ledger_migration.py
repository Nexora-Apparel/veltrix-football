"""Dry-run-first, staging-only migration for the prospective paper ledger."""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlsplit

from scripts.db_migrate import load_manifest, migrate
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target


EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_ROLE = "neondb_owner"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
MIGRATION_VERSION = "0008_prospective_paper_ledger"
EXPECTED_PENDING = [
    "0005_provider_credit_reservation_ledger",
    "0006_provider_quota_evidence",
    "0007_provider_capture_state_events",
    "0008_prospective_paper_ledger",
]


def _connect_read_only(dsn: str):
    import psycopg

    connection = psycopg.connect(dsn, autocommit=False)
    connection.execute("SET TRANSACTION READ ONLY")
    connection.execute("SET LOCAL statement_timeout = '15000ms'")
    identity = connection.execute(
        "SELECT current_database(), current_user"
    ).fetchone()
    if identity != (EXPECTED_DATABASE, EXPECTED_ROLE):
        connection.close()
        raise PermissionError("PAPER_LEDGER_MIGRATION_TARGET_NOT_ALLOWLISTED")
    return connection


def _baseline(dsn: str) -> dict[str, int]:
    with _connect_read_only(dsn) as connection:
        queries = {
            "fixtures": "SELECT COUNT(*) FROM fixtures",
            "source_observations": "SELECT COUNT(*) FROM source_observations",
            "provider_responses": "SELECT COUNT(*) FROM provider_responses",
            "capture_manifests": "SELECT COUNT(*) FROM capture_manifests",
            "capture_manifest_events": "SELECT COUNT(*) FROM capture_manifest_events",
            "provider_capture_requests": "SELECT COUNT(*) FROM provider_capture_requests",
        }
        return {
            name: int(connection.execute(sql).fetchone()[0])
            for name, sql in queries.items()
        }


def _verify_after_apply(dsn: str, baseline: dict[str, int]) -> dict[str, object]:
    with _connect_read_only(dsn) as connection:
        versions = connection.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        manifest = load_manifest()
        expected = {version: checksum for version, checksum, _ in manifest}
        if {version: checksum.strip() for version, checksum in versions} != expected:
            raise RuntimeError("PAPER_LEDGER_MIGRATION_HISTORY_MISMATCH")

        table_exists = connection.execute(
            "SELECT to_regclass('public.paper_ledger_events') IS NOT NULL"
        ).fetchone()[0]
        if not table_exists:
            raise RuntimeError("PAPER_LEDGER_TABLE_MISSING")

        trigger_names = {
            row[0] for row in connection.execute(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'public.paper_ledger_events'::regclass
                  AND NOT tgisinternal
                """
            ).fetchall()
        }
        expected_triggers = {
            "paper_ledger_events_append_only",
            "paper_ledger_events_no_truncate",
        }
        if not expected_triggers.issubset(trigger_names):
            raise RuntimeError("PAPER_LEDGER_APPEND_ONLY_TRIGGERS_MISSING")

        indexes = {
            row[0] for row in connection.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname='public' AND tablename='paper_ledger_events'
                """
            ).fetchall()
        }
        if not {
            "paper_ledger_prediction_unique",
            "paper_ledger_settlement_unique",
        }.issubset(indexes):
            raise RuntimeError("PAPER_LEDGER_UNIQUE_INDEXES_MISSING")

        after = _baseline_counts_on_connection(connection)
        if after != baseline:
            raise RuntimeError("PAPER_LEDGER_MIGRATION_CHANGED_EXISTING_EVIDENCE")
        ledger_rows = int(connection.execute(
            "SELECT COUNT(*) FROM paper_ledger_events"
        ).fetchone()[0])
        if ledger_rows != 0:
            raise RuntimeError("PAPER_LEDGER_NOT_EMPTY_AFTER_SCHEMA_MIGRATION")
        return {
            "schema_migrations": len(versions),
            "paper_ledger_events": ledger_rows,
            "append_only_triggers": sorted(expected_triggers),
            "unique_indexes": sorted({
                "paper_ledger_prediction_unique",
                "paper_ledger_settlement_unique",
            }),
            "preserved_baseline": after,
        }


def _baseline_counts_on_connection(connection) -> dict[str, int]:
    queries = {
        "fixtures": "SELECT COUNT(*) FROM fixtures",
        "source_observations": "SELECT COUNT(*) FROM source_observations",
        "provider_responses": "SELECT COUNT(*) FROM provider_responses",
        "capture_manifests": "SELECT COUNT(*) FROM capture_manifests",
        "capture_manifest_events": "SELECT COUNT(*) FROM capture_manifest_events",
        "provider_capture_requests": "SELECT COUNT(*) FROM provider_capture_requests",
    }
    return {
        name: int(connection.execute(sql).fetchone()[0])
        for name, sql in queries.items()
    }


def run(*, apply: bool = False) -> dict[str, object]:
    dsn = os.environ.get("DATABASE_URL", "")
    validate_staging_dsn_target(dsn)
    if urlsplit(dsn).hostname != EXPECTED_HOST:
        raise PermissionError("PAPER_LEDGER_MIGRATION_HOST_NOT_ALLOWLISTED")

    manifest = load_manifest()
    versions = [entry[0] for entry in manifest]
    if len(versions) < 8 or versions[-1] != MIGRATION_VERSION:
        raise RuntimeError("PAPER_LEDGER_MIGRATION_NOT_LAST_IN_MANIFEST")
    expected_pending = versions[-len(EXPECTED_PENDING):]
    if expected_pending != EXPECTED_PENDING:
        raise RuntimeError("PAPER_LEDGER_PENDING_SEQUENCE_UNEXPECTED")

    baseline = _baseline(dsn)
    dry = migrate(dsn, dry_run=True)
    expected_applied = versions[:-len(EXPECTED_PENDING)]
    if dry["applied"] != expected_applied or dry["pending"] != expected_pending:
        raise RuntimeError("PAPER_LEDGER_MIGRATION_PRECONDITION_FAILED")

    if not apply:
        return {
            "status": "DRY_RUN_READY",
            "database": dry["database"],
            "user": dry["user"],
            "applied": dry["applied"],
            "pending": dry["pending"],
            "baseline": baseline,
            "writes_performed": False,
        }

    if os.environ.get("VELTRIX_ENABLE_PHASE5_PAPER_LEDGER_MIGRATION") != "YES":
        raise PermissionError("PAPER_LEDGER_MIGRATION_EXPLICIT_GUARD_REQUIRED")

    applied = migrate(dsn, dry_run=False)
    verified = _verify_after_apply(dsn, baseline)
    return {
        "status": "APPLIED_AND_VERIFIED",
        "database": applied["database"],
        "user": applied["user"],
        "applied_now": applied["applied_now"],
        "verification": verified,
        "writes_performed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = run(apply=args.apply)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
