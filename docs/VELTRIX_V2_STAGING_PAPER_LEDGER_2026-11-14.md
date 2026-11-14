# VELTRIX Phase 5 — Staging paper ledger persistence

Date: 2026-11-14

## Why this migration exists

The prospective paper ledger currently has an append-only JSONL adapter. A GitHub Actions runner is ephemeral, and the repository is public. Raw provider responses and individual shadow predictions must not be uploaded as public workflow artifacts. This migration provides a durable staging-only event store without exposing prediction records.

## Migration 0005

`db/migrations/0005_prospective_paper_ledger.sql` creates `paper_ledger_events` with:

- Per-ledger monotonic sequence.
- Event types `PREDICTION`, `SHADOW_PREDICTION`, `SETTLEMENT`.
- Exact recorded-at ISO string preservation.
- JSONB immutable event payload.
- Previous-event SHA-256 and event SHA-256.
- Unique ledger/sequence and ledger/event-hash constraints.
- One prediction per ledger/fixture/model and one settlement per ledger/fixture/model.
- Database triggers rejecting UPDATE, DELETE and TRUNCATE.
- No historical prediction backfill.

The database does not recompute the event hash; the application adapter reconstructs and verifies the complete chain before every append.

## PostgreSQL adapter

`veltrix_v2/ledger/postgres_store.py`:

- Read-only load verifies the entire hash chain.
- Writes require explicit `write_enabled=True`.
- Staging writes require the exact Neon staging database, direct host and `neondb_owner` role.
- Local integration tests have a separate explicit test-only allowlist.
- Advisory transaction locks serialize concurrent appenders.
- Duplicate fixture/model predictions are rejected by both application and database constraints.
- No production target is permitted.

## Migration workflow

`.github/workflows/phase5-staging-paper-ledger-migration.yml` is manual-only. Its `apply` input defaults to false. The script first requires migrations 0001–0004 applied and 0005 as the sole pending migration. An explicit apply additionally requires the internal guard variable and exact staging target.

After apply, it verifies:
- Full migration checksums.
- The new table, append-only triggers and unique indexes.
- Zero paper ledger rows immediately after schema creation.
- Existing fixture, source-observation, provider-response and capture-evidence counts are unchanged.

No production database, website, Telegram, schedule or deployment is touched.

## Next integration

The manual 5Dollar capture workflow will use this adapter when its `persist_staging` input is true. Before that workflow can run with staging persistence, migration 0005 must be reviewed and manually applied to staging. The capture workflow uploads only an aggregate summary; raw response bytes and individual predictions remain in the guarded staging store.
