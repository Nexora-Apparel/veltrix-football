#!/usr/bin/env python3
"""Inspect one Telegram delivery claim on the allowlisted staging database.

Read-only only. This command cannot send, retry, authorize or mutate Telegram
delivery or reconciliation records.
"""
from __future__ import annotations

import argparse
import json
import os

from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target
from veltrix_v2.reporting.reconciliation_read import PostgresTelegramReconciliationReader


def inspect(dsn: str, idempotency_key: str) -> dict[str, object]:
    validate_staging_dsn_target(dsn)
    import psycopg

    reader = PostgresTelegramReconciliationReader(
        lambda: psycopg.connect(dsn, autocommit=False)
    )
    return reader.inspect(idempotency_key)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--idempotency-key", required=True)
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise SystemExit("DATABASE_URL_REQUIRED")
    result = inspect(dsn, args.idempotency_key)
    print(json.dumps(result, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
