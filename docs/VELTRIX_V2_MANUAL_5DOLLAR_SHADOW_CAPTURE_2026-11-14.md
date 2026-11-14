# VELTRIX Phase 5 — Manual 5Dollar shadow capture

Date: 2026-11-14

## Purpose

A manually triggered, bounded pipeline to collect first-observed 5Dollar result snapshots, map upcoming fixtures through the verified crosswalk registry, run the independent results-only Poisson challenger, and attempt rights-gated prospective shadow admission.

This workflow does not publish predictions, send Telegram messages, activate schedules, settle selections, or deploy the website.

## Trigger and request limits

- `workflow_dispatch` only; no cron or push trigger.
- Uses only the seven competition IDs already present in the approved source scope and crosswalk registry.
- One finished-results page and one scheduled-fixtures page per entitled competition.
- Hard cap: 14 provider requests per run.
- 3.1-second minimum request-start spacing; no retries.
- 90-day maximum finished-results window; 14-day maximum upcoming window.
- Page size 100; no pagination. `has_more=true` is recorded as partial coverage.
- 403 means that competition is not entitled; it is skipped without retry.
- 401, 429, network failures or malformed responses stop the run.
- If provider quota headers show less remaining quota than the bounded plan requires, the run stops instead of consuming the remaining quota.

GOAL API and StrikerAPI are not referenced by this workflow.

## Data and temporal semantics

- Staging crosswalks are built from the 2,496 existing 5Dollar observations already linked to canonical fixtures.
- Fixture, team and competition mappings must be one-to-one; ambiguous mappings fail closed.
- Crosswalks are valid only from the verification instant forward. They are never backdated.
- New scheduled targets use canonical team and competition IDs; the target fixture ID remains provider-namespaced until a canonical fixture row exists.
- Finished results are captured with the exact page response bytes, response hash, request/retrieval/recording clocks, capture manifest and item evidence hashes.
- Newly observed result snapshots are explicitly non-PIT-certified. Retrieval time is not relabelled as provider publication time.
- Rows without a valid crosswalk, rights approval, source hash or temporal evidence are rejected from model history.
- Missing history remains missing; no fallback prior or fabricated feature is introduced.

## Rights and persistence

- Source approval status is reconstructed from append-only approval status events at use time.
- Collection rights are rechecked immediately before each provider request.
- Storage and model-training rights are rechecked before result evidence persistence and shadow admission.
- The optional `persist_staging` input defaults to false.
- When enabled, raw result capture evidence is persisted only to the allowlisted Neon staging database through the guarded evidence persistence adapter. The script rejects any other database, host or role.
- Scheduled target page snapshots are retained only in the runner workspace and are not uploaded.
- The runner's detailed raw responses and individual predictions are not uploaded as GitHub artifacts.
- The only uploaded artifact is `public_summary.json`, containing aggregate counts and release-lock status; it contains no fixture IDs, raw payloads, odds, probabilities or individual predictions.
- When `persist_staging=true`, result evidence is persisted through the guarded evidence writer and the admitted shadow-prediction batch is appended atomically to the PostgreSQL paper ledger. Migrations 0005–0008 must already be applied to staging; the run fails closed if migration 0008 is absent.
- The JSONL ledger remains a runner-local audit copy in both modes. With staging persistence disabled, it is not durable between runs; with staging persistence enabled, PostgreSQL is the durable ledger.
- The PostgreSQL batch uses one transaction and one ledger-scoped advisory lock. Duplicate detection happens only after acquiring that lock, so overlapping runs cannot both classify the same fixture/model pair as new. Existing fixture/model pairs and duplicates within the same batch are skipped; new predictions append atomically. An invalid prediction rolls back the entire new batch, preventing partial forecast sets.
- The aggregate audit summary records the number of skipped duplicate predictions and whether the persisted hash chain was verified.
- The uploaded public summary is constructed from an explicit field allowlist. It excludes fixture IDs, raw-response hashes, ledger hashes, odds, probabilities, API credentials and detailed per-fixture diagnostics.

## Model and release boundaries

- Results-only Poisson challenger; up to 25 upcoming targets.
- No xG, lineup, injury, player-statistics or odds features are fabricated.
- Shadow admission requires exact target identity, manifest-linked eligible observations, source approval and model/feature hashes.
- Value betting remains locked.
- Settlement remains locked unless BENCHMARKING rights are approved.
- All forecasts remain non-publishable shadow evidence.
- No production database writes, migrations, Telegram delivery, schedule activation, public predictions or Vercel deployments.

## Manual blocker

GitHub only exposes `workflow_dispatch` for workflows present on the repository's default branch. This draft workflow cannot be run until it has passed review and is merged. It is intentionally not merged or activated by this change.
