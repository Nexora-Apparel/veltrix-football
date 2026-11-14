# VELTRIX Phase 5 — Staging paper ledger persistence

Date: 2026-11-14

## Why this migration exists

The prospective paper ledger currently has an append-only JSONL adapter. A GitHub Actions runner is ephemeral, and the repository is public. Raw provider responses and individual shadow predictions must not be uploaded as public workflow artifacts. This migration provides a durable staging-only event store without exposing prediction records.

## Migration 0008

`db/migrations/0008_prospective_paper_ledger.sql` creates `paper_ledger_events` with:

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

`.github/workflows/phase5-staging-paper-ledger-migration.yml` is manual-only. Its `apply` input defaults to false. The script now gates the combined staging sequence 0005–0009: provider-credit reservation, quota evidence, capture-state events, the prospective paper ledger, and durable Telegram delivery claims. The full sequence must be pending exactly; it is not a partial migration. Migrations 0005–0007 add the previously designed provider-credit reservation, quota-evidence and capture-state schemas; they do not dispatch providers or consume credits. An explicit apply additionally requires the internal guard variable and exact staging target.

After apply, it verifies:
- Full migration checksums.
- The new table, append-only triggers and unique indexes.
- Zero paper ledger rows immediately after schema creation.
- Existing fixture, source-observation, provider-response and capture-evidence counts are unchanged.

No production database, website, Telegram, schedule or deployment is touched.

## Next integration

The manual 5Dollar capture workflow will use this adapter when its `persist_staging` input is true. Before capture or Telegram persistence can be enabled, migrations 0005–0009 must be reviewed and manually applied to staging. The capture workflow uploads only an aggregate summary; raw response bytes and individual predictions remain in the guarded staging store.


## Target snapshot linkage

The 5Dollar admission path stores both canonical competition identity and provider competition identity. Rights are evaluated against the provider competition ID in the source approval scope; canonical competition IDs remain the model and reporting identity.

Each 5Dollar shadow event now includes target provider/source/fixture IDs, provider competition ID, per-fixture payload SHA-256, raw scheduled-page response SHA-256 and capture-manifest SHA-256. The ledger chain verifier rejects 5Dollar events missing any of these provenance fields. This allows the target snapshot to be linked directly to the immutable `provider_responses`, `capture_manifests` and `provider_capture_requests` records in staging.


## Migration 0009 — Telegram delivery claims

`db/migrations/0009_telegram_delivery_claims.sql` creates a durable unique claim keyed by the SHA-256 of report ID, report hash and destination. Only the destination hash is stored; raw chat IDs are not persisted.

- Claims are inserted before any Telegram request.
- Concurrent inserts for the same key produce exactly one claim winner.
- State transitions are limited to `CLAIMED → SENT` or `CLAIMED → OUTCOME_UNKNOWN`.
- Terminal claims cannot be updated, deleted or truncated.
- `SENT` rows retain Telegram message IDs.
- `OUTCOME_UNKNOWN` is terminal for automatic dispatch and requires manual reconciliation.

The migration has not been applied to Neon staging. PostgreSQL 16/18 integration tests are required before any staging apply.
