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

This confirms the scheduler and principal report path. A complete function-by-function call graph of every imported V1 model and helper is still outstanding.

## 3. Historical data: what is actually persisted

### 3.1 Open historical dataset

`scripts/import_open_dataset.py` downloads:

`https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data/main/data/Matches.csv`

It normalizes rows and writes the requested output, normally `data/open_historical_matches.csv`.

The daily workflow invokes it from `2020-01-01` through the current UTC date on scheduled, manual and controlled live-verification runs. This is a full historical source download/import, not an incremental local update.

The `main` repository root has no committed `data/` directory. The inspected daily workflow uploads report, paper-ledger and value-evidence artifacts, but does not upload `data/open_historical_matches.csv`. Therefore the normalized CSV is an ephemeral workflow-run input, not a durable V1 snapshot in the repository or the listed workflow artifacts.

The importer records the upstream repository/source in its normalized rows and import summary, but the inspected schema has no stable provider fixture ID for each open-dataset row. Exact row counts, duplicate reconciliation, license terms and a checksum for the currently imported upstream snapshot still need to be verified.

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

## 8. Remaining Phase 1 work

1. Finish the function-level V1 call graph for identity reconciliation, all prediction/model branches, odds matching, research verification, report filtering, value gates and Telegram command endpoints.
2. Inventory all workflow artifacts and archive files; record retention, sizes, checksums, report dates and model/version provenance.
3. Reconcile the upstream open CSV snapshot against the historical coverage audit and recent-results cache, including duplicate and missing-date analysis.
4. Verify the source dataset's license/redistribution conditions and whether the current import workflow's full re-download is necessary.
5. Identify every legacy prediction/report call site and map it to its V2 replacement.
6. Prove backups and a restore path before selecting any V2 migration target.

**No migration, data download/backfill, production write, secret read/change, Vercel setting change or deployment promotion was performed as part of this audit.**
