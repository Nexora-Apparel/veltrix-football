"""Explicit, read-only Neon staging coverage audit CLI.

No connection is opened unless --execute is supplied. The DSN must target the
single allowlisted staging host/database; the session enforces a read-only
transaction and a bounded statement timeout before running SELECT-only SQL.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from urllib.parse import urlsplit

from veltrix_v2.data.competition_coverage import audit_competition_coverage
from veltrix_v2.data.coverage_sql import (
    FIXTURE_COVERAGE_SQL,
    OBSERVATION_COVERAGE_SQL,
    validate_read_only_coverage_sql,
)
from veltrix_v2.data.persisted_coverage_adapter import adapt_persisted_coverage_rows
from veltrix_v2.data.provider_registry import DataDomain


_ALLOWED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
_ALLOWED_DATABASE = "veltrix_football_staging"


def parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("AS_OF_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("AS_OF_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed


def validate_staging_dsn_target(dsn: str) -> None:
    if not isinstance(dsn, str) or not dsn.strip():
        raise ValueError("STAGING_DSN_MISSING")
    parsed = urlsplit(dsn)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != _ALLOWED_HOST
        or parsed.path.lstrip("/") != _ALLOWED_DATABASE
    ):
        raise PermissionError("STAGING_DSN_TARGET_NOT_ALLOWLISTED")


def _rows_as_dicts(cursor) -> list[dict[str, object]]:
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def build_coverage_summary(inputs, *, as_of: datetime) -> dict[str, object]:
    report = audit_competition_coverage(
        inputs.fixtures,
        inputs.evidence,
        domains=tuple(DataDomain),
        as_of=as_of,
    )
    return {
        "as_of": as_of.isoformat(),
        "fixture_rows": len(inputs.fixtures),
        "eligible_evidence_rows": len(inputs.evidence),
        "rejected_fixture_rows": inputs.rejected_fixture_rows,
        "rejected_observation_rows": inputs.rejected_observation_rows,
        "unsupported_data_types": list(inputs.unsupported_data_types),
        "coverage": [
            {
                "competition_id": row.competition_id,
                "domain": row.domain.value,
                "target_fixtures": row.target_fixture_count,
                "eligible_fixtures": row.eligible_fixture_count,
                "coverage_ratio": round(row.coverage_ratio, 6),
                "missing_fixture_count": len(row.missing_fixture_ids),
                "rejected_evidence_count": row.rejected_evidence_count,
                "contributing_providers": list(row.contributing_providers),
            }
            for row in report.domains
        ],
        "certification_notice": (
            "Coverage is an evidence diagnostic only; it does not certify model "
            "performance or authorize publication."
        ),
    }


def run_read_only_audit(dsn: str, *, as_of: datetime) -> dict[str, object]:
    validate_staging_dsn_target(dsn)
    validate_read_only_coverage_sql()

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PSYCOPG3_REQUIRED_FOR_STAGING_AUDIT") from exc

    with psycopg.connect(dsn, autocommit=False) as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '15000ms'")
            identity = connection.execute(
                "SELECT current_database(), current_user"
            ).fetchone()
            if identity != (_ALLOWED_DATABASE, "neondb_owner"):
                raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")

            fixture_rows = _rows_as_dicts(connection.execute(FIXTURE_COVERAGE_SQL))
            observation_rows = _rows_as_dicts(connection.execute(OBSERVATION_COVERAGE_SQL))
            inputs = adapt_persisted_coverage_rows(fixture_rows, observation_rows)
            result = build_coverage_summary(inputs, as_of=as_of)
            result["database"] = _ALLOWED_DATABASE
            result["role"] = "neondb_owner"
            result["query_mode"] = "READ_ONLY"
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only VELTRIX staging coverage audit")
    parser.add_argument("--execute", action="store_true",
                        help="connect to the allowlisted staging DB and run SELECT-only audit")
    parser.add_argument("--as-of", default=None,
                        help="timezone-aware ISO-8601 cutoff; defaults to current UTC")
    args = parser.parse_args()
    as_of = parse_as_of(args.as_of)

    if not args.execute:
        print(json.dumps({
            "mode": "DRY_RUN",
            "would_connect": False,
            "target": _ALLOWED_DATABASE,
            "host": _ALLOWED_HOST,
            "as_of": as_of.isoformat(),
            "instruction": "Pass --execute to run the guarded read-only audit.",
        }, indent=2))
        return 0

    dsn = os.environ.get("VELTRIX_STAGING_DATABASE_URL", "")
    result = run_read_only_audit(dsn, as_of=as_of)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
