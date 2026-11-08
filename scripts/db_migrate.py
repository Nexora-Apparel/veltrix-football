"""Apply ordered SQL migrations with immutable SHA-256 history checks.

Requires psycopg 3 and DATABASE_URL. This command never creates a database,
never changes a connection target, and refuses checksum drift.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
from pathlib import Path

MIGRATION_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"
VERSION_RE = re.compile(r"^(\d{4}_[a-z0-9_]+)\.sql$")


def load_manifest(directory: Path = MIGRATION_DIR) -> list[tuple[str, str, str]]:
    entries = []
    for path in sorted(directory.glob("*.sql")):
        if not VERSION_RE.fullmatch(path.name):
            raise ValueError(f"Invalid migration filename: {path.name}")
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        entries.append((path.stem, checksum, raw.decode("utf-8")))
    versions = [entry[0] for entry in entries]
    if len(versions) != len(set(versions)):
        raise ValueError("Duplicate migration versions")
    return entries


def migrate(database_url: str, directory: Path = MIGRATION_DIR, dry_run: bool = False) -> dict:
    if not database_url:
        raise ValueError("DATABASE_URL is required")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install psycopg[binary]>=3.2,<4 before running migrations") from exc

    manifest = load_manifest(directory)
    applied_count = 0
    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, current_setting('server_version_num')")
            db_name, db_user, server_version = cur.fetchone()
            if int(server_version) < 160000:
                raise RuntimeError(f"PostgreSQL 16+ required; server_version_num={server_version}")
            if not db_name or "veltrix" not in db_name.lower():
                raise RuntimeError(f"Refusing unexpected database target: {db_name!r}")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('veltrix-football-migrations'))")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum CHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("SELECT version, checksum FROM schema_migrations ORDER BY version")
            history = dict(cur.fetchall())
            expected = {version: checksum for version, checksum, _ in manifest}
            unexpected = sorted(set(history) - set(expected))
            if unexpected:
                raise RuntimeError(f"Database contains migrations absent from manifest: {unexpected}")
            drift = [v for v in history if history[v].strip() != expected[v]]
            if drift:
                raise RuntimeError(f"Migration checksum mismatch: {drift}")
            pending = [entry for entry in manifest if entry[0] not in history]
            if dry_run:
                conn.rollback()
                return {"database": db_name, "user": db_user, "pending": [x[0] for x in pending], "applied": sorted(history)}
            for version, checksum, sql in pending:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                    (version, checksum),
                )
                applied_count += 1
        conn.commit()
    return {"database": db_name, "user": db_user, "applied_now": applied_count, "manifest_count": len(manifest)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(migrate(os.environ.get("DATABASE_URL", ""), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
