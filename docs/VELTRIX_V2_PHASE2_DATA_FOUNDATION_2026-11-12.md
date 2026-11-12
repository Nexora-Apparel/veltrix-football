# VELTRIX FOOTBALL 2.0 — Phase 2: Historical Database and Data Foundation

**Status:** IN PROGRESS — additive provenance schema, source-rights contracts and read-only 365-day acquisition are implemented on `phase2/historical-data-foundation`; CI and the provider dry-run remain to be verified.

## 1. Phase 2 objective

Build one auditable historical-data foundation without reusing the legacy prediction engine. The foundation must preserve exact provider response bytes, immutable source observations, provider entitlement snapshots, source-rights evidence, fixture/result versions, explicit quarantine, import manifests, checkpoints and reconciliation.

Phase 2 does not implement model features, prediction probabilities, calibration, value-bet selection, Telegram publication, production deployment or scheduling.

## 2. Existing infrastructure and data inventory

### 2.1 Neon application database

Neon project: `VELTRIXFOOTBALL` (`withered-sky-75161174`), application database `veltrix-football`, PostgreSQL 18.

The primary branch and existing `veltrix-phase3-import-dry-run` child branch were queried read-only. Both currently have the same 11 application tables from migration `0001_persistent_foundation`:

- `schema_migrations`, `provider_accounts`, `countries`, `competitions`, `teams`, `fixtures`, `fixture_results`, `source_observations`, `import_runs`, `import_checkpoints`, `reconciliation_audits`.

Observed rows in each branch:

| Table | Rows |
|---|---:|
| competitions | 0 |
| countries | 0 |
| teams | 0 |
| fixtures | 0 |
| fixture_results | 0 |
| source_observations | 0 |
| import_runs | 0 |
| import_checkpoints | 0 |
| provider_accounts | 0 |
| reconciliation_audits | 1 |
| schema_migrations | 1 |

The initial schema reconciliation record reports the migration checksum matched, 11 tables, 22 indexes, 7 foreign keys, 11 primary keys, 20 check constraints and 5 unique constraints. The rollback probe passed. The database contains schema and one acceptance audit, not historical match data. No Neon rows were written by this Phase 2 audit.

### 2.2 Existing historical CSV artifact — quarantined

The existing GitHub Actions artifact from run `40524886182`, artifact `12744031006`, was downloaded and inspected without importing it.

- File: `open_historical_matches.csv`
- Rows: 70,444
- Columns: 25
- Divisions: 38
- Date range: 2020-01-01 to 2026-09-03
- Unique teams by name: 921
- Duplicate (division, date, home, away) keys: 0
- Missing dates, teams, full-time scores or result labels: 0
- Full-time result labels matched score-derived outcomes: 100%
- Complete 1X2 odds: 70,378 / 70,444 (99.906%)
- Missing Over/Under 2.5: 21,503 (30.52%)
- Missing half-time scores: 21,484 (30.50%)
- Missing shots/shot-on-target fields: 24,429 (34.68%)
- Missing at least one home/away Elo field: 31,037 (44.06%)
- Sixteen divisions have no record later than 2024-12-08; 22 have records into 2026.

SHA-256: `f26fb9a9ae994ce611e4bed00ae8ec173ecc47123fad825705821a6eb4d5225f`

**Disposition: QUARANTINED — NOT ADMITTED TO V2 TRAINING OR PRODUCTION.** The repository `xgabora/Club-Football-Match-Data` is a wrapper/aggregation source; its match data traces to Football-Data.co.uk and ClubElo. The repository's software licence does not grant rights to the underlying third-party datasets. Football-Data.co.uk's published terms restrict its data to personal/academic research. The data therefore cannot be assumed commercially reusable for the VELTRIX product. The CSV artifact and its hash are preserved as historical evidence; it is not copied into the source repository or V2 database.

The precomputed form/Elo fields also lack source-availability timestamps and must not be treated as point-in-time-safe features.

### 2.3 Existing unmerged architecture branches

- `v2/foundation` contains a separate `v2_*` PostgreSQL schema and storage adapter. Its migration explicitly targets a newly provisioned isolated V2 database. It is **not applied** to the existing `veltrix-football` database and is not merged wholesale, because it would create a second competing source store.
- PR #43 / `phase-3/budget-aware-acquisition-contract` contains legacy `app.*` prediction/value-betting code. It is not merged and must not be reused as the V2 prediction foundation.
- PR #40 was the persistent PostgreSQL base. It is now merged as the Phase 2 schema baseline. The actual Neon schema already matched migration 0001 before this PR was merged.

Phase 2 extends the existing public schema additively rather than creating another database or duplicating the history store.

## 3. Approved Phase 2 sources

### 3.1 5DollarFootballAPI — fixtures and settled results

The Community account was verified on 2026-11-12:
- 300 requests/hour and 20 requests/minute burst;
- seven entitled competitions: Brazil Serie A, Brazil Serie B, England Premier League, France Ligue 1, Germany Bundesliga I, Italy Serie A and Spain La Liga;
- provider documentation describes 12 months of results and odds on Community Access;
- terms last updated October 2026 allow use in commercial websites, apps and models, response caching and public display with linked attribution; raw-feed resale/redistribution is prohibited.

The VELTRIX terms review is recorded in [5Dollar terms review](legal/5dollar-terms-review-2026-11-12.md). Community public display must include **Football data by 5DollarFootballAPI** linked to https://5dollarfootballapi.com.

The Phase 1 90-day qualification verified 786 finished fixtures across the seven competitions. It did not establish the full 365-day account history. The Phase 2 workflow therefore runs one bounded 365-day, read-only history probe with a 40-request cap and 4-second pacing. It does not write to Neon or any production database.

### 3.2 Wyscout open event dataset — historical shot-event source

The published event dataset is licensed CC BY 4.0 and is suitable for a later independent xG model trained from raw shot locations and event context. Its rights review and attribution wording are recorded in [Wyscout CC BY 4.0 review](legal/wyscout-cc-by-4.0-review-2026-11-12.md). The dataset is not imported by Phase 2; its event ingestion and xG model belong to a later phase.

### 3.3 Explicitly excluded

- Legacy Club-Football-Match-Data CSV: source rights unresolved/restrictive; quarantined.
- OpenPlay: upstream WhoScored/Opta provenance and rights unresolved.
- PitchAPI: upstream data provenance and model-training rights unresolved.
- StrikerAPI: latest account check HTTP 402; no free credits; no paid credits authorised.
- GOAL API: latest runner blocked by Cloudflare browser-signature HTTP 403; upstream sports-data rights remain unresolved.
- OddsPapi: provider rights do not expressly grant model training/retention; excluded.
- InferSports: current 1X2/totals discovery only; no verified historical archive or quote timestamp completeness.
- 5Dollar historical odds tick endpoint: HTTP 403 on Community. The sampled market timestamp coverage was 7/77 (9.09%), below the later 98% value-betting gate. The Odds API remains the prospective timestamped odds source.

## 4. Phase 2 storage contract

The existing 11-table schema is extended additively by `0002_historical_provenance.sql`:

- `source_approvals`: versioned source/competition/data-type rights evidence, permitted uses, commercial status, attribution and validity.
- `provider_responses`: exact raw response bytes, request parameters, safe response headers, request ID, quota headers and response SHA-256. Authentication headers and secrets are prohibited.
- `provider_entitlement_observations`: append-only plan, rate-limit, country-pack and competition-access snapshots.
- `source_observations`: append-only per-entity payload, provider response link, source event time, retrieval time, availability basis, rights approval and point-in-time certification flag.
- `fixture_result_versions`: append-only score versions tied to exact source observations and rights approval.
- `sync_watermarks`: compare-and-set incremental sync cursor/version.
- `ingestion_quarantine`: explicit record-level reason codes and resolution evidence.
- Existing `fixtures`, `fixture_results`, `import_runs` and `import_checkpoints` gain provenance, availability, rights, manifest, request-budget and rejection/quarantine fields.

Database triggers reject UPDATE/DELETE against raw provider responses, source observations, rights approvals, entitlement observations and result versions. Corrected evidence is appended as a new version; no raw source record is silently overwritten.

## 5. Point-in-time policy

5Dollar fixture/results do not expose the original result-publication timestamp. For historical target labels only, the parser stores `available_at = kickoff + 4 days` with basis `provider_finished_status_conservative_4d` and `point_in_time_certifiable=false`.

This is an explicitly labelled conservative proxy, not a verified provider publication timestamp. It must not be used to claim exact historical feature availability or to satisfy the point-in-time odds coverage gate. Model-feature eligibility will require a separate source-availability decision in the later feature-engineering phase.

## 6. Phase 2 implementation on this branch

- Additive PostgreSQL migration 0002 with immutable source evidence and explicit rights/provenance.
- Source-approval and rights-evaluation contracts that fail closed.
- Strict 5Dollar fixture/result parser requiring complete pagination metadata, stable provider IDs, timezone-aware kickoff and integer settled scores.
- Batch assessment, duplicate detection, explicit rejected/quarantined outcomes and SHA-256 source manifest.
- PostgreSQL writer targeting the existing `public` schema; writes are disabled by default, require an explicit expected database name, and hard-reject the production database names. Raw responses and observations are append-only; fixture identity conflicts and result conflicts are quarantined.
- Manual 365-day read-only workflow; 40-request hard cap, 4-second pacing, exact seven-competition allowlist, no database writes, sanitized report artifact.
- PostgreSQL 16/18 migration and append-only trigger acceptance.

## 7. Phase 2 acceptance gates

Phase 2 is not complete until all of the following are verified:

1. Migration 0002 applies cleanly after migration 0001 on PostgreSQL 16 and 18; rerunning is idempotent.
2. Database acceptance confirms the exact expected tables/indexes, foreign keys, checksums and five append-only triggers.
3. Unit tests prove rights fail-closed, strict fixture parsing, timezone/score checks, complete pagination, duplicate detection, source-manifest reconciliation, request caps and secret-header rejection.
4. The manual 365-day workflow returns complete pagination for all seven allowlisted competitions, with no duplicate fixture IDs, no missing required identity, valid settled scores and a complete SHA-256 source manifest within 40 requests.
5. The historical CSV remains quarantined; no unapproved source is imported.
6. The PostgreSQL writer is exercised against an isolated PostgreSQL test database or Neon child branch, proving idempotency, atomicity, append-only evidence and conflict quarantine.
7. The primary Neon branch remains unchanged by Phase 2 data import. No production history rows are inserted before the final release gates.

**Safety:** no prediction model or probability code, no production data import, no Vercel deployment, no Telegram delivery, no schedule activation and no value-bet unlocking.
