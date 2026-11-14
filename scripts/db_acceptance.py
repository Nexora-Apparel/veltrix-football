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
                "entity_crosswalk_no_resolved_overlap",
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
            crosswalk_body = b"phase4-crosswalk-acceptance"
            crosswalk_hash = hashlib.sha256(crosswalk_body).hexdigest()
            cur.execute("""
                INSERT INTO provider_responses(
                    provider,source_id,endpoint,request_id,request_params,http_status,
                    response_sha256,raw_body,fetched_at
                ) VALUES (
                    'phase4-acceptance','phase4-acceptance','/crosswalk-probe',
                    'phase4-crosswalk-probe','{}'::jsonb,200,%s,%s,NOW()
                )
                RETURNING id
            """, (crosswalk_hash, crosswalk_body))
            crosswalk_response_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO source_observations(
                    provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                    retrieved_at,payload,source_id,data_type,provider_response_id
                ) VALUES (
                    'phase4-acceptance','/crosswalk-probe','TEAM','provider-team-1',
                    %s,NOW(),'{}'::jsonb,'phase4-acceptance','team_metadata',%s
                )
                RETURNING id
            """, (crosswalk_hash, crosswalk_response_id))
            crosswalk_observation_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO entity_crosswalk_versions(
                    entity_type,provider,source_id,provider_entity_id,canonical_entity_key,
                    mapping_version,mapping_status,mapping_method,valid_from,valid_until,
                    evidence_observation_id,decision_reason
                ) VALUES (
                    'TEAM','phase4-acceptance','phase4-acceptance','provider-team-1',
                    'team:phase4-acceptance:home',1,'RESOLVED','EXACT_PROVIDER_ID',
                    NOW(),NOW()+INTERVAL '2 days',%s,'exact provider identity acceptance probe'
                )
            """, (crosswalk_observation_id,))
            cur.execute("SAVEPOINT crosswalk_overlap_probe")
            crosswalk_overlap_rejected = False
            try:
                cur.execute("""
                    INSERT INTO entity_crosswalk_versions(
                        entity_type,provider,source_id,provider_entity_id,canonical_entity_key,
                        mapping_version,mapping_status,mapping_method,valid_from,valid_until,
                        evidence_observation_id,decision_reason
                    ) VALUES (
                        'TEAM','phase4-acceptance','phase4-acceptance','provider-team-1',
                        'team:phase4-acceptance:renamed',2,'RESOLVED','EXACT_PROVIDER_ID',
                        NOW()+INTERVAL '1 day',NOW()+INTERVAL '3 days',%s,
                        'overlap must be rejected'
                    )
                """, (crosswalk_observation_id,))
            except psycopg.errors.RaiseException:
                crosswalk_overlap_rejected = True
                cur.execute("ROLLBACK TO SAVEPOINT crosswalk_overlap_probe")
            assert crosswalk_overlap_rejected, "overlapping RESOLVED crosswalk validity interval was accepted"
            cur.execute("RELEASE SAVEPOINT crosswalk_overlap_probe")

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
                RETURNING feature_snapshot_link_id
            """)
            feature_link_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO capture_manifests(
                    manifest_key,manifest_sha256,capture_scope,requests_planned
                ) VALUES (
                    'phase4-acceptance-manifest',repeat('1',64),
                    '{"provider":"phase4-acceptance","endpoint_family":"acceptance"}'::jsonb,1
                )
                RETURNING capture_manifest_id
            """)
            capture_manifest_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO capture_manifest_events(
                    capture_manifest_id,status,event_at,reason_code
                ) VALUES (%s,'PLANNED',NOW(),'ACCEPTANCE_PROBE')
                RETURNING capture_manifest_event_id
            """, (capture_manifest_id,))
            capture_manifest_event_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO provider_capture_requests(
                    capture_manifest_id,provider,source_id,endpoint,request_key,
                    request_fingerprint,attempt_number,requested_at,outcome
                ) VALUES (
                    %s,'phase4-acceptance','phase4-acceptance','/acceptance',
                    'phase4-acceptance-timeout',repeat('2',64),1,NOW(),'TIMEOUT'
                )
                RETURNING capture_request_id
            """, (capture_manifest_id,))
            capture_request_id = cur.fetchone()[0]
            cur.execute("""
                SELECT crosswalk_version_id FROM entity_crosswalk_versions
                WHERE provider='phase4-acceptance'
                  AND provider_entity_id='provider-team-1' AND mapping_version=1
            """)
            crosswalk_version_id = cur.fetchone()[0]
            cur.execute("""
                SELECT feature_snapshot_id FROM feature_snapshots
                WHERE snapshot_key='phase4-acceptance-snapshot'
            """)
            feature_snapshot_id = cur.fetchone()[0]
            cur.execute("""
                SELECT eligibility_event_id FROM feature_snapshot_eligibility_events
                WHERE feature_snapshot_id=%s
            """, (feature_snapshot_id,))
            eligibility_event_id = cur.fetchone()[0]

            def assert_phase4_append_only(table_name, update_sql, update_params, delete_sql, delete_params):
                for operation, statement, params in (
                    ("update", update_sql, update_params),
                    ("delete", delete_sql, delete_params),
                ):
                    savepoint = f"phase4_{table_name}_{operation}_probe"
                    cur.execute(f"SAVEPOINT {savepoint}")
                    rejected = False
                    try:
                        cur.execute(statement, params)
                    except psycopg.errors.RaiseException:
                        rejected = True
                        cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    assert rejected, f"Phase 4 {table_name} accepted {operation.upper()}"
                    cur.execute(f"RELEASE SAVEPOINT {savepoint}")

            phase4_immutable_probes = [
                (
                    "capture_manifests",
                    "UPDATE capture_manifests SET manifest_sha256=repeat('0',64) WHERE capture_manifest_id=%s",
                    (capture_manifest_id,),
                    "DELETE FROM capture_manifests WHERE capture_manifest_id=%s",
                    (capture_manifest_id,),
                ),
                (
                    "capture_manifest_events",
                    "UPDATE capture_manifest_events SET reason_code='MUTATED' WHERE capture_manifest_event_id=%s",
                    (capture_manifest_event_id,),
                    "DELETE FROM capture_manifest_events WHERE capture_manifest_event_id=%s",
                    (capture_manifest_event_id,),
                ),
                (
                    "provider_capture_requests",
                    "UPDATE provider_capture_requests SET endpoint='/mutated' WHERE capture_request_id=%s",
                    (capture_request_id,),
                    "DELETE FROM provider_capture_requests WHERE capture_request_id=%s",
                    (capture_request_id,),
                ),
                (
                    "entity_crosswalk_versions",
                    "UPDATE entity_crosswalk_versions SET canonical_entity_key='mutated' WHERE crosswalk_version_id=%s",
                    (crosswalk_version_id,),
                    "DELETE FROM entity_crosswalk_versions WHERE crosswalk_version_id=%s",
                    (crosswalk_version_id,),
                ),
                (
                    "feature_snapshots",
                    "UPDATE feature_snapshots SET selector_version='mutated' WHERE feature_snapshot_id=%s",
                    (feature_snapshot_id,),
                    "DELETE FROM feature_snapshots WHERE feature_snapshot_id=%s",
                    (feature_snapshot_id,),
                ),
                (
                    "feature_snapshot_eligibility_events",
                    "UPDATE feature_snapshot_eligibility_events SET eligibility_status='ELIGIBLE' WHERE eligibility_event_id=%s",
                    (eligibility_event_id,),
                    "DELETE FROM feature_snapshot_eligibility_events WHERE eligibility_event_id=%s",
                    (eligibility_event_id,),
                ),
                (
                    "feature_snapshot_links",
                    "UPDATE feature_snapshot_links SET eligibility_reason_code='MUTATED' WHERE feature_snapshot_link_id=%s",
                    (feature_link_id,),
                    "DELETE FROM feature_snapshot_links WHERE feature_snapshot_link_id=%s",
                    (feature_link_id,),
                ),
            ]
            for probe in phase4_immutable_probes:
                assert_phase4_append_only(*probe)

            # Composite response FK must reject a response linked to a different provider/source.
            cur.execute("SAVEPOINT phase4_response_scope_probe")
            response_scope_mismatch_rejected = False
            try:
                cur.execute("""
                    INSERT INTO provider_capture_requests(
                        capture_manifest_id,provider,source_id,endpoint,request_key,
                        request_fingerprint,attempt_number,requested_at,response_id,outcome
                    ) VALUES (
                        %s,'wrong-provider','wrong-source','/acceptance',
                        'phase4-response-scope-mismatch',repeat('3',64),1,NOW(),%s,'RESPONSE'
                    )
                """, (capture_manifest_id, crosswalk_response_id))
            except psycopg.errors.ForeignKeyViolation:
                response_scope_mismatch_rejected = True
                cur.execute("ROLLBACK TO SAVEPOINT phase4_response_scope_probe")
            assert response_scope_mismatch_rejected, "Provider response composite FK accepted a mismatched provider/source"
            cur.execute("RELEASE SAVEPOINT phase4_response_scope_probe")
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
            "phase4_append_only_relations": 7, "phase4_append_only_operations": 14,
            "provider_response_scope_mismatch_rejected": True, "status": "PASS"}


if __name__ == "__main__":
    print(run_acceptance())
