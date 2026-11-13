"""Exercise a real upgrade from Phase 3 schema 0003 to Phase 4 migration 0004.

This script creates a disposable localhost-only test database. It never uses
Neon, production credentials, or a non-test DATABASE_URL.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import tempfile

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg import sql

from scripts.db_migrate import MIGRATION_DIR, migrate


BASE_DATABASE = "veltrix_football_test"
UPGRADE_DATABASE = "veltrix_football_upgrade_test"


def _insert_observation(conn, suffix: str) -> int:
    raw = f"phase4-upgrade-{suffix}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO provider_responses(
                provider,source_id,endpoint,request_id,request_params,http_status,
                response_sha256,raw_body,fetched_at
            ) VALUES (
                'upgrade-probe','upgrade-probe','/upgrade-probe',
                %s,'{}'::jsonb,200,%s,%s,NOW()
            ) RETURNING id
            """,
            (f"phase4-upgrade-{suffix}", digest, raw),
        )
        response_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO source_observations(
                provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                retrieved_at,payload,source_id,data_type,provider_response_id
            ) VALUES (
                'upgrade-probe','/upgrade-probe','TEAM',%s,%s,NOW(),
                '{}'::jsonb,'upgrade-probe','team_metadata',%s
            ) RETURNING id
            """,
            (f"legacy-team-{suffix}", digest, response_id),
        )
        return cur.fetchone()[0]


def run_upgrade_acceptance() -> dict:
    base_url = os.environ.get("DATABASE_URL", "")
    base_expected = os.environ.get("VELTRIX_EXPECTED_DATABASE", "")
    if not base_url or base_expected != BASE_DATABASE:
        raise RuntimeError("Upgrade acceptance requires the exact ephemeral CI base database")
    base_params = conninfo_to_dict(base_url)
    if base_params.get("dbname") != BASE_DATABASE or base_params.get("host") not in ("localhost", "127.0.0.1"):
        raise RuntimeError("Refusing non-local or unexpected upgrade-acceptance database target")

    admin_params = dict(base_params)
    admin_params["dbname"] = "postgres"
    admin_url = make_conninfo(**admin_params)
    upgrade_params = dict(base_params)
    upgrade_params["dbname"] = UPGRADE_DATABASE
    upgrade_url = make_conninfo(**upgrade_params)

    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(UPGRADE_DATABASE))
        )

    original_expected = os.environ.get("VELTRIX_EXPECTED_DATABASE")
    try:
        os.environ["VELTRIX_EXPECTED_DATABASE"] = UPGRADE_DATABASE
        with tempfile.TemporaryDirectory(prefix="veltrix-phase4-0003-") as temp:
            pre_phase4_dir = Path(temp)
            for path in sorted(MIGRATION_DIR.glob("000[123]_*.sql")):
                shutil.copy2(path, pre_phase4_dir / path.name)

            # Apply only 0001-0003, then create an observation that genuinely
            # predates migration 0004.
            migrate(upgrade_url, directory=pre_phase4_dir)
            with psycopg.connect(upgrade_url) as conn:
                legacy_id = _insert_observation(conn, "legacy")

            # Apply the full manifest; only migration 0004 should be pending.
            result = migrate(upgrade_url, directory=MIGRATION_DIR)
            if result.get("applied_now") != 1:
                raise AssertionError(f"Expected exactly migration 0004 to apply: {result}")

            with psycopg.connect(upgrade_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT recorded_at,source_published_at,source_effective_at,
                               source_timestamp_basis
                        FROM source_observations WHERE id=%s
                        """,
                        (legacy_id,),
                    )
                    legacy = cur.fetchone()
                    if legacy != (None, None, None, "unknown"):
                        raise AssertionError(f"Legacy evidence was backfilled: {legacy}")

                    new_id = _insert_observation(conn, "new")
                    cur.execute(
                        """
                        SELECT recorded_at,source_published_at,source_effective_at,
                               source_timestamp_basis
                        FROM source_observations WHERE id=%s
                        """,
                        (new_id,),
                    )
                    current = cur.fetchone()
                    if current is None or current[0] is None or current[1] is not None or current[2] is not None or current[3] != "unknown":
                        raise AssertionError(f"New observation timestamp defaults invalid: {current}")

                    cur.execute("SELECT version FROM schema_migrations ORDER BY version")
                    versions = [row[0] for row in cur.fetchall()]
                    if versions != [f"000{i}_{name}" for i, name in (
                        (1, "persistent_foundation"),
                        (2, "historical_provenance"),
                        (3, "source_approval_status_events"),
                        (4, "point_in_time_feature_capture"),
                    )]:
                        raise AssertionError(f"Unexpected upgrade migration history: {versions}")

        return {
            "status": "PASS",
            "upgrade_path": "0001-0003 -> 0004",
            "legacy_recorded_at_remained_null": True,
            "legacy_publication_and_effective_times_remained_null": True,
            "new_recorded_at_defaulted": True,
            "publication_time_not_fabricated": True,
        }
    finally:
        if original_expected is None:
            os.environ.pop("VELTRIX_EXPECTED_DATABASE", None)
        else:
            os.environ["VELTRIX_EXPECTED_DATABASE"] = original_expected


if __name__ == "__main__":
    print(run_upgrade_acceptance())
