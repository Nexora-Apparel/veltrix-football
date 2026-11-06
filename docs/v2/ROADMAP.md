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
- Latest verified V2 branch HEAD: `fc35c1be99580ada72b1d755afbc7e4c8923bdc6` (2026-11-06). The branch is 20 commits ahead of `main`; verify again before editing.
- `main` HEAD remains `05e517af4dcac27507a3c32ebaceee117828df22`; `command-data` HEAD remains `1b735d9f515241583ecd0eb1195d3e2585b8540a`. V2 work remains isolated.
- Hosted V2 CI run `42188667633` passed: 23 tests passed in 0.04 seconds after correcting a test-helper typo. The prior run `42188058167` failed with a `NameError` in the global-prior regression test; the correction is committed on V2 only.
- Latest V2 preview deployment for `fc35c1be99580ada72b1d755afbc7e4c8923bdc6` was reported READY by the Vercel project metadata. The current production-target deployment remains on `main` commit `942596f6124d3585298c2b9f81239b3a01edac8a` and was READY at audit time.
- Read-only V1 report/delivery/storage trace is documented in `docs/v2/V1_FORENSIC_AUDIT.md`. It confirms `command-data/public-data` as the website's published snapshot store, GitHub Actions artifacts as 90-day report/ledger retention, and the open historical CSV as a freshly downloaded ephemeral workflow input rather than a committed dataset.
- Rebuild boundary is recorded in `docs/v2/REBUILD_BOUNDARY_DECISION.md`.
- Architecture baseline is recorded in `docs/v2/ARCHITECTURE.md`.
- Quota policy is recorded in `docs/v2/QUOTA_AND_DEPLOYMENT_BUDGET.md`.
- V1 investigation is recorded in `docs/v2/V1_PREDICTION_FINDINGS.md`.
- Infrastructure audit is recorded in `docs/v2/INFRASTRUCTURE_AUDIT_2026-11-06.md`.
- Migration inventory is recorded in `docs/v2/LEGACY_MIGRATION_INVENTORY.md`.
- Preliminary V2 tests have **not** been confirmed passing. A local clone/test attempt was blocked by DNS/network failure. The GitHub Actions workflow must be checked for a real run and result.
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
1. Trace the exact daily report-generation entrypoint and scheduler.
2. Trace the full call graph from provider ingestion through normalization, identity, history, feature construction, model selection, probability generation, calibration, value calculation and publication.
3. Trace website data reads and Telegram report delivery. Prove whether both currently consume the same artifact/report ID.
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
- Production deployment record: READY deployment from `main` commit `942596f6124d3585298c2b9f81239b3a01edac8a`. Latest V2 preview for `fc35c1be99580ada72b1d755afbc7e4c8923bdc6` was reported READY. Neither was promoted or changed by this audit.
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
| 0. Isolation and baseline | PASSED | 2026-11-06: branch isolation, 23 hosted tests, V2 preview and production deployment checked |
| 1. V1 forensic audit | IN PROGRESS | Entry point, report/delivery paths and primary persistence traced; full source inventory, backups and provenance reconciliation remain |
| 2. Data architecture and quota | PARTIAL | Logical contracts, quota policy and V1 persistence map drafted; V2 storage target and measured provider caps unverified |
| 3. Ingestion and history | NOT STARTED | Blocked on source inventory and storage proof |
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
2. Reconcile historical CSV, recent-results cache, report archives, paper ledger and value-evidence ledger counts, dates, IDs, provenance and backup/retention guarantees.
3. Inspect workflow artifact inventory and command-data archive policy without downloading or rewriting production data.
4. Exclude Football-Data.co.uk-derived history from V2 commercial training. Use 5DollarFootballAPI/The Odds API only within their published commercial terms; verify the current plan's history depth, league coverage, quota and required attribution before migration.
5. Verify provider secret *names* and measured quotas only where permitted; never access API-Football credentials.
6. Finalize V1 retirement map and preservation plan.
7. Only after source inventory and data-rights gates are complete, choose a dedicated isolated V2 storage target and design additive migration.

Do not skip ahead to model training while source data, identity and point-in-time history are unverified.

---

## H. New-session handoff protocol

At the start of any new conversation in this project:

1. Locate and read this file: `docs/v2/ROADMAP.md`.
2. Read `docs/v2/REBUILD_BOUNDARY_DECISION.md`, `docs/v2/ARCHITECTURE.md`, `docs/v2/QUOTA_AND_DEPLOYMENT_BUDGET.md` and `docs/v2/V1_FORENSIC_AUDIT.md`.
3. Read the latest V1 audit, `docs/v2/V1_FORENSIC_AUDIT.md`, `docs/v2/V1_RETIREMENT_MAP.md`, infrastructure audit and migration inventory.
4. Verify current GitHub branch/commit and check for later roadmap updates.
5. Check the project status board and resume the earliest incomplete phase.
6. Do not ask the owner to repeat decisions already documented here.
7. Do not claim access to a previous chat is necessary; this repository document is the continuity contract.
8. Do not perform production writes, change secrets, trigger expensive API calls, create backfills or promote deployments unless the roadmap's relevant gates authorize them.
9. If a blocker prevents one task, record it and continue with the next independent read-only or offline task.
10. Update this roadmap after meaningful milestones with exact commit SHA, tests and evidence.

**Authority rule:** If an older chat summary conflicts with this roadmap, use the newest committed roadmap and architecture decisions unless the project owner explicitly changes them. Never silently weaken the rebuild boundary, validation thresholds or quota safeguards.
