# VELTRIX FOOTBALL V1 — Prediction Stack Retirement Map

**Status:** Initial map from read-only repository inspection, 2026-11-06.  
**Scope:** Map V1 runtime components to independent V2 replacements. This is a migration plan, not authorization to disable or modify production.  
**Rule:** V2 must not import, wrap, call or subclass V1 prediction, identity, feature, calibration, eligibility, value or report-generation logic.

## 1. Retained infrastructure (replace data contracts, not the surface)

| V1 component | Treatment | V2 destination / rule |
|---|---|---|
| Vercel project, domains and route shell | RETAIN | Keep website hosting and route surface. Replace prediction data readers with V2 immutable-report adapter only after shadow validation. |
| `api/telegram.py`, `api/dashboard.py`, `api/dashboard_data.py`, `api/index.py` | RETAIN SHELL | Keep webhook/dashboard route infrastructure where safe. Remove V1 report loading and any probability calculations; render V2 report fields only. |
| Telegram bot, chat/channel, webhook credentials and transport | RETAIN | Reuse transport credentials as secret references. Delivery adapter must read the exact published V2 report ID/hash and be idempotent. |
| Existing production deployment and V1 website | RETAIN AS ROLLBACK | Do not replace until V2 passes all market, delivery, quota and rollback gates. |
| `main`, `command-data`, current V1 report artifacts and archives | READ-ONLY | Preserve as V1 provenance and rollback records. Never migrate in place or feed V1 forecasts into V2 training/calibration. |

## 2. Components to replace

| V1 component / call site | V1 responsibility | V2 replacement |
|---|---|---|
| `.github/workflows/daily-fixture-predictions.yml` | Scheduled/manual run, historical import, provider calls, model/report build, Telegram send, command-data publication | New bounded V2 scheduler/orchestrator with separate ingestion, report build, immutable publication and delivery stages. Never use a V1 workflow as a V2 runtime dependency. |
| `scripts/import_open_dataset.py` | Downloads and normalizes the external historical CSV into an ephemeral file | V2 one-time/versioned historical import pipeline with raw-source hash, license provenance, resumable batches, source IDs where available and reconciliation report. The current Football-Data.co.uk-derived source is BLOCKED for commercial training until a commercial licence/written permission is verified. |
| `app/provider_adapters.py` | 5Dollar, The Odds API, InferSports normalization and market enrichment | New `veltrix_v2/ingestion` adapters, provider request budget, raw payload archive, typed normalized records and bounded sync. Transport may be reused only via independently implemented V2 clients. |
| `app/recent_results.py` | Incremental result refresh, cache cursor, gap retry | V2 `ingestion` + `history` watermarks, provider-specific result states, idempotent persistence and explicit gap/coverage evidence. |
| `app/fixture_identity.py` | V1 normalized-name, squad/competition and kickoff matching; source provenance | New `veltrix_v2/identity` canonical registry, verified aliases, provider-local ID links, deterministic match decisions and quarantine. No V1 helper reuse. |
| `app/live_predictions.py::load_historical_matches` | Reads/normalizes CSV and constructs historical rows | V2 `history` repository and point-in-time evidence query. Preserve source-row provenance and distinguish NOT_FOUND from QUERY_FAILED and INSUFFICIENT_COVERAGE. |
| `app/live_predictions.py::predict_fixtures` | V1 history lookup, Elo/Poisson selection, sparse/global priors and probability generation | Independent V2 `features` and `models` implementations, one model per market/version, no fallback publication. |
| `app/live_predictions.py::build_daily_report` | V1 report orchestration, filtering and strict-publication cleanup | V2 `eligibility` + `reports` pipeline. Reject withheld forecasts structurally; create immutable report only from certified market outputs. |
| `app/advanced_models.py`, `app/prediction.py`, calibration modules | V1 Poisson, Dixon-Coles, Elo and goal-market calculations/calibration | New independent V2 model and calibration implementations. Algorithms may be researched independently, but no V1 source code or trained parameters may be imported. |
| `app/research_evidence.py`, `app/research_verification.py` | External source discovery and structured evidence checks | Optional V2 evidence adapter under `ingestion`/identity evidence contracts. Only verified, timestamped, licensed, pre-kickoff records may enter historical evidence. Search snippets alone are never model rows. |
| `app/value_bets_runtime.py`, `app/value_intelligence_runtime.py`, `app/value_bets.py` | Market screens, odds matching and value diagnostics | V2 `value` module using calibrated market probabilities, timestamped matched quotes and independent release certificates. Remain shadow/locked until gates pass. |
| `scripts/filter_report_for_delivery.py` | Same-day report reuse filter; imports V1 identity helpers and strips selected forecasts | V2 report validator/eligibility gate. Delivery filtering must not import identity or model logic; immutable report already contains safe fixture/market states. |
| `scripts/publish_command_data.py` | Mutable snapshot publication and timestamped V1 archives on `command-data` | V2 `reports` publisher with report ID, content hash, manifest/commit-level publication state and atomic visibility boundary in isolated V2 storage. |
| `scripts/send_telegram_report.py` | Formats and sends workflow-local report; stores duplicate guard | V2 `delivery` Telegram adapter consuming only a successfully published immutable report ID/hash. No model calculations in delivery. |
| `app/report_artifacts.py` | Reads latest mutable report/dashboard/ledger from `command-data` | V2 report repository/reader keyed by report ID and manifest. Retain V1 reader only for archived V1 surfaces during transition. |
| `app/telegram_commands.py` | Command router; reads report, but recalculates BTTS/O-U from xG in some commands | V2 presentation-only command router. It must display saved market probabilities exactly and never derive or recalibrate probabilities. |
| V1 paper ledger and value-evidence scripts | V1 model-version paper tracking and value research | New V2 prospective ledger with immutable selection time, model/calibration version, quote timestamp, settlement provenance and date-clustered metrics. Never merge V1 scores into V2 samples. |

## 3. Known V1 defects that V2 must not reproduce

1. No-history neutral priors can generate fixture probability vectors.
2. Sparse-history forecasts can retain probabilities when one team has zero or fewer than five prior matches; V1 strict-publication cleanup only strips the both-sides-zero case.
3. Non-senior fixtures have a neutral-rate fallback rather than verified category-matched evidence.
4. 1X2 can use competition Elo while BTTS/totals remain Poisson-derived; model provenance is not one coherent per-market artifact.
5. Telegram `/btts` and `/overunder` recalculate from xG instead of rendering the stored report market probabilities.
6. Telegram sends before command-data publication; website and Telegram can temporarily consume different report versions.
7. V1 publication writes mutable snapshots separately and marks the report as published before every individual write is confirmed.
8. The full historical CSV is downloaded on every scheduled run but is not retained in the inspected artifact set.
9. V1 delivery filter imports V1 identity helpers, coupling presentation to legacy matching code.

## 4. Cutover dependencies and retirement order

1. Complete source inventory, provenance reconciliation, backup/export and restore proof; establish documented commercial rights for every historical source before V2 training.
2. Build isolated V2 storage and additive migration tooling only after the source inventory is accepted.
3. Implement V2 ingestion, identity and point-in-time history; prove no source-record loss.
4. Implement V2 features, market models, calibration and independent release certificates.
5. Build immutable V2 report and verify website/Telegram report ID/hash parity in shadow mode.
6. Complete prospective validation and quota/operational tests.
7. Cut over website and Telegram through retained route/transport surfaces.
8. Disable V1 scheduled prediction/publication paths only after cutover and rollback checks.
9. Keep V1 source, artifacts, command-data and production deployment read-only until retention policy and explicit owner approval permit retirement.

**No V1 component is marked safe to reuse as prediction logic.** The retained items are infrastructure and delivery surfaces only. The historical Football-Data.co.uk-derived dataset is not approved for V2 commercial model training unless rights are cleared.
