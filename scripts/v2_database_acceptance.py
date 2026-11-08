"""Read-only acceptance gate for an isolated VELTRIX FOOTBALL V2 PostgreSQL database.

This script never applies migrations or prints connection credentials. Apply schema
only with scripts/v2_apply_migrations.py after separately verifying the target.
"""
from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from scripts.v2_apply_migrations import EXPECTED_DATABASE, validate_database_dsn

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations" / "v2"
REQUIRED_TABLES = frozenset({
    "v2_schema_migrations",
    "v2_source_records",
    "v2_competition_mappings",
    "v2_team_mappings",
    "v2_canonical_fixtures",
    "v2_fixture_sources",
    "v2_historical_matches",
    "v2_historical_match_sources",
    "v2_identity_quarantine",
    "v2_sync_watermarks",
    "v2_ingestion_runs",
})
REQUIRED_INDEXES = frozenset({
    "ix_v2_source_fixture",
    "ix_v2_source_competition_time",
    "ix_v2_team_mapping_lookup",
    "ix_v2_history_provider_fixture",
})
REQUIRED_CONSTRAINTS = frozenset({
    "v2_source_records_pkey",
    "v2_source_records_idempotency_key_key",
    "v2_source_records_provider_source_id_provider_record_id_data_cl",
    "v2_competition_mappings_pkey",
    "v2_team_mappings_pkey",
    "v2_canonical_fixtures_pkey",
    "v2_canonical_fixtures_check",
    "v2_fixture_sources_pkey",
    "v2_fixture_sources_source_record_id_fkey",
    "v2_fixture_sources_canonical_fixture_id_fkey",
    "v2_historical_matches_pkey",
    "v2_historical_matches_canonical_fixture_id_fkey",
    "v2_historical_matches_home_goals_check",
    "v2_historical_matches_away_goals_check",
    "v2_historical_matches_canonical_fixture_id_key",
    "v2_historical_match_sources_pkey",
    "v2_historical_match_sources_historical_match_id_fkey",
    "v2_historical_match_sources_source_record_id_fkey",
    "v2_historical_match_sources_provider_source_id_provider_fixture",
    "v2_identity_quarantine_pkey",
    "v2_identity_quarantine_source_record_id_fkey",
    "v2_sync_watermarks_pkey",
    "v2_sync_watermarks_version_check",
    "v2_ingestion_runs_pkey",
})


REQUIRED_COLUMNS = {
    "v2_source_records": {"source_record_id", "provider", "source_id", "provider_record_id", "provider_fixture_id", "raw_payload", "raw_payload_sha256", "fetched_at_utc", "ingested_at_utc", "rights_evidence"},
    "v2_competition_mappings": {"provider", "source_id", "provider_competition_id", "canonical_competition_id", "verification_state", "mapping_version", "evidence_ref", "valid_from_utc"},
    "v2_team_mappings": {"provider", "source_id", "provider_team_id", "canonical_team_id", "verification_state", "mapping_version", "evidence_ref", "valid_from_utc"},
    "v2_canonical_fixtures": {"canonical_fixture_id", "canonical_competition_id", "squad_category", "canonical_home_team_id", "canonical_away_team_id", "kickoff_at_utc"},
    "v2_fixture_sources": {"provider", "source_id", "provider_fixture_id", "source_record_id", "canonical_fixture_id", "identity_status", "evidence_refs"},
    "v2_historical_matches": {"historical_match_id", "canonical_fixture_id", "home_goals", "away_goals", "imported_at_utc"},
    "v2_historical_match_sources": {"historical_match_id", "source_record_id", "provider", "source_id", "provider_fixture_id"},
    "v2_identity_quarantine": {"quarantine_id", "source_record_id", "status", "reason_code", "candidate_ids", "created_at_utc"},
    "v2_sync_watermarks": {"provider", "data_class", "scope", "cursor", "version", "updated_at_utc"},
    "v2_ingestion_runs": {"ingestion_run_id", "provider", "data_class", "request_id", "status", "quota_units_consumed"},
}


def expected_migrations() -> dict[str, str]:
    result = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        result[path.stem] = sha256(path.read_bytes()).hexdigest()
    if not result:
        raise RuntimeError("V2_MIGRATION_FILES_MISSING")
    return result


def _require_target_approval(dsn: str) -> None:
    if os.environ.get("VELTRIX_V2_STORAGE_APPROVED") != "true":
        raise RuntimeError("V2_STORAGE_APPROVAL_REQUIRED")
    expected_host = os.environ.get("VELTRIX_V2_EXPECTED_HOST", "")
    if not expected_host:
        raise RuntimeError("V2_EXPECTED_NEON_HOST_REQUIRED")
    validate_database_dsn(dsn, expected_host=expected_host)
    parsed = urlparse(dsn)
    if (parsed.hostname or "").lower() != expected_host.lower():
        raise RuntimeError("V2_DATABASE_HOST_ALLOWLIST_MISMATCH")


def inspect_database(connection, *, expected_db: str = EXPECTED_DATABASE) -> dict:
    """Inspect schema/catalog and checksums inside a read-only transaction."""
    with connection.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SELECT current_database(), current_user, current_setting('transaction_read_only')")
        database, db_user, read_only = cur.fetchone()
        if database != expected_db:
            raise RuntimeError("V2_CONNECTED_DATABASE_NAME_MISMATCH")
        if read_only != "on":
            raise RuntimeError("V2_ACCEPTANCE_TRANSACTION_NOT_READ_ONLY")

        cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")
        tables = {row[0] for row in cur.fetchall()}
        cur.execute("""
            SELECT indexname FROM pg_catalog.pg_indexes
            WHERE schemaname='public'
        """)
        indexes = {row[0] for row in cur.fetchall()}
        cur.execute("""
            SELECT conname FROM pg_catalog.pg_constraint c
            JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
            JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public'
        """)
        constraints = {row[0] for row in cur.fetchall()}

        missing_tables = sorted(REQUIRED_TABLES - tables)
        cur.execute("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema='public'
        """)
        actual_columns = {}
        for table_name, column_name in cur.fetchall():
            actual_columns.setdefault(table_name, set()).add(column_name)
        missing_columns = {
            table: sorted(required - actual_columns.get(table, set()))
            for table, required in REQUIRED_COLUMNS.items()
            if required - actual_columns.get(table, set())
        }

        missing_indexes = sorted(REQUIRED_INDEXES - indexes)
        missing_constraints = sorted(REQUIRED_CONSTRAINTS - constraints)

        expected = expected_migrations()
        cur.execute("""
            SELECT migration_version, checksum_sha256, database_name
            FROM public.v2_schema_migrations
            ORDER BY migration_version
        """) if "v2_schema_migrations" in tables else None
        applied_rows = cur.fetchall() if "v2_schema_migrations" in tables else []
        applied = {version: (checksum.strip(), target_db)
                   for version, checksum, target_db in applied_rows}
        checksum_errors = []
        for version, digest in expected.items():
            stored = applied.get(version)
            if stored is None:
                checksum_errors.append({"migration": version, "reason": "NOT_APPLIED"})
            elif stored[0] != digest:
                checksum_errors.append({"migration": version, "reason": "CHECKSUM_MISMATCH"})
            elif stored[1] != expected_db:
                checksum_errors.append({"migration": version, "reason": "DATABASE_NAME_MISMATCH"})
        unexpected = sorted(set(applied) - set(expected))
        if unexpected:
            checksum_errors.append({"migration": ",".join(unexpected), "reason": "UNEXPECTED_APPLIED_MIGRATION"})

    report = {
        "database": database,
        "database_user": db_user,
        "transaction_read_only": read_only,
        "tables_found": len(tables),
        "tables_required": len(REQUIRED_TABLES),
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "missing_indexes": missing_indexes,
        "missing_constraints": missing_constraints,
        "migration_count_expected": len(expected),
        "migration_count_applied": len(applied),
        "migration_checksum_errors": checksum_errors,
    }
    report["accepted"] = not any((
        missing_tables, missing_columns, missing_indexes, missing_constraints, checksum_errors
    ))
    return report


def main() -> int:
    dsn = os.environ.get("VELTRIX_V2_DATABASE_URL", "")
    _require_target_approval(dsn)
    import psycopg

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        report = inspect_database(connection)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
