# VELTRIX FOOTBALL 2.0 — Prospective evaluation ledger

## Purpose

Persist free-provider snapshots, generated forecast batches, fixture-level predictions, independently sourced settlements and chronological evaluation summaries. This is required to accumulate prospective evidence without relying on reconstructed historical timestamps.

## Isolation

- Uses a dedicated `veltrix_eval` PostgreSQL schema.
- Has its own migration stream under `db/migrations/free_first/`.
- Does not depend on Odds API migrations 0005–0007.
- Does not alter existing `public` tables or the Phase 3/4 migration history.
- The migration is prepared for isolated PostgreSQL 16/18 tests only; it has not been applied to Neon staging or production.

## Tables

- `capture_runs`: immutable bounded free-provider capture summary, scope and report hash.
- `fixture_snapshots`: append-only provider fixture snapshots with exact IDs, kickoff, retrieval/availability timestamps, rights approval and payload hash.
- `prediction_batches`: immutable cutoff, model configuration and source-manifest identity. Publication lock is enforced in SQL.
- `prediction_records`: fixture-level 1X2, BTTS and O/U forecasts, expected goals, evidence counts and model provenance. SQL rejects publishable=true.
- `result_settlements`: append-only result versions with separate availability, recorded and settlement timestamps.
- `evaluation_runs`: immutable walk-forward metrics and dataset/model hashes. Publication lock is enforced in SQL.

## Data integrity

- All evidence tables reject UPDATE and DELETE.
- Provider and fixture identity are explicit and never merged by display name.
- Every source payload is represented by a SHA-256, not copied into this ledger.
- Prediction targets must be retrieved no later than the forecast cutoff and kick off strictly after it.
- 1X2 probabilities must sum to one within a strict tolerance.
- Batch size is capped at 25.
- Paid requests must remain zero.
- Prediction rows are hard-constrained to publishable=false.

## Next integration

After PostgreSQL 16/18 tests pass, implement a parameterized append-only store with exact idempotent replay. Only then consider applying this separate migration to the dedicated Neon staging branch. Production remains untouched.
