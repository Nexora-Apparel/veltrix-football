#!/usr/bin/env python3
"""Read-only Neon schema acceptance check for VELTRIX FOOTBALL.

Usage:
  DATABASE_URL='postgresql://…' python scripts/neon_acceptance.py

The script never writes, migrates, truncates, or imports data. It starts a
read-only transaction and verifies the persistent foundation's catalog shape.
Connection strings and credentials are never printed.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlsplit
from typing import Any

try:
    import psycopg
except ImportError as exc:  # pragma: no cover - exercised in deployment env
    raise SystemExit("Missing dependency: install requirements.txt (psycopg[binary])") from exc


EXPECTED = {
    "public_tables": 11,
    "primary_keys": 11,
    "foreign_keys": 7,
    "unique_constraints": 5,
    "check_constraints": 83,
    "indexes": 22,
    "applied_migrations": 1,
    "passing_reconciliation_audits": 1,
}


def fetch_one(conn: psycopg.Connection[Any], query: str) -> int:
    row = conn.execute(query).fetchone()
    if row is None:
        raise RuntimeError("Acceptance query returned no row")
    return int(row[0])


PRODUCTION_NEON_HOSTS = {
    "ep-raspy-butterfly-bcuuxx6c.c-16.us-east-1.aws.neon.tech",
    "ep-raspy-butterfly-bcuuxx6c-pooler.c-16.us-east-1.aws.neon.tech",
}


def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("BLOCKED: DATABASE_URL is not configured", file=sys.stderr)
        return 2

    host = urlsplit(dsn).hostname
    if not host or host.lower() not in PRODUCTION_NEON_HOSTS:
        print("BLOCKED: DATABASE_URL does not point to the verified production Neon endpoint", file=sys.stderr)
        return 2

    report: dict[str, Any] = {"target": "verified production Neon endpoint", "read_only": True}
    try:
        # read_only=True enforces PostgreSQL transaction read-only mode.
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute("SET LOCAL statement_timeout = '15s'")
                report["transaction_read_only"] = conn.execute(
                    "SHOW transaction_read_only"
                ).fetchone()[0] == "on"
                report["server_version"] = conn.execute(
                    "SHOW server_version"
                ).fetchone()[0]
                report["database"] = conn.execute(
                    "SELECT current_database()"
                ).fetchone()[0]
                if report["database"] != "veltrix-football":
                    raise RuntimeError("DATABASE_URL is not connected to the veltrix-football database")

                queries = {
                    "public_tables": """
                        SELECT count(*) FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    """,
                    "primary_keys": """
                        SELECT count(*) FROM information_schema.table_constraints
                        WHERE constraint_schema = 'public' AND constraint_type = 'PRIMARY KEY'
                    """,
                    "foreign_keys": """
                        SELECT count(*) FROM information_schema.table_constraints
                        WHERE constraint_schema = 'public' AND constraint_type = 'FOREIGN KEY'
                    """,
                    "unique_constraints": """
                        SELECT count(*) FROM information_schema.table_constraints
                        WHERE constraint_schema = 'public' AND constraint_type = 'UNIQUE'
                    """,
                    "check_constraints": """
                        SELECT count(*) FROM information_schema.table_constraints
                        WHERE constraint_schema = 'public' AND constraint_type = 'CHECK'
                    """,
                    "indexes": """
                        SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'
                    """,
                    "applied_migrations": """
                        SELECT count(*) FROM public.schema_migrations
                    """,
                    "passing_reconciliation_audits": """
                        SELECT count(*) FROM public.reconciliation_audits
                        WHERE status = 'PASS'
                    """,
                }
                observed = {name: fetch_one(conn, sql) for name, sql in queries.items()}
                report["observed"] = observed
                report["expected"] = EXPECTED
                report["checks"] = {
                    name: observed[name] == expected
                    for name, expected in EXPECTED.items()
                }
                report["passed"] = (
                    report["transaction_read_only"]
                    and all(report["checks"].values())
                )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    except Exception as exc:
        # Deliberately omit exception text: drivers can include connection data.
        print(json.dumps({
            "passed": False,
            "error_type": type(exc).__name__,
            "error": "Neon acceptance query failed; diagnostic text withheld to protect credentials.",
        }, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
