# VELTRIX FOOTBALL 2.0 — Legacy Preservation & Migration Inventory

Status: initial inventory from repository documentation and prior project records. This is not a completed database audit.

## Known repository

- GitHub: https://github.com/Nexora-Apparel/veltrix-football
- Default branch: `main`
- V2 working branch: `v2/foundation`
- Production data branch: `command-data` (preserve; do not write during foundation work)

## Known provider configuration (secret names only)

- `FIVEDOLLARFOOTBALL_API_KEY` — primary fixture/recent-results provider.
- `THE_ODDS_API_KEY` — supplemental bookmaker odds.
- `ODDSPAPI_API_KEY` — optional odds enrichment.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET` — delivery configuration.
- InferSports is disabled by default pending actual market coverage.
- API-Football/API-Sports is not an active runtime dependency. Do not use `API_FOOTBALL_KEY` in V2.

No secret values belong in this document, repository files, logs or reports.

## Known legacy components

- `app/live_predictions.py` — legacy fixture-to-prediction pipeline; includes team-name normalization, historical CSV loading, competition mapping, Elo/Poisson paths and fallback/prior behaviour. Treat as untrusted until reviewed.
- `app/provider_adapters.py` — provider adapters, normalization and odds retrieval.
- `app/oddspapi_odds.py` and `scripts/enrich_oddspapi_odds.py` — optional OddsPapi enrichment.
- `scripts/import_open_dataset` — historical dataset import.
- GitHub Actions daily pipeline and Telegram recovery workflows.
- Website/dashboard and Telegram commands consuming published report data.

## Known historical-data evidence

Repository documentation records an open historical dataset import of 70,444 completed matches across 38 competition codes from 2020-01-01 through 2026-10-24, with one malformed row skipped. This count must be independently re-verified against the actual current artifact/database before migration.

Prior reports also recorded incomplete historical date coverage and a small prospective paper ledger. Those records must be retained with their original model/version provenance; they must not be mixed with V2 paper results.

## Required audit before migration

- Enumerate Neon projects, branches, databases, schemas, tables, row counts, indexes and migration history.
- Identify the exact production database and its write paths.
- Inventory `command-data` artifacts and immutable report snapshots.
- Inventory GitHub Actions workflows, schedules, secrets by name only, environment protections and deployment targets.
- Inventory Vercel projects, domains, environment-variable names and production/preview branch mappings without revealing values.
- Verify backup/export availability and perform a read-only restore test where supported.
- Reconcile fixture, provider-source, historical-match, forecast, quote, paper-ledger and report counts.
- Identify model versions and training cutoffs for every retained forecast.
- Mark legacy predictions as V1 and never silently relabel them as V2.

## Migration policy

1. Read-only inspection first.
2. Create and verify a backup/export before any data copy.
3. Build an additive V2 schema in an isolated Neon branch or database.
4. Copy records with original IDs and provenance; never overwrite source records.
5. Record source table, source primary key, migration batch, checksum and migration timestamp.
6. Reconcile counts and checksums; quarantine conflicts.
7. Keep V1 as the production rollback target until V2 passes acceptance.
8. Do not delete legacy tables, branches, artifacts, secrets or deployments as part of the rebuild.

## Open audit items

- Exact Neon project ID, branch IDs and production database/schema: not yet inspected.
- Exact Vercel project IDs, domains and environment mapping: not yet inspected.
- Current GitHub Actions workflow inventory: not yet inspected.
- Current database row counts and backups: not yet inspected.
- Whether the current production deployment is reading `main`, an alternate branch or generated command-data: not yet inspected.
