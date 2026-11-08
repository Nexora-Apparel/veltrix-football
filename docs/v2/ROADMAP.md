
> **Final hardened diagnostics result — 2026-11-08 09:39 UTC:** commit `893e5bc054479d01f82fb7e3c76e1dbf2e343d5e` passed hosted run `42468038418`: **293 passed in 1.40 seconds** with PostgreSQL 16. The reconciliation audit is read-only and covers orphaned fixture source records, missing/unverified/ambiguous active competition and team mappings, missing or mismatched provenance, and duplicate canonical fixture identities. This is CI-fixture acceptance only; no actual V2 source database exists yet. Phase 3 remains open pending dedicated Neon provisioning, provider entitlements/rights, real source import, mapping population, historical reconciliation and backup/restore proof.


> **Diagnostics CI update — 2026-11-08:** the first PostgreSQL-backed reconciliation audit implementation passed run `42467966378` with **292 tests passed**. A subsequent hardening change now detects ambiguous overlapping verified mappings (multiple distinct canonical targets), with an additional PostgreSQL regression test. Latest run `42468038418` for commit `893e5bc054479d01f82fb7e3c76e1dbf2e343d5e` was queued at this update; do not mark the hardened final version green until that run completes.


> **Continuation checkpoint — 2026-11-08 (supersedes older checkpoint values below where they conflict):** V2 branch HEAD at documentation update: `30c3345b19c4bab6580e60be462e7f329cb0f5a8`. Latest completed hosted CI before the new diagnostics: run `42467645029`, commit `254c6d8e3fcc4773ce29f016183662a30157296b`, **289 passed** using a PostgreSQL 16 service container. Read-only PostgreSQL reconciliation diagnostics have now been added for orphaned fixture source records, unverified/missing competition and home/away team mappings, provenance inconsistencies/gaps and duplicate canonical fixture identities. New PostgreSQL integration cases cover clean and deliberately corrupted fixtures and verify the audit does not mutate row counts. CI for the diagnostics commit is pending; do not claim those tests pass until the run completes. `main` remains `05e517af4dcac27507a3c32ebaceee117828df22`; `command-data` remains `f759046a44edcc5a0c69198b4b7183176c2562b5`. No production deployment, provider API call, Neon database creation or migration occurred. Phase 3 remains IN PROGRESS.

# VELTRIX FOOTBALL 2.0 — Master Roadmap and Continuity Contract

**Document type:** Binding project execution roadmap  
**Status:** Active  
**Current working branch:** `v2/foundation`  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Production protection:** `main`, `command-data`, current website, provider credentials, Telegram delivery and production data remain protected.

> This document is the persistent source of truth for VELTRIX FOOTBALL 2.0 across conversations. Any future assistant session working on this project must read this roadmap and the linked V2 architecture documents before making changes. Continue from the recorded phase and verified repository state; do not restart, contradict, or silently relax these decisions.

---

## A. Mission

Build a new, independently validated football prediction system that produces trustworthy, fixture-specific probabilities for 1X2, BTTS and Over/Under markets, with value-bet analysis only after market-specific validation.

The primary objective is forecast integrity and measurable predictive performance—not maximum fixture count, maximum message volume or an arbitrary accuracy claim.

**Core rebuild decision:** retain the existing website, usable API/provider connectivity and credentials, Telegram bot/delivery infrastructure, historical source records and production deployment as protected infrastructure. Rebuild the complete prediction stack from a clean V2 boundary.

V2 is not a refactor of V1. It is a new prediction system behind retained delivery surfaces.

## B. Binding decisions — do not change without explicit project-owner instruction

### B1. What is retained

- Existing website, domain, hosting and user-facing shell.
- Existing provider accounts, API connectivity and credentials where still valid.
- Existing Telegram bot, channel/chat configuration, credentials and message transport.
- Original historical match, odds, result and settlement records, including provider IDs, timestamps and provenance.
- Existing production deployment, `main`, `command-data` and V1 artifacts as read-only audit/rollback references during development.

Retaining an API integration means retaining transport/access only. V2 must build its own adapter normalization, identity mapping, evidence validation and data contracts.

### B2. What is replaced

Rebuild all prediction-related components independently:
- Provider payload normalization and ingestion validation.
- Fixture, competition, team and squad identity resolution.
- Historical data access, quality checks, deduplication and point-in-time snapshots.
- Feature engineering and team-strength estimation.
- Training data construction, temporal splits, model training and selection.
- Every 1X2, BTTS and totals model and probability generator.
- Calibration, uncertainty estimation and confidence methodology.
- Eligibility, value/edge/EV calculation and odds matching.
- Backtesting, walk-forward evaluation, prospective paper tracking and release certification.
- Forecast generation, publication gates and prediction-specific report logic.

No V1 model, feature pipeline, identity matcher, probability generator, calibration routine, value calculator, eligibility implementation or prediction/report logic may be imported or called by V2.

Legacy outputs may be stored for audit and comparison only. They must never become V2 features, priors, labels, calibration inputs, fallbacks or training targets.

### B3. Explicit provider constraint

The API-Football/API-Sports account/key was suspended. The project owner explicitly instructed that `API_FOOTBALL_KEY` must be left alone. Do not read, reveal, rotate, test, change or use it in V2. Current intended provider strategy is 5DollarFootballAPI as primary, The Odds API for supplementary prices and OddsPapi only where coverage is demonstrated. Verify current secret *names and availability* without exposing values before activation. Do not assume credentials are present in Vercel; prior audit found no 5Dollar/Odds/OddsPapi production environment variable names there, while provider secrets may be stored in GitHub Actions.

### B4. Prediction integrity

- No global, neutral, generic, competition-only or copied probability distribution may be published as a fixture-specific forecast.
- Missing, stale, ambiguous, failed or insufficient evidence means WITHHELD—not a fabricated prediction.
- Markets are independently eligible. A valid 1X2 model does not automatically authorize BTTS or totals.
- Past-kickoff, live, postponed, cancelled and completed fixtures cannot receive a pre-match forecast.
- Every published probability must be reproducible from identified source records, identity decisions, point-in-time feature snapshots, model version, training cutoff and calibration version.
- No target accuracy percentage is promised without prospective, independently measured evidence.

### B5. Quota protection

Daily API quotas, GitHub Actions minutes and Vercel build/deployment allowances are scarce resources. Every call, run, backfill, experiment and deployment must have a bounded purpose and stop condition. Batch provider calls, cache results, use incremental sync, reserve quota for the scheduled run, and never run broad historical backfills in a daily report or deployment hook. Batch related commits and avoid unnecessary Vercel previews. Unknown quota is treated as scarce.

---

## C. Current verified project checkpoint

As of 2026-11-06:

- Repository: `Nexora-Apparel/veltrix-football`.
- Isolated branch: `v2/foundation`, created from `main`.
- Production `main` and `command-data` have not been changed by the V2 work recorded here.
- V2 foundation documents, domain contracts, eligibility gate, identity resolver, tests and CI workflow have been created on the isolated branch.
- Verified V2 branch HEAD at the 2026-11-06 execution checkpoint: `966f6479021f9b0f196521146db4573cc2ba56ff`. Earlier `9c6d638` was superseded by subsequent ingestion and audit commits; verify again before editing.
- `main` HEAD remains `05e517af4dcac27507a3c32ebaceee117828df22`; `command-data` HEAD remains `1b735d9f515241583ecd0eb1195d3e2585b8540a`. V2 work remains isolated.
- Hosted V2 CI run `42189655107` passed: **34 tests passed in 0.07 seconds**. The suite now includes a fail-closed source-rights gate that requires verified, hashed terms evidence and checks purpose, commercial-use and public-attribution permissions. Earlier test-only failures were corrected on V2 only.
- Latest V2 preview deployment for `9c6d638596fb9ae7c24e4f988b005b9ef02700b9` was reported READY by Vercel. The current production-target deployment remains on `main` commit `942596f6124d3585298c2b9f81239b3a01edac8a` and was READY at audit time.
- Read-only V1 report/delivery/storage trace is documented in `docs/v2/V1_FORENSIC_AUDIT.md`. It confirms `command-data/public-data` as the website's published snapshot store, GitHub Actions artifacts as 90-day report/ledger retention, and the open historical CSV as a freshly downloaded ephemeral workflow input rather than a committed dataset.
- Rebuild boundary is recorded in `docs/v2/REBUILD_BOUNDARY_DECISION.md`.
- Architecture baseline is recorded in `docs/v2/ARCHITECTURE.md`.
- Quota policy is recorded in `docs/v2/QUOTA_AND_DEPLOYMENT_BUDGET.md`.
- V1 investigation is recorded in `docs/v2/V1_PREDICTION_FINDINGS.md`.
- Infrastructure audit is recorded in `docs/v2/INFRASTRUCTURE_AUDIT_2026-11-06.md`.
- Migration inventory is recorded in `docs/v2/LEGACY_MIGRATION_INVENTORY.md`.
- Hosted V2 CI run `42191542832` for commit `966f6479021f9b0f196521146db4573cc2ba56ff` completed successfully: **95 tests passed in 0.19 seconds**. Local test execution remains unnecessary while hosted CI is available.
- Vercel preview builds have been triggered by branch commits; a previous status was pending/initializing. Do not claim a preview is ready without checking.
- No V2 production deployment, production database migration, secret change or V1 deletion has been performed.
- Neon projects inspected in the prior audit were not established as the football database. Do not use either inspected Neon project as V2 storage without evidence. One is Gold Scalper; the other contains Nexora/Cardinal-related schema.
- The exact production report-generation call graph, V1 storage location and full historical-data source have not yet been proven.

If a new session starts, first verify this checkpoint against GitHub and the documents. Do not infer that a task completed merely because it appears in a planned phase.

---

## D. Execution roadmap

Phases are sequential where marked. A phase is not complete until its exit criteria are evidenced in repository artifacts, test results or system diagnostics.

### Phase 0 — Continuity, isolation and baseline control

**Objective:** make the V2 workspace safe and reproducible.

Tasks:
1. Read this roadmap and all referenced V2 documents.
2. Verify current branch, latest commit and working-tree state.
3. Verify `main` and `command-data` remain unchanged.
4. Verify V2 CI workflow configuration and obtain actual test-run status.
5. Check Vercel preview status only for the latest known V2 commit; do not force a redeploy.
6. Confirm no V2 secrets or production writes are configured accidentally.

Exit criteria:
- Branch and production boundaries verified.
- CI status known, with failures recorded rather than hidden.
- No production mutation.

### Phase 1 — Complete V1 forensic audit (read-only)

**Objective:** understand what must be replaced and where source data actually lives.

Tasks:
1. Trace the exact daily report-generation entrypoint and scheduler. The principal workflow and function-level stages are now recorded in `V1_FORENSIC_AUDIT.md` section 11.
2. Trace the full call graph from provider ingestion through normalization, identity, history, feature construction, model selection, probability generation, calibration, value calculation and publication. Principal entrypoints are mapped; helper-level audit of all branches remains.
3. Trace website data reads and Telegram report delivery. The V1 parity race is confirmed: Telegram sends before command-data publication and no immutable shared report ID/hash exists.
4. Identify every legacy model and prediction-related module, including hidden fallbacks and duplicate paths.
5. Locate the actual historical match dataset, odds history, results, paper ledger, report artifacts and their backups.
6. Identify whether records live in repository files, GitHub Actions artifacts, a database, object storage or another service.
7. Inventory source counts, date ranges, competition coverage, provider IDs, duplicate rates, missing fields and provenance.
8. Confirm whether the previously reported historical dataset of 70,444 matches across 38 competition codes (2020-01-01 through 2026-10-24) is still available and reconcile it against the actual source. Treat that figure as unverified until reconciled.
9. Inspect workflow schedules and provider request patterns without triggering expensive endpoints.
10. Record a V1 retirement map: component, call sites, data dependencies, replacement module and decommission condition.

**Verified forensic findings (2026-11-06; Phase 1 remains IN PROGRESS):**
- Scheduled entrypoint: `.github/workflows/daily-fixture-predictions.yml`, cron `0 4 * * *` UTC (05:00 WAT start); the workflow holds Telegram delivery until 05:00 UTC (06:00 WAT).
- Main report path: workflow -> `scripts/run_daily_predictions.py` -> `app.live_predictions.build_daily_report(...)`, with provider adapters, recent-results cache, odds enrichment and value diagnostics. The report is written locally to `reports/daily_predictions.json`.
- Historical CSV: `scripts/import_open_dataset.py` downloads `xgabora/Club-Football-Match-Data` `data/Matches.csv` and writes `data/open_historical_matches.csv`. The scheduled workflow repeats the full import from 2020-01-01 on each run. The `main` tree has no committed `data/` directory and the workflow does not upload this CSV as an artifact; it is an ephemeral run input, not a durable V1 snapshot.
- Durable V1 report state: `command-data/public-data/` contains current report, dashboard snapshot, recent-results cache, paper ledger, model-validation report, value evidence ledger, verification status and Telegram delivery state. `scripts/publish_command_data.py` also writes timestamped report archives. The 2026-11-05 successful run `42075832565` retained report, paper-ledger and value-evidence workflow artifacts for 90 days.
- Website reads published snapshots from `command-data` through `app/report_artifacts.py` and `api/telegram.py`; dashboard client code also has raw GitHub, jsDelivr and Contents API fallbacks.
- Telegram delivery uses the local generated report through `scripts/send_telegram_report.py`, then the workflow publishes command-data snapshots afterwards. This creates a report-parity race: Telegram can deliver the new report while the website still serves the previous snapshot. The V1 report has neither `report_id` nor `content_sha256`; V2 must generate one immutable report and deliver that exact ID/hash to both channels.
- No football database was identified in the inspected Neon projects. The audited V1 report path's durable persistence is GitHub `command-data` plus expiring Actions artifacts; the original open historical CSV is external and re-downloaded. Full source inventory, backup proof, provider-ID coverage and exact data counts remain open.
- Production deployment record: READY deployment from `main` commit `942596f6124d3585298c2b9f81239b3a01edac8a`. Latest V2 preview for `9c6d638596fb9ae7c24e4f988b005b9ef02700b9` was reported READY. Neither was promoted or changed by this audit.
- Additional V1 defects confirmed: sparse-history forecasts can remain publishable when one side is below minimum history; Telegram recalculates BTTS/O-U from xG rather than rendering the stored report market values; the delivery filter still imports V1 identity helpers. Full evidence and remaining questions: `docs/v2/V1_FORENSIC_AUDIT.md`.

Constraints:
- Read-only. No production edits, writes, deployments, backfills or secret changes.
- Do not use the suspended API-Football credential.
- Do not guess the storage location.

Exit criteria:
- Auditable call graph.
- Proven storage map and source-of-truth inventory.
- Source-record preservation/backup strategy.
- Website and Telegram report path documented.
- V1 replacement map complete enough to build V2 without importing V1 logic.

### Phase 2 — V2 data architecture and quota budget

**Objective:** design V2 storage and ingestion around verified source data.

Tasks:
1. Define canonical data contracts for provider sources, competitions, teams, fixtures, results, odds and ingestion runs.
2. Preserve all original provider IDs and raw payload references/hashes.
3. Define verified aliases and explicit squad categories (senior men, women, youth, reserve and age group).
4. Define deterministic fixture reconciliation using competition identity, squad category, home/away identity and kickoff proximity.
5. Quarantine ambiguous matches; never silently merge or discard provider records.
6. Define evidence states: FOUND, NOT_FOUND, QUERY_FAILED, IDENTITY_MISMATCH and INSUFFICIENT_COVERAGE.
7. Select V2 storage only after Phase 1 proves the source and migration path. Use a separate database/project or isolated branch/schema; never repurpose V1 tables in place.
8. Build additive, resumable, checksummed migration tooling with reconciliation reports.
9. Establish provider-specific request ceilings, reserve, reset time, endpoint costs, cache TTLs and stop conditions.
10. Create a local quota ledger and observability for requests, remaining budget, cache hits, retries and rate-limit responses.

Exit criteria:
- Versioned V2 schema and data contracts.
- Verified isolated storage target.
- Reproducible migration plan with no unexplained source-record loss.
- Measured provider quota budget fits daily workload with contingency reserve.

### Phase 3 — V2 ingestion and historical evidence

**Objective:** produce reliable, point-in-time source data without prediction logic.

Tasks:
1. Implement fresh V2 adapters for 5DollarFootballAPI and The Odds API; add OddsPapi only if independently useful and within budget.
2. Persist raw provider records and normalized records separately.
3. Implement batch retrieval, incremental watermarks, caching, idempotency and bounded retries.
4. Preserve source fixture, team and competition IDs and timestamps.
5. Implement canonical identity decisions and quarantine workflow.
6. Import verified historical records in resumable chunks; reconcile counts, dates, duplicates and source provenance.
7. Build historical coverage diagnostics by competition, team, season and date.
8. Build evidence queries that distinguish missing history from failed lookup, identity mismatch and insufficient coverage.
9. Build odds matching by fixture identity, market, bookmaker, timestamp and kickoff cutoff; retain quote history.
10. Add provider contract tests using recorded fixtures; tests must not call paid APIs.

Exit criteria:
- Reconciled historical import with zero unexplained source-record loss.
- Provider and identity diagnostics pass.
- No ambiguous identity silently enters model datasets.
- Daily ingestion request budget proven.

### Phase 4 — Point-in-time features and model research datasets

**Objective:** create reproducible features with no future leakage.

Tasks:
1. Define feature catalog, mathematical definitions, source dependencies and versioning.
2. Build team form, attack/defence strength, venue effects, opponent adjustment, rest/travel where reliable, competition context and squad/category-aware features.
3. Build features strictly as-of each fixture cutoff; no post-kickoff results, odds or metadata leakage.
4. Store immutable feature snapshots with source record IDs, generation time, feature version and cutoff.
5. Define chronological train/validation/test partitions and rolling walk-forward folds.
6. Keep missingness explicit; do not silently impute a missing feature with an arbitrary league/global value.
7. Build reproducible research datasets and manifests independent of live API calls.

Exit criteria:
- Feature snapshots reproducible from immutable source data.
- Leakage tests pass.
- Training datasets can be regenerated with exact version/cutoff.

### Phase 5 — Independent model development

**Objective:** rebuild every market model from clean V2 implementations.

Tasks:
1. Establish transparent, testable baseline estimators as V2 implementations—not copied V1 code.
2. Evaluate appropriate model families independently for 1X2, BTTS and totals.
3. Candidate families may include calibrated multinomial models, hierarchical/team-strength models, goal-distribution models, gradient boosting and ensembles where justified by data volume.
4. Select models using chronological out-of-sample results, not in-sample fit or a single recent date range.
5. Benchmark against de-vigged bookmaker probabilities wherever timestamped odds coverage is adequate.
6. Track model versions, feature versions, training data cutoffs, hyperparameters, random seeds and experiment manifests.
7. Reject models that are unstable across competitions, seasons or time periods.
8. Do not publish model outputs while validation/calibration gates are incomplete.

Exit criteria:
- Each market has an independently reproducible candidate model.
- No V1 model dependency.
- Out-of-sample results and failure cases documented.
- Baselines beat only what they demonstrably beat; no unsupported accuracy claims.

### Phase 6 — Calibration, uncertainty and eligibility

**Objective:** make probability outputs statistically meaningful and publication-safe.

Tasks:
1. Fit calibration only on chronological held-out data, separately by market/model where sample size supports it.
2. Evaluate reliability diagrams, calibration error, Brier score and log loss.
3. Quantify uncertainty and identify unsupported competition/team regimes.
4. Implement one authoritative V2 eligibility gate with explicit reasons.
5. Require verified fixture identity, future kickoff, supported competition, sufficient history, valid features, functioning model and available calibration.
6. Require valid probability vectors and matching fixture/model/feature/evidence references.
7. Emit no probability fields for withheld statuses.
8. Test that unrelated fixtures cannot inherit identical generic/global distributions and that missing evidence cannot trigger a fallback.

Exit criteria:
- Calibration is measured on held-out chronological data.
- Withheld states cannot contain public probability values.
- All eligibility and probability integrity tests pass.

### Phase 7 — Market validation and release certification

**Objective:** certify each market independently before publication.

Minimum release gates carried forward from project requirements:
- At least 1,000 chronological walk-forward matches per market.
- At least 300 prospective settled selections across at least 90 distinct dates.
- At least 98% timestamped pre-kickoff odds coverage for the applicable evaluation.
- Positive cumulative flat-stake ROI and positive lower 95% confidence bound using a match-date-cluster bootstrap.
- 1X2 must additionally beat the de-vigged bookmaker benchmark on both Brier score and log loss.
- Results must match the exact deployed model, feature and calibration versions.

Tasks:
1. Implement reproducible walk-forward runner.
2. Implement prospective paper ledger with immutable selection timestamps and source odds.
3. Record all eligible and withheld decisions to prevent selection/reporting bias.
4. Settle outcomes from verified results and retain correction provenance.
5. Run confidence intervals with date clustering.
6. Generate signed/versioned release certificates per market.
7. Keep value-bet publication locked until its own evidence passes.
8. If any gate fails, keep that market withheld; do not relax thresholds to force release.

Exit criteria:
- Independent release certificate for every enabled market.
- No market inherits another market's approval.
- Failed markets remain unavailable to public forecast consumers.

### Phase 8 — Immutable reporting and retained delivery integration

**Objective:** connect the new prediction engine to the existing website and Telegram without duplicating forecast logic.

Tasks:
1. Define immutable report schema with report ID, date, generated timestamp, pipeline/model/feature/calibration versions, input run IDs, per-fixture identity/status, market statuses, diagnostics and content hash.
2. Generate the report once from V2-approved forecasts.
3. Make website read the report through a versioned V2 adapter.
4. Make Telegram deliver the exact same report ID and content hash.
5. Preserve website navigation and existing dashboard shell; replace prediction data adapters and forecast presentation as needed.
6. Preserve Telegram bot/channel transport; replace prediction payload generation and publication logic.
7. Add idempotent delivery, retries and an outbox/manifest.
8. Keep withheld fixtures visible as match records/status where useful, but hide forecast chips and probabilities.
9. Preserve target delivery around 06:00 Africa/Lagos (05:00 UTC), subject to measured pipeline completion and quota budget.

Exit criteria:
- Website and Telegram verified against the exact same report ID/hash.
- No old prediction endpoint or fallback remains reachable from V2.
- Retries cannot duplicate successful Telegram deliveries.

### Phase 9 — Shadow operation and controlled cutover

**Objective:** prove the complete system before production replacement.

Tasks:
1. Run V2 in isolated shadow mode using bounded API calls and cached historical data.
2. Compare V2 and V1 outputs for audit only; V1 outputs do not feed V2.
3. Run prospective paper tracking until the sample/date gates are met.
4. Test provider outage, quota exhaustion, stale cache, ambiguous fixture, missing history, model failure, calibration failure and delivery retry scenarios.
5. Verify V1 production website/Telegram remains available during shadow mode.
6. Create rollback and cutover runbooks.
7. Promote V2 only after all data, model, market, quota, delivery and operational release gates pass.

Exit criteria:
- All market release certificates pass.
- Website/Telegram report parity verified.
- Quota budget proven under real scheduled load.
- Rollback tested.
- Production cutover is a deliberate, documented operation.

### Phase 10 — V1 prediction retirement and ongoing operations

**Objective:** retire old prediction logic only after V2 is stable.

Tasks:
1. Switch retained website and Telegram delivery surfaces to V2 report source.
2. Disable V1 prediction scheduler and publication paths after parity and rollback checks.
3. Keep V1 source and artifacts archived read-only for audit until retention policy allows otherwise.
4. Remove obsolete secrets only after dependency checks and explicit owner approval; never touch the suspended API-Football key under this roadmap.
5. Monitor provider quota, data freshness, model drift, calibration drift, market performance, report delivery and system health.
6. Revalidate models on schedule and suspend markets when release certificates expire or evidence degrades.

Exit criteria:
- No public delivery path consumes V1 predictions.
- V2 operation is observable, quota-bounded and independently maintainable.
- Legacy records remain auditable.

---

## E. Quota and deployment operating rules

1. No continuous polling.
2. No per-fixture API calls where a batch endpoint exists.
3. Cache successful provider responses with provider/data-class-specific TTLs.
4. Use incremental sync and persistent watermarks.
5. Respect provider rate-limit headers and Retry-After; use bounded exponential backoff with jitter.
6. Never automatically retry authentication, plan-limit, permission or invalid-request failures.
7. Set hard daily ceilings and reserve budget for the scheduled report and essential recovery.
8. Stop optional enrichment before consuming the reserve.
9. Never run full historical backfills during daily ingestion, CI or Vercel builds.
10. Do not train models by calling live providers; train from versioned datasets.
11. Run fast tests for relevant changes; reserve expensive walk-forward/bootstrap runs for planned milestones.
12. Batch commits to avoid unnecessary Vercel preview deployments.
13. Do not force redeploys or repeatedly poll deployment status.
14. Keep production deployment untouched until Phase 9 exit criteria are met.
15. Log request usage and deployment/build usage without exposing credentials.
16. If actual provider quotas are unknown, disable nonessential polling and treat quota as scarce.

---

## F. Project status board

Update this section whenever a phase materially changes. Use only evidence-backed statuses.

| Phase | Status at roadmap creation | Evidence / next action |
|---|---|---|
| 0. Isolation and baseline | PASSED | 2026-11-06: branch isolation verified; hosted V2 CI run 42190330172 passed 65 tests; production branches unchanged |
| 1. V1 forensic audit | IN PROGRESS | 2026-11-06: report/delivery path and 108-file command-data tree audited; 39 report archives inventoried (55.08 MiB) with Git blob SHAs. Backup/restore proof, exhaustive Actions-artifact inventory, raw historical-source reconciliation and full API call-site audit remain |
| 2. Data architecture and quota | IN PROGRESS | Logical contracts, quota policy, source-rights/account-capability gates and provider-neutral ports implemented; storage target, account tiers and measured quota budgets unverified |
| 3. Ingestion and history | IN PROGRESS | 2026-11-06: offline acceptance, quota and account gates plus provider-neutral transport/persistence protocols implemented; concrete adapters, atomic storage, watermarks and history remain unbuilt |
| 4. Features and datasets | NOT STARTED | Await Phase 3 |
| 5. Independent models | NOT STARTED | Await verified datasets |
| 6. Calibration and eligibility | FOUNDATION ONLY | Preliminary eligibility code exists; tests not yet confirmed |
| 7. Market validation | NOT STARTED | Await model candidates and prospective ledger |
| 8. Reporting and delivery | NOT STARTED | Await V2 report contract implementation |
| 9. Shadow and cutover | NOT STARTED | Await all prior gates |
| 10. V1 retirement | NOT STARTED | Only after successful cutover |

Allowed status values: NOT STARTED, IN PROGRESS, BLOCKED, PARTIAL, PASSED, FAILED. Add date, commit SHA, evidence and remaining blocker when updating a status. Never mark PASSED based on intention or a successful file write alone.

---

## G. Next action queue — execute in this order

1. Complete the V1 workflow call graph through every research, enrichment, filtering, validation and delivery step; identify all active and legacy model paths. Neutral-prior, sparse-history, Elo/Poisson and Telegram's independent BTTS/O-U recalculation paths are now confirmed.
2. Reconcile historical CSV, recent-results cache, report archives, paper ledger and value-evidence ledger counts, dates, IDs, provenance and backup/retention guarantees. The command-data archive inventory and a verified sample of three GitHub Actions artifacts are committed at `docs/v2/V1_ARTIFACT_INVENTORY.md`.
3. Inspect workflow artifact inventory and command-data archive policy without downloading or rewriting production data. The inspected workflow sets 90-day retention; Actions artifact inventory is not exposed through the current supported connector.
4. Football-Data.co.uk-derived history remains excluded from V2 commercial training. 5DollarFootballAPI and The Odds API published terms permit commercial model/app use, but active account plans, history depth, competition coverage, quota and required attribution are unverified. The rights gate, account-capability gate and quota guard are implemented as offline boundaries; provider adapters and persistence remain pending.
5. Verify provider secret *names* and measured quotas only where permitted; never access API-Football credentials.
6. Finalize V1 retirement map and preservation plan.
7. Only after source inventory and data-rights gates are complete, choose a dedicated isolated V2 storage target and design additive migration.

Do not skip ahead to model training while source data, identity and point-in-time history are unverified.

### 2026-11-06 execution checkpoint
- Branch HEAD before this work: `cb727038e43d02d20eb006a0475e39255b6ea062`.
- Implemented `veltrix_v2/ingestion/acceptance.py` and its typed provider-record envelope.
- Acceptance requires a verified rights decision for the requested purpose and for caching, validates source identity, immutable payload SHA-256 and timezone-aware fetch/ingest/source timestamps, and preserves provider fixture/competition IDs.
- Added an offline quota preflight guard: unknown, stale, expired, malformed or overdrawn snapshots fail closed; configured reserve units cannot be spent. Atomic reservation is explicitly delegated to the future persistence adapter.
- Added a verified account-plan capability gate: requests are blocked unless the actual account evidence covers the requested competitions, data class, history start and quota snapshot. Published plan descriptions cannot substitute for account verification.
- Hosted CI run `42190061519` for ingestion acceptance commit `9deef706` passed. Hosted CI run `42190126086` for quota-guard commit `2dc12662` also passed.
- This is an offline boundary only. No provider calls, database writes, credentials access, historical imports or production changes occurred.
- Hosted CI run `42190330172` for provider-access commit `77841128` completed successfully: **65 tests passed in 0.11 seconds**. The current `8ccb777` head is a documentation-only descendant.

---

## H. New-session handoff protocol

At the start of any new conversation in this project:

1. Locate and read this file: `docs/v2/ROADMAP.md`.
2. Read `docs/v2/REBUILD_BOUNDARY_DECISION.md`, `docs/v2/ARCHITECTURE.md`, `docs/v2/QUOTA_AND_DEPLOYMENT_BUDGET.md`, `docs/v2/V1_FORENSIC_AUDIT.md` and `docs/v2/DATA_RIGHTS_REGISTER.md`.
3. Read the latest V1 audit, `docs/v2/V1_FORENSIC_AUDIT.md`, `docs/v2/V1_RETIREMENT_MAP.md`, infrastructure audit and migration inventory.
4. Verify current GitHub branch/commit and check for later roadmap updates.
5. Check the project status board and resume the earliest incomplete phase.
6. Do not ask the owner to repeat decisions already documented here.
7. Do not claim access to a previous chat is necessary; this repository document is the continuity contract.
8. Do not perform production writes, change secrets, trigger expensive API calls, create backfills or promote deployments unless the roadmap's relevant gates authorize them.
9. If a blocker prevents one task, record it and continue with the next independent read-only or offline task.
10. Update this roadmap after meaningful milestones with exact commit SHA, tests and evidence.

**Authority rule:** If an older chat summary conflicts with this roadmap, use the newest committed roadmap and architecture decisions unless the project owner explicitly changes them. Never silently weaken the rebuild boundary, validation thresholds or quota safeguards.


### 2026-11-06 provider-neutral port milestone
- Added `veltrix_v2/ingestion/ports.py`: bounded request specifications with mandatory quota cost/idempotency, immutable scalar parameters, exact-byte raw payload hashing, provider batch provenance, atomic quota-ledger protocol, source-rights/capability repositories, atomic accepted-record persistence protocol and ingestion-run lifecycle.
- Added `tests/v2/test_ingestion_ports.py` for request bounds, duplicate competition rejection, parameter immutability, raw-byte hashing, provider consistency, timezone validation, quota reservation and stored-record references.
- These are offline contracts only. No provider implementation, API request, database adapter, database write or credential access is included.
- Next: define storage-neutral history and watermark contracts; continue V1 source reconciliation and provider schema verification. Storage selection remains blocked until Phase 1 and quota evidence are complete.


### 2026-11-06 history and preflight milestone
- Added `veltrix_v2/history/contracts.py` with provenance-backed canonical historical matches, point-in-time team-history query contracts, explicit history evidence states, bounded incremental sync plans and compare-and-set watermark repository semantics.
- Added `tests/v2/test_history_contracts.py`.
- Added `veltrix_v2/ingestion/preflight.py`, combining verified account capability and quota snapshot checks. It rejects provider/scope mismatch and quota snapshots not linked to the verified account profile.
- Added `tests/v2/test_ingestion_preflight.py`.
- Hosted CI run `42191456747` passed **88 tests** for the history-contract commit. Hosted CI run `42191542832` passed **95 tests** for the combined preflight commit.
- All new components are offline contracts and pure gates. No provider request, secret access, database write or production deployment occurred.
- Next: continue the V1 function-level retirement/data-source audit, then implement a storage-neutral ingestion execution coordinator only after its rights, quota reservation and idempotency semantics are fully specified.


### 2026-11-06 provider schema research milestone
- Reviewed official 5DollarFootballAPI and The Odds API documentation and recorded endpoint, pagination, plan/history, quota, rate-limit, market-discovery and error-handling constraints in `docs/v2/PROVIDER_ADAPTER_RESEARCH.md`.
- Important constraints: 5Dollar history depth is plan-dependent and its per-fixture odds tick-history endpoint is Ultra-only; The Odds API historical snapshots are paid-only and cost 10 credits per region per market. User account plans and remaining quotas are not verified.
- No provider API call, credential read or quota spend occurred. Both provider runtimes remain disabled.


### 2026-11-06 rights-aware batch persistence milestone
- Added `veltrix_v2/ingestion/persist.py`: checks request/response identity, provider quota cost, data class and competition scope; evaluates commercial rights for the requested purpose and caching; preserves provider fixture/competition IDs and exact raw bytes; uses deterministic per-record idempotency keys; delegates atomic raw-payload + source-envelope + rights-decision persistence to a repository adapter.
- Added `tests/v2/test_ingestion_persist.py`.
- Hosted CI run `42192009839` for commit `0c590565` passed **105 tests in 0.14 seconds**.
- CI found and corrected two test-fixture mistakes in intermediate commits. No production code or policy gate was relaxed; the succeeding run is green.
- Provider adapter research is documented in `PROVIDER_ADAPTER_RESEARCH.md`. Both external provider runtimes remain disabled because actual account plans, rights evidence, quota and data depth have not been verified.
- No provider API calls, secrets access, database writes, production writes or production deployments occurred.


### 2026-11-06 V1 runtime call-graph milestone
- Expanded `V1_FORENSIC_AUDIT.md` with the ordered workflow stages, daily runner sequence, provider client entrypoints, prediction module functions, delivery filter coupling, Telegram command recalculation and publication ordering.
- Expanded `V1_RETIREMENT_MAP.md` with explicit V2 boundary replacements and cutover requirements.
- Confirmed V1 report/Telegram parity race, independent Telegram Poisson goal-market calculation, non-atomic command-data publication and repeated full historical CSV import.
- Phase 1 remains IN PROGRESS: full helper-level call graph, source count/date/ID reconciliation, independent SHA-256 export and restore proof, exhaustive Actions artifact inventory, and rights/source approval remain open.


### 2026-11-06 provider parser and point-in-time history milestone
- Added an offline 5DollarFootballAPI fixture-response parser. It preserves provider fixture, competition, home-team and away-team IDs; exact response bytes; pagination; rate-limit headers; and explicit 301 league-merge redirects. It classifies 401/403/429/5xx without retrying auth/plan failures.
- Added an offline The Odds API v4 event-odds parser. It preserves event/sport IDs and exact response bytes, captures observed quota cost headers and discovers actual market keys rather than assuming BTTS exists.
- Added shared provider error classifications. These are response parsers only: no HTTP transport, API key access or provider call is implemented.
- Extended source envelopes with provider home/away team IDs.
- Added `history/query.py`: point-in-time team-history selection excludes kickoff at or after cutoff, normalizes date windows to UTC, filters canonical competition and squad category, selects the most recent bounded sample and returns explicit NOT_FOUND / INSUFFICIENT_COVERAGE / IDENTITY_MISMATCH states.
- Hosted CI run `42192586750` passed **132 tests in 0.25 seconds**.
- Next: build the transport executor and atomic storage adapter only after account capabilities, measured quota and storage target are established. Continue Phase 1 source reconciliation and backup/restore proof.


### 2026-11-06 transport and orchestration milestone
- Added injectable stdlib HTTP GET transport and a disabled-by-default 5Dollar fixture adapter with strict endpoint/query allowlisting, 24-hour window cap, provider ID validation, and no credential logging.
- Added disabled-by-default The Odds API v4 adapter with explicit sport/region/market validation, historical snapshot timestamp validation and exact 10-credits-per-region-per-market reservation check.
- Added `ingestion/service.py` to orchestrate account capability, quota snapshot, source rights and CACHE rights before transport; reserve quota atomically; conservatively settle unknown transport costs; persist accepted records idempotently; and complete/fail ingestion runs.
- Both provider adapters default to disabled. The service also defaults to transport disabled. No API key was read or passed, no provider request occurred and no external quota was consumed.
- Latest fully green hosted CI at this checkpoint: run `42193057875`, **162 tests passed**. Newer coordinator changes are pending their own CI confirmation.


### 2026-11-06 provider identity registry milestone
- Added explicit, versioned provider competition/team mapping records with verification state, evidence reference and effective validity window.
- Added exact-ID resolver that rejects missing, ambiguous, revoked/unverified, wrong-source and squad-category-conflicting mappings. It never fuzzy-matches names.
- Historical mappings can be verified retrospectively: validity is evaluated at fixture kickoff, while verification timestamp is checked against decision time.
- Added the identity pipeline joining verified provider mappings to deterministic canonical fixture reconciliation; ambiguous canonical candidates are quarantined and provider home/away orientation is preserved.
- Hosted CI run `42193498440` passed **181 tests in 0.33 seconds**.
- Mapping rows themselves are not populated; real provider IDs and canonical mappings remain blocked on verified provider access and source data.


## Current verified continuity update — 2026-11-08

This section supersedes earlier checkpoint and test-count statements above. Always verify the branch again before editing.

- Current V2 branch HEAD: `8d47aeaa26c053a13e9c2a95c19dd1d54844842a`.
- Latest hosted V2 CI: run `42466905692`, **268 tests passed**; completed successfully.
- Latest Vercel preview for that V2 commit: **READY** (deployment `dpl_4iS1Xs937V8TtQPzfVT9kfqg7Ua6`). This is a preview, not a production promotion.
- Production `main` remains `05e517af4dcac27507a3c32ebaceee117828df22`.
- `command-data` currently points to `f759046a44edcc5a0c69198b4b7183176c2562b5`, written by the scheduled V1 verification workflow; no V2 commit was made to that branch.
- No V2 database was provisioned, no migration was applied, no provider API call was made, and no historical records were imported.
- V2 preview environment variables are empty. The Vercel production environment-variable names inspected (without decrypting values) include only the legacy API-Football names and Telegram settings; no 5DollarFootballAPI key, The Odds API key or V2 database URL is configured there. The API-Football credentials remain untouched and must not be used.
- GitHub Actions secret metadata is not exposed by the available connector, so provider secrets potentially stored there cannot be confirmed. Do not infer that they exist.
- The Neon projects previously inspected are unrelated to football. Neither is approved as V2 storage.

### Phase 3 — implementation status

**Status: IN PROGRESS — offline architecture implemented; live data verification blocked.**

Added on `v2/foundation`:
- PostgreSQL schema for immutable raw source records, versioned team/competition mappings, canonical fixtures, provider fixture provenance, historical results, quarantine, sync watermarks and ingestion runs.
- DB-API repositories for raw source records, identity mappings, fixture reconciliation/quarantine, historical results and atomic watermarks.
- Exact source-record-to-provider-fixture provenance links; distinct provider payload versions are retained by payload hash.
- Bounded incremental synchronization with starting-watermark checks, cursor-progress checks, page limits and compare-and-set advancement only after all pages succeed.
- Rights-gated historical result import in bounded, resumable chunks with explicit imported/rejected/quarantined outcomes and a source-manifest SHA-256.
- Historical coverage diagnostics and strict point-in-time team-history retrieval.

### Phase 3 exit criteria still outstanding

1. Provision a dedicated V2 PostgreSQL database under an approved plan and configure a V2-only connection secret. Do not use either previously inspected Neon project.
2. Make provider credentials available to the V2 ingestion worker through secret storage (never commit or paste secret values into chat).
3. Verify actual 5DollarFootballAPI account plan, supported competitions/data classes, historical depth, quota/reset and commercial-use permissions. Verify The Odds API account/credit limits if used. Public plan descriptions are not account verification.
4. Populate team and competition mappings from actual provider IDs with auditable evidence; do not seed guessed aliases.
5. Run a small, bounded provider sample, persist raw records and verify exact hashes, IDs, timestamps, rights evidence and idempotency.
6. Execute resumable historical import and reconcile source counts, date ranges, provider fixture IDs, canonical duplicates, quarantines and coverage. Zero unexplained source-record loss is mandatory.
7. Run the repository adapters against the actual isolated PostgreSQL target and perform restore/replay checks. Current CI uses offline tests and does not prove a live database migration.

Until those criteria pass, provider adapters remain disabled, no watermark may advance for an unverified import, Phase 3 must not be marked complete, and Phase 4 model research must not consume unverified history.

### Quota and deployment note

Several V2 commits triggered automatic Vercel preview builds. The latest preview is READY. Avoid additional commits, preview builds, provider calls or redeploys until a necessary code change or the storage/provider blockers are resolved. No V2 production deployment has occurred.


## Continuity update — 2026-11-08 09:29 UTC

Supersedes earlier 2026-11-08 checkpoint details above.

- V2 branch HEAD: `c4c62d89b1b385f2bc491ee021e19a4b5661d93c`.
- Hosted CI run `42467301711`: **280 passed in 0.70 seconds**, successful. This run includes PostgreSQL 16 integration tests using an ephemeral CI service database.
- Previous hosted PostgreSQL integration run `42467197463`: **276 passed in 1.02 seconds**.
- Latest Vercel preview for current HEAD: **READY**, deployment `dpl_3aRGZxvbWY7n6k9MdZCfmdjE2szT`. It is a preview, not production.
- Production `main` remains `05e517af4dcac27507a3c32ebaceee117828df22`.
- `command-data` remains `f759046a44edcc5a0c69198b4b7183176c2562b5`.
- Vercel V2 preview environment variable listing (decryption disabled) returned zero variables.
- Neon account project listing returned only the two already-audited unrelated projects. No approved V2 football database exists.
- No provider API request, external quota use, migration to persistent storage, historical import or production write occurred.

### New Phase 3 integrity additions
- Added exact source-manifest reconciliation. Every expected source record must have exactly one explicit IMPORTED, REJECTED or QUARANTINED terminal outcome; missing, unexpected, duplicate and count-tampered outcomes fail closed.
- PostgreSQL integration tests now exercise immutable raw payload versions, verified mapping persistence, fixture/source identity consistency, canonical fixture reconciliation, quarantine, historical result retrieval and watermark persistence.
- Sync watermark advancement now requires exactly one version increment and disallows timestamp regression.
- A fixture repository mock regression was corrected; current hosted CI run above is green.

### Remaining Phase 3 acceptance blockers
- No dedicated persistent V2 database or V2-only connection secret is provisioned.
- No provider credentials are confirmed in V2 preview or available through the inspected Vercel project environment. GitHub Actions secret metadata cannot be inspected through available connector access.
- Actual 5DollarFootballAPI and The Odds API account entitlements, rights, quotas/reset, supported competitions and historical depth remain unverified.
- Real provider team/competition mappings are not populated.
- No provider sample or historical backfill has run; production source counts, completeness and zero-loss reconciliation remain unproven.
- CI integration tests use a temporary PostgreSQL service and do not substitute for persistent V2 database provisioning, migration deployment or backup/restore proof.

**Decision:** Phase 3 remains IN PROGRESS. Keep provider transport disabled. Do not mark Phase 3 complete or begin Phase 4 model research until the real provider and persistent-storage acceptance criteria pass.


### Storage provisioning discovery — 2026-11-08
- Neon organization `org-muddy-sunset-38353006` is confirmed on the **Free** plan.
- The installed Vercel Marketplace Neon integration is also confirmed on its **Free** billing plan: $0, no payment method required, 1 GB/project and 100 CU-hours/project.
- The organization is Vercel-managed. Direct Neon `create_project` was rejected by the provider with `organization is managed by Vercel`. This is a provider-side policy restriction, not a database/schema failure.
- The Vercel integration configuration exposes Neon provisioning capability, but the available Vercel connector has no create/provision integration-resource action. Existing integration reports no provisioned projects.
- No project was created and no paid plan or billing change was initiated. The correct path is provisioning Neon through the Vercel Marketplace integration UI, selecting the Free plan and a region compatible with the Vercel project. Once the integration is attached, use its generated project environment variables; do not paste database credentials into chat or commit them.
- This is now the single infrastructure blocker for persistent storage. CI PostgreSQL 16 integration tests continue to validate the migration and repositories independently.
