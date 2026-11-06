# VELTRIX FOOTBALL V1 — Forensic Runtime, Delivery and Storage Audit

**Audit date:** 2026-11-06  
**Scope:** Read-only inspection of `main`, `command-data`, the daily GitHub Actions workflow, report/delivery modules, Vercel project/deployment metadata and one successful workflow's artifact manifest.  
**V2 boundary:** Findings describe V1 only. No V1 code is imported into V2. No production branch, secret, database or deployment was changed.

## 1. Verified branch and deployment baseline

- Repository: `Nexora-Apparel/veltrix-football`.
- `main` HEAD: `05e517af4dcac27507a3c32ebaceee117828df22`.
- `command-data` HEAD: `1b735d9f515241583ecd0eb1195d3e2585b8540a`.
- `v2/foundation` HEAD at this audit: `fc35c1be99580ada72b1d755afbc7e4c8923bdc6`.
- V2 CI run `42188667633` completed successfully: **23 passed**. The prior failure was a test-only `NameError` caused by calling a nonexistent helper; the regression test now calls `evaluate_fixture_eligibility`.
- Vercel production-target deployment was READY from `main` commit `942596f6124d3585298c2b9f81239b3a01edac8a`. The latest V2 preview for `fc35c1be99580ada72b1d755afbc7e4c8923bdc6` was reported READY by project metadata. Production remains on V1.

## 2. Daily scheduler and report-generation path

Workflow: `.github/workflows/daily-fixture-predictions.yml`.

- Scheduled cron: `0 4 * * *` UTC, equivalent to 05:00 Africa/Lagos.
- A scheduled run holds the final Telegram send until 05:00 UTC (06:00 Africa/Lagos).
- Manual dispatch accepts a Nigeria-local date. A marked push can trigger controlled live verification; ordinary pushes run tests only.
- The main generation command is `scripts/run_daily_predictions.py`.
- That script imports V1 prediction/runtime modules including `app.live_predictions`, `app.provider_adapters`, `app.recent_results`, `app.value_bets_runtime` and `app.value_intelligence_runtime`.
- The report builder call is `build_daily_report(..., strict_publication=True)`; output is written to `reports/daily_predictions.json`.
- Primary fixture/results integration is 5DollarFootballAPI. The Odds API supplements fixtures/prices; OddsPapi is optional enrichment. The workflow passes 5Dollar and The Odds API credentials as Actions secrets. No secret values were inspected.
- Research-source discovery, odds enrichment, value-evidence updates, fixture visibility validation and value-certificate generation are additional workflow stages.

### V1 prediction and market-output defects confirmed

- `app/live_predictions.py::predict_fixtures` has a no-history branch that sets both teams to the same neutral expected-goals rate (1.225) and still calculates 1X2, BTTS and totals probabilities with the legacy Poisson helper.
- A separate non-senior branch also uses neutral scoring rates rather than category-matched team evidence.
- The sparse-history path activates when either team has fewer than the configured minimum of five prior matches, then shrinks available team rates toward competition or global rates and still emits public probabilities with status `LOW_HISTORY_FORECAST`. This includes a fixture where one team has zero matched history.
- `build_daily_report(..., strict_publication=True)` strips probability fields for the zero-history case only when **both** home and away history counts are zero. A sparse fixture with one side missing or either side below the five-match threshold can retain its probabilities. This is narrower than a strict minimum-history publication gate.
- When competition Elo is selected for 1X2, the report still uses the recent-goals Poisson path for xG, BTTS and totals. Market heads therefore have distinct model provenance and must be validated independently.
- `app/telegram_commands.py::_goal_market_probabilities` independently recalculates BTTS and Over/Under probabilities from expected goals using its own independent-Poisson helper. Telegram's `/btts` and `/overunder` commands therefore do not simply render the saved report market probabilities; they can diverge from report values and do not apply the report's calibration metadata.
- `scripts/filter_report_for_delivery.py` imports V1 team-name normalization and fuzzy-match helpers from `app.live_predictions`. The delivery filter is therefore coupled to the legacy identity implementation, even though it can withhold some unsafe matches.

These findings reinforce the V2 requirement for one authoritative identity service, one market-specific forecast record per market, a single eligibility decision, and delivery clients that render stored probabilities without recalculating them.

This confirms the scheduler and principal report path. A complete function-by-function call graph of every imported V1 model and helper is still outstanding.

### V1 identity and odds integration

- `app/fixture_identity.py` reconciles cross-provider fixture rows using normalized team names, inferred squad category, normalized competition name/country and kickoff proximity. Its default strict match tolerance is five minutes; nearby same-team/category records with competition or kickoff conflicts are quarantined.
- The V1 identity module retains provider name, provider fixture ID, competition ID, team IDs/names and source kickoff in per-row provenance. It does not create a durable canonical identity registry or verified provider team-ID crosswalk. `TEAM_ALIASES` is empty; a separate unverified-alias list is used to trigger quarantine rather than merge.
- The report's odds enrichment joins provider events back to report predictions using normalized home/away names, competition identity and kickoff time. The Odds API queries only mapped competitions represented in the report and applies a bounded per-event BTTS request cap. InferSports is disabled by default and, when enabled, event odds calls are capped.
- `app/recent_results.py` performs incremental catch-up using bounded date ranges and records transient gaps/plan-limited dates in the cache state. Retryable gaps are retried no more than weekly. This cache strategy is distinct from the separate full open-CSV download that still occurs each scheduled workflow run.

## 3. Historical data: what is actually persisted

### 3.1 Open historical dataset

`scripts/import_open_dataset.py` downloads:

`https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data/main/data/Matches.csv`

It normalizes rows and writes the requested output, normally `data/open_historical_matches.csv`.

The daily workflow invokes it from `2020-01-01` through the current UTC date on scheduled, manual and controlled live-verification runs. This is a full historical source download/import, not an incremental local update.

The `main` repository root has no committed `data/` directory. The inspected daily workflow uploads report, paper-ledger and value-evidence artifacts, but does not upload `data/open_historical_matches.csv`. Therefore the normalized CSV is an ephemeral workflow-run input, not a durable V1 snapshot in the repository or the listed workflow artifacts.

The importer records the upstream repository/source in its normalized rows and import summary, but the inspected schema has no stable provider fixture ID for each open-dataset row.

The published V1 validation metadata records the historical dataset as **not eligible for commercial use** and marks its rights status `RESEARCH_ONLY_UPSTREAM_SOURCE_RESTRICTS_COMMERCIAL_AI_MODEL_TRAINING`. It identifies Football-Data.co.uk as the underlying match-data source and ClubElo as the Elo source. The official Football-Data.co.uk policy page states that its free data is intended for private personal/academic use, is not intended for commercial or data-training projects, and that users should assume no permission is granted for those uses unless they obtain the appropriate commercial subscription. The xgabora repository README itself says the match data is taken from Football-Data.co.uk; the repository's MIT code license does not override the upstream data provider's restrictions.

External source evidence checked 2026-11-06:
- Football-Data.co.uk fair data usage policy: https://football-data.co.uk/contact.php
- Dataset repository provenance and README: https://github.com/xgabora/Club-Football-Match-Data/blob/main/README.md

**Commercial-use gate:** Do not import this dataset, its odds fields or its derived features into V2 commercial training, calibration, inference or product outputs unless an applicable commercial licence or written permission is obtained. Preserve the existing V1 copy only as an isolated audit/rollback artifact; it is not an approved V2 training source. ClubElo-derived fields require a separate rights review.

The stored V1 audit reports 238,854 normalized rows across 38 competitions, while the current upstream repository README reports 238,858 match records. The four-row difference is unexplained and must be reconciled against a pinned raw-source snapshot before any permitted research migration. The V1 coverage audit reports 37.24% missing home Elo, 37.27% missing away Elo, 34.40% missing Over 2.5 odds, 48.72% missing home shots and 49.06% missing home shots-on-target. Team names, dates and full-time scores are complete in that normalized snapshot; optional fields must retain explicit missingness and cannot be assumed present.

### 3.2 Incremental recent-results cache

The workflow restores:

`command-data/public-data/recent_results_cache.json`

before refreshing recent completed results, then publishes the updated cache back to `command-data`. The inspected public-data file was approximately 1.63 MB. Its schema stores date, competition/division, home/away names, scores, optional fixture ID, fixture status, source provider and license/attribution fields.

Rows without an explicit source are marked `LEGACY_UNATTRIBUTED` by the V1 loader. V1 live modelling has a licensed-source filter, but the cache still retains legacy rows for audit and reconciliation.

### 3.3 Report, ledger and audit artifacts

The `command-data/public-data/` tree currently contains:
- `daily_predictions.json`
- `dashboard_snapshot.json`
- `recent_results_cache.json`
- `paper_tracking_ledger.json`
- `model_validation_report.json`
- `historical_coverage_audit.json`
- `value_evidence_ledger.json`
- `verification_status.json`
- `telegram_delivery_state.json`
- OpenLigaDB attribution/licensing notices and an `archive/` directory.

The inspected 2026-11-05 report had 69 prediction records, `as_of_date=2026-11-05`, and `publication_status=PUBLISHED`. It did not contain `report_id` or `content_sha256`.

The successful workflow run `42075832565` uploaded:
- `veltrix-daily-predictions`
- `veltrix-paper-ledger`
- `veltrix-value-evidence-ledger`

All three artifacts had a 90-day retention window. The command-data publisher also writes a timestamped daily-report archive. The branch is the durable current-snapshot store; Actions artifacts are expiring copies, not a permanent database.

## 4. Website read path

- `app/report_artifacts.py` reads report, dashboard, paper ledger and model-validation JSON from `command-data/public-data/`.
- It prefers raw.githubusercontent.com and uses a bounded GitHub Contents API fallback.
- `api/telegram.py` serves dashboard data and Telegram webhook routes; `api/dashboard.py` and `api/dashboard_data.py` expose dedicated Vercel entrypoints.
- The dashboard browser code also has raw GitHub, jsDelivr and Contents API fallback routes for the public dashboard snapshot.

The website is a reader of published snapshots; it does not run the prediction model in the dashboard request path.

## 5. Telegram delivery path and report-parity defect

- `scripts/send_telegram_report.py` reads the workflow-local `reports/daily_predictions.json` and formats/sends Telegram messages.
- It uses `public-data/telegram_delivery_state.json` on `command-data` to suppress duplicate deliveries by report date and message fingerprint.
- In the workflow, Telegram delivery occurs **before** the `Publish validated command data snapshots` step.
- The publisher then writes the mutable current report and dashboard snapshot, plus a timestamped report archive.

This ordering creates a race: Telegram may receive the new report while the website still serves the previous published snapshot. The V1 report has no immutable report ID or content hash shared with Telegram. The existing fingerprint is a Telegram duplicate-suppression mechanism, not a cross-channel report identity.

**Additional market-output defect:** the Telegram `/btts` and `/overunder` handlers recalculate probabilities from expected goals instead of rendering the exact saved market outputs. V2 delivery must be presentation-only: no probability model or calibration code may run in the Telegram or website adapter.

**V2 requirement:** create and validate one immutable report, compute its content hash, publish it successfully, then have both website and Telegram consume that exact report ID/hash. Delivery must be idempotent and must not send a report whose publication failed.

## 6. Publication mechanics and failure surface

`scripts/publish_command_data.py` writes current snapshots to `command-data` and separately creates a timestamped archive. It uses the GitHub Contents API for ordinary-size files and Git Data API for larger files. It retries optimistic-concurrency conflicts for large-blob publication.

The script publishes report, dashboard, archive and optional ledgers as separate operations. It collects per-snapshot errors and returns failure if any operation fails, but the individual writes are not one atomic multi-file transaction. The report is marked `PUBLISHED` in its payload before the individual publication attempts finish; a failed report write can therefore coexist with a different snapshot having been written successfully. V2 should use a manifest/commit-level publication boundary and only mark a report published after the authoritative artifact and manifest are durable.

## 7. Storage conclusion

The audited V1 reporting path is primarily GitHub-backed:
- Durable current snapshots and state: `command-data/public-data/`.
- Immutable report archive: `command-data/public-data/archive/`.
- Expiring workflow copies: GitHub Actions artifacts (90 days in the inspected workflow).
- Historical base data: externally hosted open CSV, downloaded afresh into the workflow workspace and not retained by the inspected artifact steps.
- Recent completed-results history: persistent `recent_results_cache.json` on `command-data`.

The previously inspected Neon projects were not football databases. No V1 football database was established from this audit. This is not a claim that no database exists anywhere; it means no database dependency was found in the traced report path and no safe football database target has been proven.

## 8. Data-rights gate

The data-rights register is maintained in `docs/v2/DATA_RIGHTS_REGISTER.md`. The historical Football-Data.co.uk-derived dataset is currently BLOCKED for commercial model training; a repository-level MIT label is not sufficient evidence of downstream data rights. V2 training must use only sources with documented rights appropriate to the intended use. This restriction is independent of data quality, row count or technical availability.

## 9. V1 component retirement mapping

The complete component-to-replacement map is maintained separately in `docs/v2/V1_RETIREMENT_MAP.md`. Key dependency rules:
- V1 provider adapters and identity functions are not reusable V2 implementation dependencies; rebuild them behind V2 ports/adapters and canonical identity contracts.
- V1 model and prediction functions are excluded entirely from V2. The V2 model layer must consume only V2 point-in-time feature snapshots.
- V1 report filtering and Telegram commands must not be reused as V2 publication gates or market calculators.
- Existing website routes, dashboard shell, Telegram webhook/bot credentials and transport are retained only as delivery infrastructure; their data adapters are replaced with immutable V2 report readers.
- `command-data` and all V1 snapshots remain read-only audit/rollback sources until a controlled cutover.

## 10. Remaining Phase 1 work

1. Finish the function-level V1 call graph for all research verification, report filtering, value gates and Telegram command endpoints; neutral-prior, sparse-history, Elo/Poisson, odds matching and Telegram recalculation paths are now confirmed.
2. Inventory all workflow artifacts and archive files; record retention, sizes, checksums, report dates and model/version provenance.
3. Reconcile the upstream open CSV snapshot against the historical coverage audit and recent-results cache, including duplicate and missing-date analysis.
4. Obtain documented commercial rights for any historical source proposed for V2; reconcile the 238,854 versus 238,858 row count and review ClubElo-derived fields separately.
5. Validate the component retirement map against every live workflow/API call site.
6. Prove backups and a restore path before selecting any V2 migration target.

**No migration, data download/backfill, production write, secret read/change, Vercel setting change or deployment promotion was performed as part of this audit.**
