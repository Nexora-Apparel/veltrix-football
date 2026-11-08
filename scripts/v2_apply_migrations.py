"""Fail-closed, checksummed migration runner for the isolated V2 Neon database."""
from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

EXPECTED_DATABASE = "veltrix_football_v2"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "v2"
LOCK_NAME = "veltrix-football-v2-schema"


def validate_database_dsn(dsn: str, *, expected_database: str = EXPECTED_DATABASE) -> None:
    """Reject non-Neon, non-V2 or non-TLS connection targets before connecting."""
    if not dsn or not dsn.strip():
        raise ValueError("VELTRIX_V2_DATABASE_URL_REQUIRED")
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("V2_DATABASE_URL_MUST_USE_POSTGRESQL")
    if not parsed.hostname or not parsed.hostname.lower().endswith(".neon.tech"):
        raise ValueError("V2_DATABASE_HOST_MUST_BE_NEON")
    database = unquote(parsed.path.lstrip("/").split("/", 1)[0])
    if database != expected_database or expected_database != EXPECTED_DATABASE:
        raise ValueError("V2_DATABASE_NAME_MUST_MATCH_APPROVED_TARGET")
    sslmode = parse_qs(parsed.query).get("sslmode", [])
    if not sslmode or sslmode[0] not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("V2_DATABASE_SSLMODE_MUST_REQUIRE_TLS")


def apply_sql_migration(connection, *, migration_version: str, sql: str,
                        checksum_sha256: str) -> bool:
    """Apply one migration once, under a transaction-scoped advisory lock."""
    if not migration_version or not migration_version.strip():
        raise ValueError("MIGRATION_VERSION_REQUIRED")
    actual = sha256(sql.encode("utf-8")).hexdigest()
    if actual != checksum_sha256:
        raise ValueError("MIGRATION_CHECKSUM_INPUT_MISMATCH")
    with connection.transaction():
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_NAME,))
            cur.execute("""CREATE TABLE IF NOT EXISTS v2_schema_migrations (
                migration_version TEXT PRIMARY KEY,
                checksum_sha256 CHAR(64) NOT NULL,
                applied_at_utc TIMESTAMPTZ NOT NULL,
                database_name TEXT NOT NULL
            )""")
            cur.execute(
                "SELECT checksum_sha256 FROM v2_schema_migrations WHERE migration_version=%s",
                (migration_version,),
            )
            existing = cur.fetchone()
            if existing:
                if existing[0].strip() != checksum_sha256:
                    raise ValueError("APPLIED_MIGRATION_CHECKSUM_MISMATCH")
                return False
            # psycopg 3 uses simple-query mode for multi-statement migration files.
            cur.execute(sql, prepare=False)
            cur.execute("""INSERT INTO v2_schema_migrations
                (migration_version,checksum_sha256,applied_at_utc,database_name)
                VALUES (%s,%s,now(),current_database())""",
                (migration_version, checksum_sha256))
    return True


def apply_all_migrations(connection, migrations_dir: Path = MIGRATIONS_DIR) -> tuple[str, ...]:
    applied = []
    for path in sorted(migrations_dir.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        checksum = sha256(sql.encode("utf-8")).hexdigest()
        if apply_sql_migration(connection, migration_version=path.stem,
                                sql=sql, checksum_sha256=checksum):
            applied.append(path.stem)
    return tuple(applied)


def main() -> int:
    dsn = os.environ.get("VELTRIX_V2_DATABASE_URL", "")
    if os.environ.get("VELTRIX_V2_STORAGE_APPROVED") != "true":
        raise SystemExit("BLOCKED: set VELTRIX_V2_STORAGE_APPROVED=true after verifying the V2-only target")
    validate_database_dsn(dsn)
    import psycopg

    with psycopg.connect(dsn, connect_timeout=10) as connection:
        with connection.cursor() as cur:
            cur.execute("SELECT current_database()")
            actual_database = cur.fetchone()[0]
        if actual_database != EXPECTED_DATABASE:
            raise SystemExit("BLOCKED: connected database does not match the approved V2 database name")
        applied = apply_all_migrations(connection)
    print("V2_SCHEMA_MIGRATIONS_APPLIED=" + (",".join(applied) if applied else "NONE_ALREADY_CURRENT"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
