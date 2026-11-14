# VELTRIX 2.0 — Read-only staging coverage audit CLI

Date: 2026-11-14

## Purpose

`scripts/phase5_staging_coverage_audit.py` executes the existing fixture/observation coverage SELECT statements, normalizes them through `persisted_coverage_adapter`, and reports competition-by-domain coverage using the pure coverage auditor.

It does not import provider data, create manifests, update rows, migrate schemas, or persist reports.

## Safety controls

- Dry-run is the default. Without `--execute`, the script prints the intended staging target and does not read a DSN or open a connection.
- The only accepted direct database target is the exact Neon staging hostname and `veltrix_football_staging` database.
- Pooled hostnames and every other host/database are rejected before connection.
- Requires the explicit `VELTRIX_STAGING_DATABASE_URL` environment variable only after `--execute`.
- After connecting, verifies `current_database()` and `current_user` against the staging allowlist.
- Starts a transaction with `SET TRANSACTION READ ONLY` before executing any identity or coverage query.
- Applies a 15-second statement timeout.
- Reuses only validated SELECT-only SQL templates.
- Does not print the DSN, username password or connection string.
- Report is diagnostic; it does not certify model quality or authorize publication.

## Usage

Dry-run:

```bash
python scripts/phase5_staging_coverage_audit.py
```

Explicit read-only staging audit:

```bash
VELTRIX_STAGING_DATABASE_URL="$VELTRIX_STAGING_DATABASE_URL" \
  python scripts/phase5_staging_coverage_audit.py --execute
```

Optional fixed evaluation cutoff:

```bash
python scripts/phase5_staging_coverage_audit.py \
  --execute --as-of 2026-11-14T12:00:00Z
```

Requires psycopg 3 in the execution environment. No dependency is imported at module load time; offline unit tests do not need a database driver.

## Output

The JSON report includes:
- as-of timestamp
- accepted fixture rows
- eligible evidence rows
- rejected fixture/observation row counts
- unsupported data types
- each competition and data domain's target count, eligible count, ratio, missing fixture count, rejected evidence count and contributing providers

Missing or incomplete rights, timestamps, capture-manifest linkage, item hashes or point-in-time flags remain ineligible. No values are imputed.

## Operational boundary

This script is designed for a manually invoked, read-only staging audit. It is not wired to a schedule or production runtime. Do not point it at production or change the target allowlist without a separate reviewed change.
