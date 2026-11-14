"""Guarded Phase 4 migration runner for the dedicated Neon staging database.

Default behavior is a read-only dry run. Applying migration 0004 requires the
manual workflow's explicit apply flag and a second environment guard.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Mapping

import psycopg
from psycopg.conninfo import conninfo_to_dict

from scripts.db_migrate import load_manifest, migrate


EXPECTED_APPLIED = [
    "0001_persistent_foundation",
    "0002_historical_provenance",
    "0003_source_approval_status_events",
]
EXPECTED_PENDING = ["0004_point_in_time_feature_capture"]
EXPECTED_FIXTURES = 2496
EXPECTED_RESULT_VERSIONS = 2496
EXPECTED_PROVIDER_RESPONSES = 28
EXPECTED_SOURCE_OBSERVATIONS = 2496

PHASE4_APPEND_ONLY_TRIGGERS = {
    "capture_manifests_append_only",
    "capture_manifest_events_append_only",
    "provider_capture_requests_append_only",
    "entity_crosswalk_versions_append_only",
    "feature_snapshots_append_only",
    "feature_snapshot_eligibility_events_append_only",
    "feature_snapshot_links_append_only",
}


def validate_connection_target(
    params: Mapping[str, str],
    *,
    expected_database: str,
    expected_host: str,
    expected_role: str,
) -> dict[str, str]:
    """Reject pooled, wrong-project, wrong-database, or wrong-role targets."""
    host = params.get("host", "")
    database = params.get("dbname", "")
    role = params.get("user", "")
    if not expected_host or host != expected_host or "-pooler." in host or host.endswith("-pooler"):
        raise RuntimeError("STAGING_DATABASE_HOST_NOT_ALLOWLISTED")
    if not expected_database or database != expected_database:
        raise RuntimeError("STAGING_DATABASE_NAME_NOT_ALLOWLISTED")
    if not expected_role or role != expected_role:
        raise RuntimeError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
    return {"host": host, "database": database, "role": role}


def _target_from_environment(database_url: str) -> dict[str, str]:
    params = conninfo_to_dict(database_url)
    target = validate_connection_target(
        params,
        expected_database=os.environ.get("VELTRIX_EXPECTED_DATABASE", ""),
        expected_host=os.environ.get("VELTRIX_EXPECTED_DATABASE_HOST", ""),
        expected_role=os.environ.get("VELTRIX_EXPECTED_DATABASE_ROLE", ""),
    )
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), current_user, current_setting('server_version_num')"
            )
            db_name, role_name, server_version = cur.fetchone()
    if db_name != target["database"] or role_name != target["role"]:
        raise RuntimeError("CONNECTED_STAGING_IDENTITY_MISMATCH")
    if int(server_version) < 160000:
        raise RuntimeError("POSTGRESQL_16_OR_NEWER_REQUIRED")
    return {**target, "postgres_version_num": str(server_version)}


def _verify_staging(database_url: str, expected_database: str) -> dict:
    manifest = load_manifest()
    expected_history = {version: checksum for version, checksum, _ in manifest}
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            if cur.fetchone()[0] != expected_database:
                raise RuntimeError("POST_MIGRATION_DATABASE_IDENTITY_MISMATCH")

            cur.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version"
            )
            history = {version: checksum.strip() for version, checksum in cur.fetchall()}
            if history != expected_history:
                raise RuntimeError("POST_MIGRATION_CHECKSUM_HISTORY_MISMATCH")

            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
            table_count = cur.fetchone()[0]
            if table_count != 25:
                raise RuntimeError(f"POST_MIGRATION_TABLE_COUNT_MISMATCH:{table_count}")

            cur.execute(
                """
                SELECT
                    (SELECT count(*) FROM fixtures),
                    (SELECT count(*) FROM fixture_result_versions),
                    (SELECT count(*) FROM provider_responses),
                    (SELECT count(*) FROM source_observations)
                """
            )
            fixture_count, result_count, response_count, observation_count = cur.fetchone()
            expected_counts = (
                EXPECTED_FIXTURES,
                EXPECTED_RESULT_VERSIONS,
                EXPECTED_PROVIDER_RESPONSES,
                EXPECTED_SOURCE_OBSERVATIONS,
            )
            actual_counts = (fixture_count, result_count, response_count, observation_count)
            if actual_counts != expected_counts:
                raise RuntimeError(f"STAGING_DATA_COUNTS_CHANGED:{actual_counts}")

            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE point_in_time_certifiable IS FALSE),
                    count(*) FILTER (WHERE source_published_at IS NULL),
                    count(*) FILTER (WHERE source_effective_at IS NULL),
                    count(*) FILTER (WHERE recorded_at IS NULL)
                FROM source_observations
                """
            )
            historical_guards = cur.fetchone()
            if historical_guards != (2496, 2496, 2496, 2496):
                raise RuntimeError(f"HISTORICAL_ROWS_CHANGED_OR_PROMOTED:{historical_guards}")

            cur.execute(
                """
                SELECT tgname
                FROM pg_trigger
                WHERE NOT tgisinternal
                  AND tgrelid IN (
                    'capture_manifests'::regclass,
                    'capture_manifest_events'::regclass,
                    'provider_capture_requests'::regclass,
                    'entity_crosswalk_versions'::regclass,
                    'feature_snapshots'::regclass,
                    'feature_snapshot_eligibility_events'::regclass,
                    'feature_snapshot_links'::regclass
                  )
                """
            )
            trigger_names = {row[0] for row in cur.fetchall()}
            if not PHASE4_APPEND_ONLY_TRIGGERS <= trigger_names:
                raise RuntimeError(
                    f"PHASE4_APPEND_ONLY_TRIGGER_GAP:{sorted(PHASE4_APPEND_ONLY_TRIGGERS - trigger_names)}"
                )

            cur.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid='feature_snapshots'::regclass AND contype='u'
                """
            )
            unique_definitions = [row[0] for row in cur.fetchall()]
            if not any(
                all(field in definition for field in (
                    "fixture_id", "prediction_cutoff_at", "feature_schema_version",
                    "model_build_id", "selector_version", "feature_set_sha256"
                ))
                for definition in unique_definitions
            ):
                raise RuntimeError("FEATURE_SNAPSHOT_IDENTITY_CONSTRAINT_MISMATCH")

    return {
        "status": "PASS",
        "migrations": len(expected_history),
        "public_tables": table_count,
        "fixtures": fixture_count,
        "result_versions": result_count,
        "provider_responses": response_count,
        "source_observations": observation_count,
        "point_in_time_certifiable": 0,
        "phase4_append_only_relations": len(PHASE4_APPEND_ONLY_TRIGGERS),
        "historical_publication_effective_recorded_timestamps_fabricated": False,
    }


def expected_history_checksum(version: str) -> str:
    for candidate, checksum, _ in load_manifest():
        if candidate == version:
            return checksum
    raise RuntimeError(f"MIGRATION_NOT_IN_MANIFEST:{version}")


def run(*, apply: bool = False) -> dict:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL_REQUIRED")
    target = _target_from_environment(database_url)

    plan = migrate(database_url, dry_run=True)
    if plan.get("applied") != EXPECTED_APPLIED or plan.get("pending") != EXPECTED_PENDING:
        raise RuntimeError(
            f"STAGING_MIGRATION_PREFLIGHT_MISMATCH:applied={plan.get('applied')},"
            f"pending={plan.get('pending')}"
        )

    if not apply:
        return {
            "status": "DRY_RUN_PASS",
            "target": target,
            "applied_migrations": plan["applied"],
            "pending_migrations": plan["pending"],
            "migration_0004_sha256": expected_history_checksum("0004_point_in_time_feature_capture"),
            "writes_performed": False,
        }

    if os.environ.get("VELTRIX_ENABLE_PHASE4_STAGING_MIGRATION") != "YES":
        raise RuntimeError("PHASE4_STAGING_MIGRATION_ENABLE_GUARD_REQUIRED")

    result = migrate(database_url, dry_run=False)
    if result.get("applied_now") != 1:
        raise RuntimeError(f"EXPECTED_EXACTLY_ONE_MIGRATION:{result}")
    verification = _verify_staging(database_url, target["database"])
    return {
        "status": "APPLIED_AND_VERIFIED",
        "target": target,
        "migration_result": result,
        "verification": verification,
        "writes_performed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply exactly migration 0004 after all guards pass")
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply), sort_keys=True))


if __name__ == "__main__":
    main()
