"""PostgreSQL 16 schema, constraint, checksum and idempotency acceptance."""
from __future__ import annotations

import hashlib
import json
import os

import psycopg

from scripts.db_migrate import load_manifest


EXPECTED_TABLES = {
    "schema_migrations", "provider_accounts", "countries", "competitions",
    "teams", "fixtures", "fixture_results", "source_observations",
    "import_runs", "import_checkpoints", "reconciliation_audits",
    "source_approvals", "provider_responses", "provider_entitlement_observations",
    "fixture_result_versions", "sync_watermarks", "ingestion_quarantine",
    "source_approval_status_events",
}
EXPECTED_INDEXES = {
    "fixtures_kickoff_idx", "fixtures_competition_kickoff_idx",
    "fixtures_home_kickoff_idx", "fixtures_away_kickoff_idx",
    "source_observations_lookup_idx", "import_checkpoints_status_idx",
    "source_approvals_version_idx", "provider_responses_provider_time_idx",
    "provider_entitlement_history_idx", "source_observations_source_lookup_idx",
    "fixtures_provider_kickoff_idx", "fixture_result_versions_fixture_time_idx",
    "ingestion_quarantine_open_idx", "source_approval_status_latest_idx",
}


def run_acceptance() -> dict:
    url = os.environ["DATABASE_URL"]
    expected_db = os.environ["VELTRIX_EXPECTED_DATABASE"]
    manifest = load_manifest()
    manifest_hash = hashlib.sha256(
        "\n".join(f"{v}:{c}" for v, c, _ in manifest).encode()
    ).hexdigest()

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_setting('server_version_num')")
            db_name, version = cur.fetchone()
            assert db_name == expected_db, f"Wrong database: {db_name!r}"
            assert int(version) >= 160000, f"PostgreSQL 16 required, got {version}"

            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
            """)
            actual_tables = {r[0] for r in cur.fetchall()}
            assert actual_tables == EXPECTED_TABLES, {
                "missing": sorted(EXPECTED_TABLES - actual_tables),
                "unexpected": sorted(actual_tables - EXPECTED_TABLES),
            }

            cur.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
            actual_history = {v: c.strip() for v, c in cur.fetchall()}
            expected_history = {v: c for v, c, _ in manifest}
            assert actual_history == expected_history, {
                "missing": sorted(set(expected_history) - set(actual_history)),
                "unexpected": sorted(set(actual_history) - set(expected_history)),
                "checksum_mismatch": sorted(
                    v for v in set(actual_history) & set(expected_history)
                    if actual_history[v] != expected_history[v]
                ),
            }

            cur.execute("""
                SELECT contype, count(*) FROM pg_constraint
                WHERE connamespace='public'::regnamespace GROUP BY contype
            """)
            constraint_counts = dict(cur.fetchall())
            assert constraint_counts.get("p", 0) >= 11, constraint_counts
            assert constraint_counts.get("f", 0) >= 7, constraint_counts
            assert constraint_counts.get("u", 0) >= 5, constraint_counts
            assert constraint_counts.get("c", 0) >= 12, constraint_counts

            cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            actual_indexes = {r[0] for r in cur.fetchall()}
            assert EXPECTED_INDEXES <= actual_indexes, sorted(EXPECTED_INDEXES - actual_indexes)

            cur.execute("""
                SELECT tgname FROM pg_trigger
                WHERE NOT tgisinternal
                  AND tgrelid IN (
                    'source_observations'::regclass,
                    'provider_responses'::regclass,
                    'source_approvals'::regclass,
                    'provider_entitlement_observations'::regclass,
                    'fixture_result_versions'::regclass
                  )
            """)
            immutable_triggers = {row[0] for row in cur.fetchall()}
            expected_triggers = {
                "source_observations_append_only",
                "provider_responses_append_only",
                "source_approvals_append_only",
                "provider_entitlement_append_only",
                "fixture_result_versions_append_only",
                "source_approval_status_events_append_only",
            }
            assert expected_triggers <= immutable_triggers, sorted(expected_triggers - immutable_triggers)

            # The append-only guard must reject mutations without changing the source row.
            cur.execute("SAVEPOINT immutable_probe")
            cur.execute("""
                INSERT INTO source_approvals (
                    approval_id, provider, source_id, competition_scope, data_type,
                    status, rights_basis, terms_url, terms_version, evidence_uri,
                    evidence_sha256, reviewed_at, reviewer_id, valid_from,
                    permitted_uses, commercial_use_allowed
                ) VALUES (
                    '__acceptance_immutable_probe__', 'probe', 'probe', '*', 'fixture_result',
                    'APPROVED', 'TERMS', 'https://example.invalid/terms', 'test',
                    'https://example.invalid/evidence', repeat('a',64), NOW(), 'acceptance',
                    NOW(), '["STORAGE"]'::jsonb, TRUE
                )
            """)
            mutation_rejected = False
            try:
                cur.execute("UPDATE source_approvals SET status='REVOKED' WHERE approval_id='__acceptance_immutable_probe__'")
            except psycopg.errors.RaiseException:
                mutation_rejected = True
                cur.execute("ROLLBACK TO SAVEPOINT immutable_probe")
            assert mutation_rejected, "source approval append-only trigger did not reject UPDATE"

            # Approval revocation is an append-only event, never an UPDATE to the original approval.
            cur.execute("SAVEPOINT rights_event_probe")
            cur.execute("""
                INSERT INTO source_approval_status_events(
                    approval_id,status,evidence_uri,evidence_sha256,effective_at,reason_code
                ) VALUES (
                    '__acceptance_immutable_probe__','REVOKED',
                    'https://example.invalid/revocation', repeat('b',64), NOW(), 'ACCEPTANCE_PROBE'
                )
            """)
            status_event_mutation_rejected = False
            try:
                cur.execute("UPDATE source_approval_status_events SET status='APPROVED' WHERE approval_id='__acceptance_immutable_probe__'")
            except psycopg.errors.RaiseException:
                status_event_mutation_rejected = True
                cur.execute("ROLLBACK TO SAVEPOINT rights_event_probe")
            assert status_event_mutation_rejected, "source approval status event accepted UPDATE"
            cur.execute("RELEASE SAVEPOINT rights_event_probe")

            # Prove rollback semantics without leaving a probe row behind.
            cur.execute("SAVEPOINT acceptance_rollback_probe")
            cur.execute(
                "INSERT INTO provider_accounts(provider) VALUES ('__acceptance_rollback_probe__')"
            )
            cur.execute("ROLLBACK TO SAVEPOINT acceptance_rollback_probe")
            cur.execute(
                "SELECT count(*) FROM provider_accounts WHERE provider='__acceptance_rollback_probe__'"
            )
            assert cur.fetchone()[0] == 0
            cur.execute("RELEASE SAVEPOINT acceptance_rollback_probe")

            cur.execute("""
                INSERT INTO reconciliation_audits
                    (manifest_sha256, expected_migrations, applied_migrations, status, details)
                VALUES (%s, %s, %s, 'PASS', %s::jsonb)
            """, (
                manifest_hash, len(manifest), len(actual_history),
                json.dumps({"tables": len(actual_tables), "indexes": len(actual_indexes),
                            "constraints": constraint_counts}),
            ))
        conn.commit()
    return {"database": expected_db, "postgres_version_num": int(version),
            "tables": len(actual_tables), "indexes": len(actual_indexes),
            "migration_count": len(actual_history), "manifest_sha256": manifest_hash,
            "status": "PASS"}


if __name__ == "__main__":
    print(run_acceptance())
