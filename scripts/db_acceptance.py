"""PostgreSQL 16 schema, constraint, checksum and idempotency acceptance."""
# Includes migration 0004 point-in-time capture and append-only feature evidence invariants.
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
    "source_approval_status_events", "capture_manifests", "capture_manifest_events",
    "provider_capture_requests", "entity_crosswalk_versions", "feature_snapshots",
    "feature_snapshot_eligibility_events", "feature_snapshot_links",
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
                    'fixture_result_versions'::regclass,
                    'source_approval_status_events'::regclass,
                    'capture_manifests'::regclass,
                    'capture_manifest_events'::regclass,
                    'provider_capture_requests'::regclass,
                    'entity_crosswalk_versions'::regclass,
                    'feature_snapshots'::regclass,
                    'feature_snapshot_eligibility_events'::regclass,
                    'feature_snapshot_links'::regclass
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
                "capture_manifests_append_only",
                "capture_manifest_events_append_only",
                "provider_capture_requests_append_only",
                "entity_crosswalk_versions_append_only",
                "feature_snapshots_append_only",
                "feature_snapshot_eligibility_events_append_only",
                "feature_snapshot_links_append_only",
            }
            assert expected_triggers <= immutable_triggers, sorted(expected_triggers - immutable_triggers)

            # Phase 4 timestamp columns must not fabricate publication history.
            cur.execute("""
                SELECT column_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name='source_observations'
                  AND column_name IN (
                    'source_published_at','source_effective_at','recorded_at',
                    'source_timestamp_raw','source_timestamp_basis'
                  )
            """)
            timestamp_columns = {row[0]: row[1:] for row in cur.fetchall()}
            assert set(timestamp_columns) == {
                'source_published_at','source_effective_at','recorded_at',
                'source_timestamp_raw','source_timestamp_basis'
            }
            assert timestamp_columns['source_published_at'][0] == 'YES'
            assert timestamp_columns['source_effective_at'][0] == 'YES'
            assert timestamp_columns['recorded_at'][0] == 'YES'
            assert timestamp_columns['recorded_at'][1] is not None

            # New feature snapshots must reference a real fixture and remain append-only.
            cur.execute("SAVEPOINT phase4_snapshot_probe")
            cur.execute("""
                INSERT INTO countries(country_code,country_name,source_provider,observed_at)
                VALUES ('ZZ','Phase4 Test','phase4-acceptance',NOW())
            """)
            cur.execute("""
                INSERT INTO teams(provider,provider_team_id,name,observed_at)
                VALUES ('phase4-acceptance','home','Phase4 Home',NOW()),
                       ('phase4-acceptance','away','Phase4 Away',NOW())
            """)
            cur.execute("""
                INSERT INTO fixtures(
                    provider,provider_fixture_id,home_team_id,away_team_id,
                    kickoff_at,status,source_payload_sha256,retrieved_at
                )
                SELECT 'phase4-acceptance','fixture',h.id,a.id,NOW()+INTERVAL '1 day',
                       'SCHEDULED',repeat('d',64),NOW()
                FROM teams h,teams a
                WHERE h.provider='phase4-acceptance' AND h.provider_team_id='home'
                  AND a.provider='phase4-acceptance' AND a.provider_team_id='away'
            """)
            cur.execute("""
                INSERT INTO feature_snapshots(
                    snapshot_key,fixture_id,prediction_cutoff_at,feature_schema_version,
                    model_build_id,feature_set_sha256,selector_version
                )
                SELECT 'phase4-acceptance-snapshot',id,NOW(),'test-v1','test-build',
                       repeat('e',64),'selector-v1'
                FROM fixtures WHERE provider_fixture_id='fixture'
            """)
            cur.execute("""
                INSERT INTO feature_snapshot_eligibility_events(
                    feature_snapshot_id,eligibility_status,reason_codes,evidence_sha256
                )
                SELECT feature_snapshot_id,'PENDING','[]'::jsonb,repeat('f',64)
                FROM feature_snapshots WHERE snapshot_key='phase4-acceptance-snapshot'
            """)
            cur.execute("""
                INSERT INTO feature_snapshot_links(
                    feature_snapshot_id,feature_key,feature_status,feature_value,
                    eligibility_reason_code
                )
                SELECT feature_snapshot_id,'F01.form','MISSING',NULL,'SOURCE_NOT_CAPTURED'
                FROM feature_snapshots WHERE snapshot_key='phase4-acceptance-snapshot'
            """)
            phase4_mutation_rejected = False
            try:
                cur.execute("""
                    UPDATE feature_snapshots SET selector_version='mutated'
                    WHERE snapshot_key='phase4-acceptance-snapshot'
                """)
            except psycopg.errors.RaiseException:
                phase4_mutation_rejected = True
                cur.execute("ROLLBACK TO SAVEPOINT phase4_snapshot_probe")
            assert phase4_mutation_rejected, "Phase 4 feature snapshot accepted UPDATE"
            cur.execute("RELEASE SAVEPOINT phase4_snapshot_probe")

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
                INSERT INTO source_approvals (
                    approval_id, provider, source_id, competition_scope, data_type,
                    status, rights_basis, terms_url, terms_version, evidence_uri,
                    evidence_sha256, reviewed_at, reviewer_id, valid_from,
                    permitted_uses, commercial_use_allowed
                ) VALUES (
                    '__acceptance_status_event_probe__', 'probe', 'probe', '4160026622', 'fixture_result',
                    'APPROVED', 'TERMS', 'https://example.invalid/terms', 'test',
                    'https://example.invalid/evidence', repeat('c',64), NOW(), 'acceptance',
                    NOW(), '["STORAGE"]'::jsonb, TRUE
                )
            """)
            cur.execute("""
                INSERT INTO source_approval_status_events(
                    approval_id,status,evidence_uri,evidence_sha256,effective_at,reason_code
                ) VALUES (
                    '__acceptance_status_event_probe__','REVOKED',
                    'https://example.invalid/revocation', repeat('b',64), NOW(), 'ACCEPTANCE_PROBE'
                )
            """)
            status_event_mutation_rejected = False
            try:
                cur.execute("UPDATE source_approval_status_events SET status='APPROVED' WHERE approval_id='__acceptance_status_event_probe__'")
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
