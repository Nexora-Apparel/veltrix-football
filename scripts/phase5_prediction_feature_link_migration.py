"""Dry-run-first staging migration for append-only V2 prediction evidence links."""
from __future__ import annotations

import argparse
import os
from urllib.parse import urlsplit

from scripts.db_migrate import load_manifest, migrate
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target

EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_ROLE = "neondb_owner"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
PENDING = ["0012_prediction_feature_snapshot_links"]


def _connect_read_only(dsn: str):
    import psycopg
    conn = psycopg.connect(dsn, autocommit=False)
    conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL statement_timeout='15000ms'")
    identity = conn.execute("SELECT current_database(),current_user").fetchone()
    if identity != (EXPECTED_DATABASE, EXPECTED_ROLE):
        conn.close()
        raise PermissionError("V2_FEATURE_LINK_MIGRATION_TARGET_NOT_ALLOWLISTED")
    return conn


def _baseline(dsn: str) -> dict[str, int]:
    names = (
        "fixtures","source_observations","provider_responses","capture_manifests",
        "provider_capture_requests","paper_ledger_events","feature_snapshots",
        "feature_snapshot_links","feature_snapshot_eligibility_events",
        "odds_quote_observations",
    )
    result = {}
    with _connect_read_only(dsn) as conn:
        for name in names:
            exists = conn.execute(
                "SELECT to_regclass(%s) IS NOT NULL",(f"public.{name}",)
            ).fetchone()[0]
            result[name] = int(conn.execute(f"SELECT COUNT(*) FROM public.{name}").fetchone()[0]) if exists else 0
    return result


def _verify(dsn: str, baseline: dict[str, int]) -> dict[str, object]:
    with _connect_read_only(dsn) as conn:
        versions = conn.execute(
            "SELECT version,checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        manifest = load_manifest()
        expected = {version:checksum for version,checksum,_ in manifest}
        actual = {version:checksum.strip() for version,checksum in versions}
        if actual != expected:
            raise RuntimeError("V2_FEATURE_LINK_MIGRATION_HISTORY_MISMATCH")
        if not conn.execute(
            "SELECT to_regclass('public.prediction_feature_snapshot_links') IS NOT NULL"
        ).fetchone()[0]:
            raise RuntimeError("V2_PREDICTION_FEATURE_LINK_TABLE_MISSING")
        triggers = {
            row[0] for row in conn.execute(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid='public.prediction_feature_snapshot_links'::regclass
                  AND NOT tgisinternal
                """
            ).fetchall()
        }
        required = {
            "prediction_feature_snapshot_links_validate",
            "prediction_feature_snapshot_links_no_update",
            "prediction_feature_snapshot_links_no_truncate",
        }
        if not required.issubset(triggers):
            raise RuntimeError("V2_PREDICTION_FEATURE_LINK_TRIGGERS_MISSING")
        count = int(conn.execute(
            "SELECT COUNT(*) FROM prediction_feature_snapshot_links"
        ).fetchone()[0])
        if count != 0:
            raise RuntimeError("V2_PREDICTION_FEATURE_LINK_TABLE_NOT_EMPTY_AFTER_MIGRATION")
        after = _baseline(dsn)
        if after != baseline:
            raise RuntimeError("V2_FEATURE_LINK_MIGRATION_CHANGED_EXISTING_EVIDENCE")
        return {
            "schema_migrations":len(versions),
            "prediction_feature_snapshot_links":count,
            "append_only_triggers":sorted(required),
            "preserved_baseline":after,
        }


def run(*, apply: bool=False) -> dict[str, object]:
    dsn=os.environ.get("DATABASE_URL","")
    validate_staging_dsn_target(dsn)
    if urlsplit(dsn).hostname != EXPECTED_HOST:
        raise PermissionError("V2_FEATURE_LINK_MIGRATION_HOST_NOT_ALLOWLISTED")
    manifest=load_manifest()
    versions=[item[0] for item in manifest]
    if not versions or versions[-1] != PENDING[0]:
        raise RuntimeError("V2_FEATURE_LINK_MIGRATION_NOT_LAST_IN_MANIFEST")
    dry=migrate(dsn,dry_run=True)
    if dry["applied"] != versions[:-1] or dry["pending"] != PENDING:
        raise RuntimeError("V2_FEATURE_LINK_MIGRATION_PRECONDITION_FAILED")
    baseline=_baseline(dsn)
    if not apply:
        return {
            "status":"DRY_RUN_READY",
            "database":dry["database"],
            "user":dry["user"],
            "applied":dry["applied"],
            "pending":dry["pending"],
            "baseline":baseline,
            "writes_performed":False,
        }
    if os.environ.get("VELTRIX_ENABLE_PHASE5_PREDICTION_FEATURE_LINK_MIGRATION") != "YES":
        raise PermissionError("V2_FEATURE_LINK_MIGRATION_EXPLICIT_GUARD_REQUIRED")
    applied=migrate(dsn,dry_run=False)
    verified=_verify(dsn,baseline)
    return {
        "status":"APPLIED_AND_VERIFIED",
        "database":applied["database"],
        "user":applied["user"],
        "applied_now":applied["applied_now"],
        "verification":verified,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    import json
    print(json.dumps(run(apply=args.apply),sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
