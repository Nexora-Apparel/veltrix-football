# VELTRIX FOOTBALL 2.0 — Independent Prediction Architecture

Status: architecture blueprint plus initial independent contract implementation. Model fitting, calibration, evaluation claims, publication and prediction activation remain blocked until full Phase 3 data acceptance is signed off. Foundation work is isolated from the production prediction path.
Design rule: preserve the website, APIs, Telegram infrastructure and approved historical records; rebuild prediction logic independently. No legacy prediction model, feature pipeline, probability fallback, calibrator or decision rule may be imported, wrapped or reused.

## 1. System boundaries

Retain as integration surfaces only:
- Website UI and existing dashboard/navigation.
- Existing API routes and authentication/session infrastructure.
- Telegram bot, delivery, commands and destination configuration.
- Production Neon database and migration history, with records preserved.

New prediction subsystem must be a separate package namespace, with no imports from legacy prediction modules. The first implementation is not allowed to call legacy app/live_predictions.py, app/prediction.py, app/advanced_models.py, app/calibration.py, app/backtest_engine.py or legacy fallback/prior functions.

## 2. Package architecture

Proposed package root: veltrix_v2/

```text
veltrix_v2/
  contracts/       immutable fixtures, observations, forecasts and model manifests
  ingestion/       provider adapters, provenance, snapshots and schema validation
  identity/        scoped provider team/competition/fixture crosswalks
  quality/         completeness, freshness, rights and point-in-time gates
  features/        as-of feature construction and feature lineage
  xg/              VELTRIX-owned shot-location xG model
  models/           independent goal and outcome probability models
  calibration/      market-specific out-of-fold calibrators
  evaluation/       chronological walk-forward and benchmark suite
  registry/         immutable model, feature and calibrator versions
  publication/      strict forecast publication eligibility
  cli/              reproducible build, evaluate and report commands
tests/veltrix_v2/   isolated unit, contract, leakage and regression tests
```

All package boundaries are enforced by import-boundary tests. No v2 module may import legacy prediction code.

## 3. Immutable data contracts and provenance

Every provider observation is append-only and carries:
- provider, endpoint, provider entity IDs and source competition/season;
- retrieved_at_utc, source_event_time_utc and available_at_utc;
- raw payload SHA-256 and normalized record hash;
- schema version, source status, correction lineage and quality flags;
- rights/entitlement approval identifier and data-type approval;
- explicit valid-time interval where source data can be revised.

Feature construction uses only observations whose available_at_utc is less than or equal to the forecast cutoff. Current provider responses must never be backdated to earlier decision times. Re-fetches create new observations; they never silently overwrite previous values.

Provider IDs remain provider-scoped. Crosswalks require independent evidence, competition and season scope, one-to-one uniqueness and explicit reviewer approval. Fuzzy matching is diagnostic only and cannot create canonical links.

## 4. Data quality and publication gates

Before a fixture enters feature construction:
- competition and provider entitlement are approved for the exact data type;
- fixture identity is unique, home/away orientation is valid and kickoff is timezone-aware;
- result status and score are internally consistent for completed matches;
- source freshness, completeness and retrieval timestamps satisfy the feature policy;
- conflicting, ambiguous, duplicate or quarantined identities are excluded;
- provider-modelled fields are not mislabeled as observed values.

Missing or weak evidence is represented as missing with a reason code. No global home/away prior, default probability vector, generic fallback, forced prediction or silent source substitution is allowed. If the feature/model support is insufficient, publication is suppressed and the reason is retained internally.

## 5. Independent feature engineering

All features are computed sequentially and as-of the forecast timestamp. Initial feature families:
- Team attack/defence strength: opponent-adjusted goals for/against and shot-quality rates.
- Recent form: exponentially weighted and rolling windows with explicit match counts and uncertainty.
- Shot process: shot volume, shot location, shot quality and VELTRIX-owned xG; provider xG is context-only until point-in-time provenance is proven.
- Match context: home advantage, competition, surface/venue where verified, rest days, schedule congestion and travel distance only when source evidence exists.
- Lineup availability: expected XI, confirmed XI, player availability and replacement strength only when timestamped before kickoff.
- Market context: de-vigged bookmaker probabilities and timestamped movement as a separate benchmark/input family, never as a leaked target.

Every feature includes feature_name, value, source_observation_ids, computed_at_utc, cutoff_utc, sample_size and quality state. Feature snapshots are reproducible from their manifests.

## 6. Statistical model stack

Models are developed and benchmarked independently; none is assumed superior before evaluation.

### Goal-rate family
- Independent Poisson baseline with team-specific attack and defence parameters.
- Dixon–Coles low-score dependence correction fitted only on prior data.
- Hierarchical partial-pooling goal model for sparse teams and newly promoted clubs, with explicit uncertainty and competition scope.
- Dynamic attack/defence state updates evaluated against static parameters.

### Scoreline and market derivation
- Generate a normalized joint scoreline distribution from the selected goal model.
- Derive 1X2, BTTS, totals and exact-score probabilities from the same distribution.
- Verify probability mass sums to one and market probabilities are internally coherent.
- No independent ad hoc probability chips or market-specific hidden fallback logic.

### Independent benchmark set
- De-vigged bookmaker consensus at a defined pre-kickoff timestamp.
- Simple competition baseline as a benchmark only, never as a production fallback.
- Elo-style outcome benchmark only if implemented and evaluated in the v2 package.

## 7. VELTRIX-owned xG

Fit an original shot-location model from raw shot coordinates and outcomes. Training rows must be restricted to shots observed before each model cutoff. Candidate features include distance, angle, body part, assist type and verified shot context. Fit/validate by chronological splits, calibrate shot probabilities, monitor drift and version each model. Provider-computed xG is not used as a leakage-safe historical target or feature unless its historical as-of values and model version can be demonstrated.

## 8. Calibration

- Calibrators are market-specific and model-version-specific.
- Train calibration only on chronological out-of-fold predictions generated without future data.
- Candidate methods: Platt/logistic scaling, temperature scaling for multiclass 1X2, isotonic regression only with adequate sample size.
- Compare raw model, calibrated model and expanding-frequency baseline.
- Store training cutoff, sample size, market, model hash, feature hash, calibration method and parameters.
- Never transfer calibration parameters between model versions, competitions or markets without explicit validation.
- If calibration evidence is inadequate, do not publish calibrated probabilities or unlock value screening.

## 9. Chronological evaluation

Use rolling-origin walk-forward evaluation, never random train/test splitting for release claims.

For each fold:
1. freeze a UTC training cutoff;
2. fit feature transforms, model parameters and hyperparameters only on prior observations;
3. fit calibration from earlier out-of-fold predictions only;
4. predict the next untouched time block;
5. settle outcomes only after their final status is verified;
6. retain predictions, source snapshots, model manifest and evaluation metrics immutably.

Required metrics:
- 1X2: multiclass Brier score, log loss, ranked probability score and reliability by probability bin.
- BTTS/totals: binary Brier, log loss, calibration curve, precision/recall as diagnostics.
- Goal distribution: negative log likelihood and scoreline residual diagnostics.
- Benchmark comparison: paired Brier/log-loss differences against de-vigged bookmaker consensus on the same fixtures.
- Stability: competition, season, favourite/underdog, home/away, data-depth and probability-band slices.
- Value screening only after separate prospective evidence, timestamped odds coverage, ROI and confidence-bound gates are met.

All uncertainty intervals use date-clustered resampling where match-date dependence matters. Small samples are reported as insufficient evidence, not success.

## 10. Release gates

Prediction delivery stays disabled until:
- provider/competition/data-type rights and import qualification pass Phase 3;
- all feature lineage and point-in-time leakage tests pass;
- chronological walk-forward samples meet predeclared minimums;
- 1X2 beats de-vigged market Brier and log loss on full and recent holdouts;
- each binary market beats raw and historical-frequency calibration baselines;
- model artifacts are reproducible from immutable manifests;
- production can suppress unsupported or stale forecasts without fallback;
- website, scheduled report and Telegram render the same validated forecast snapshot.

Existing value certification thresholds remain separate and unchanged: at least 1,000 walk-forward matches per market, at least 300 settled prospective selections across at least 90 distinct dates, 98% timestamped odds coverage, positive net ROI and positive lower 95% ROI bound; 1X2 must also beat bookmaker Brier and log loss. No value market is unlocked by this architecture document.

## 11. Delivery sequence after Phase 3

1. Implement immutable v2 contracts and import-boundary tests.
2. Implement provider snapshot ingestion and isolated data-quality gates.
3. Implement point-in-time feature store and feature lineage.
4. Implement VELTRIX-owned xG from raw shot locations where licensed and available.
5. Implement independent Poisson and Dixon–Coles goal models.
6. Implement hierarchical sparse-team model and compare it against simpler baselines.
7. Implement market-specific calibration and immutable model registry.
8. Implement rolling-origin walk-forward evaluator and bookmaker benchmark.
9. Implement strict publication gate and API/Telegram adapters.
10. Shadow-run validated reports before any public prediction activation.

## 12. Current gate

Phase 3 is not fully signed off. The 2026-11-11 acceptance record allows only limited fixture/results sources for the next import dry-run. The Python Neon acceptance runner, isolated provider-backed import dry-run and written NWSL clarification remain outstanding. Therefore this branch contains architecture only; it must not be merged as production prediction code or deployed as an active prediction system.


## 11. Initial implementation record — 2026-11-11

The isolated `veltrix-2.0-architecture-blueprint` branch now contains:
- `veltrix_v2/contracts/observations.py`: immutable provider-observation, fixture-identity and forecast-cutoff contracts.
- UTC normalization and timezone-awareness enforcement.
- SHA-256 format validation, required provenance and rights-approval identifiers.
- Explicit point-in-time availability checks.
- `tests/veltrix_v2/test_observation_contracts.py`: contract tests for immutability, timestamp validity, hash validation, cutoff enforcement and distinct team identity.
- `veltrix_v2/features/snapshot.py`: immutable feature-value and feature-snapshot contracts with shared cutoff, source-observation lineage, sample-size, quality-state and missing-reason enforcement.
- `tests/veltrix_v2/test_feature_snapshots.py`: tests for missing-value semantics, duplicate features, future computation and non-finite values.
- `veltrix_v2/identity/crosswalk.py`: competition- and season-scoped provider-team crosswalks; only explicitly approved mappings resolve, while ambiguous mappings fail closed.
- `tests/veltrix_v2/test_identity_crosswalk.py`: tests for approval state, scope isolation and ambiguous mapping rejection.
- `veltrix_v2/ingestion/observations.py`: provider-neutral immutable observation builder with deterministic, order-independent SHA-256 payload hashing.
- `tests/veltrix_v2/test_ingestion_observations.py`: payload-hash stability and provenance binding tests.
- `veltrix_v2/quality/eligibility.py`: fail-closed provider/competition/data-type rights approval, validity-window, point-in-time availability and freshness gates.
- `tests/veltrix_v2/test_source_eligibility.py`: approved-scope, provisional, future-data, stale-data and expired-approval tests.

This is foundational implementation only. It does not fit a model, generate a forecast, import legacy code or activate prediction delivery. Next modules are ingestion normalization and identity crosswalk contracts, followed by feature lineage and point-in-time feature snapshots after data acceptance.


### 2026-11-11 continued — first point-in-time feature builder

Added `veltrix_v2/features/team_form.py` and `tests/veltrix_v2/test_team_form.py`:
- Immutable settled-match input with provider fixture/team IDs, competition-season scope, kickoff, result-availability timestamp, final status, score and source-observation ID.
- As-of filtering requires kickoff strictly before cutoff and result availability no later than cutoff; wrong competitions/seasons and future/unavailable records are excluded.
- Recency-weighted goals-for, goals-against and points-per-match features over a bounded last-N match window.
- Explicit low-sample state; zero-history features are missing with a reason, never replaced by a generic prior.
- No provider requests, database writes, model fitting, prediction generation or legacy imports.
- The new feature builder is isolated to the v2 architecture branch and is not wired to production or publication.


## 13. Repository and integration audit — 2026-11-11

### V2 implementation audit

- Audited all 53 Python source files under `veltrix_v2/`, all five operational scripts under `scripts/veltrix_v2/`, and all 48 V2 test modules.
- Static scan found no TODO/FIXME/NotImplemented/placeholder markers in the V2 source modules or operational scripts. The only `pass` statement in those scripts is the body of the `ProbeError` exception class.
- V2 test files contain no pytest skip, skipif or xfail markers.
- Latest verified V2 foundation suite: 371 passed. Latest verified full repository suite: 869 passed. The legacy-import boundary test passed.
- The feature snapshot cutoff contradiction, direct certified-report construction bypass, Python invalid-escape warning, and historical runner entitlement mismatch have been corrected with regression tests.
- The historical runner now checks `GET /v1/status` before downloading data: Free is capped at 90 days; Community/approved paid tiers may request up to 365 days; unknown plans fail closed. Lookbacks above 90 days require at least 300 observed history days. Default request budget is 30; the 1,000 held-out-match gate is unchanged.
- The Community country-pack filter supports Argentina, Brazil and Nigeria. No country pack has been activated or assumed.

### Existing production integration boundary — not yet migrated

The website/API/Telegram infrastructure is retained, but its data path is still legacy and must not be treated as V2:

- `api/dashboard.py`, `api/dashboard_data.py` and `api/index.py` route into `api/telegram.py`.
- `api/telegram.py` still imports `app.telegram_commands`, `app.report_artifacts` and `app.telegram_security`. Its dashboard payload and Telegram output still read legacy report artifacts.
- `scripts/run_daily_predictions.py` imports `app.live_predictions`, legacy provider adapters and legacy value-intelligence/runtime modules. It is not a V2 runner and must remain disabled.
- The current website/Telegram renderer still contains legacy statuses such as `EXPERIMENTAL_ONLY` and `EXPERIMENTAL_LOW_DATA`. Remove those labels when the V2 publication adapter replaces the legacy report payload; do not merely rename legacy forecasts.
- V2 has a certified-report renderer and Telegram delivery-receipt validator, but neither is connected to the production API, website, Telegram transport or Neon persistence yet. No V2 prospective paper ledger or production orchestrator has been verified.

### Workflow and release safety

- All 28 workflow files were checked. None currently has an active `schedule` trigger. The daily prediction job and daily watchdog job are disabled with `if: false`; recent PR pushes show the daily prediction workflow skipped.
- Provider verification is now manual-only. Its optional BTTS probe is opt-in and capped at eight The Odds API credits across the top-five leagues plus Argentina and Brazil. No live odds-market probe has been run.
- The latest provider smoke check confirmed 5Dollar Free access to the top five leagues and sampled five EPL fixtures (1X2 5/5, BTTS 3/5, O/U 2.5 5/5). The Odds API key is authenticated with 46 soccer sports and 298 remaining credits at the time of the check. These are provider access/coverage observations, not model-performance evidence.
- PR #51 remains draft and unmerged. No Vercel deployment was attempted; the Vercel check reports its external build-rate limit.

### Remaining gates

1. Finish the full legacy/integration inventory and preserve only required website/API/Telegram infrastructure; do not reuse legacy prediction logic.
2. Complete provider rights and account qualification. Community Access is a manual account action; Argentina is the strongest one-country-pack candidate by the provider's current 12-month match counts, but entitlement must be confirmed from `/v1/status`.
3. Run the plan-appropriate historical diagnostic and inspect its artifact. Historical 5Dollar availability uses a conservative four-day proxy and is not point-in-time certifiable.
4. Build prospective, timestamped odds and settled-selection evidence; do not claim CLV or ROI certification from historical closing fields.
5. Complete model validation and publication gating before website/Telegram integration.
6. Connect the same immutable V2 report to website, API and Telegram; verify delivery receipt and 06:00 WAT timing before enabling any schedule.
7. Complete controlled production acceptance. No merge, deployment, Neon production writes, Telegram activation or daily schedule before all gates pass.


## 14. Legacy repository disposition map — 2026-11-11

The following classification is an integration/retirement plan, not permission to delete production files before the V2 replacement is accepted.

| Existing surface/module | Disposition | Migration rule |
|---|---|---|
| `api/index.py`, `api/dashboard.py`, `api/dashboard_data.py` | Preserve as routing surfaces | Keep endpoint URLs and authentication/session compatibility; replace only the report-data source after V2 acceptance. |
| `api/telegram.py` | Preserve transport and UI shell; replace legacy data backend | Keep FastAPI routes, webhook verification, dashboard navigation and delivery transport. Remove legacy report loaders/status logic and render only a validated V2 report. |
| `app/telegram_security.py` | Preserve security behavior | Keep webhook secret-token validation and regression tests. |
| `app/telegram_commands.py` | Preserve command interface only | Keep command names/UX where useful; rewrite handlers to call the V2 report and tracking services. Do not reuse legacy prediction selection logic. |
| `app/report_artifacts.py` | Preserve storage/transport pattern only | Version the payload schema and store immutable V2 report artifacts; do not expose legacy report JSON as V2. |
| `app/config.py` | Review and selectively preserve configuration | Reuse only generic environment/config parsing; remove credentials and provider settings for retired sources. |
| `app/live_predictions.py`, `app/prediction.py`, `app/advanced_models.py`, `app/poisson_dc_head.py`, `app/team_form.py`, `app/calibration.py`, `app/goal_market_calibration.py`, `app/backtest_engine.py`, `app/bias_audit.py` | Retire legacy prediction/model logic | No imports, wrappers, model reuse, fallback reuse or silent feature reuse in V2. |
| `app/provider_adapters.py`, `app/recent_results.py`, `app/football_api.py`, `app/api_football_odds.py`, `app/oddspapi_odds.py`, `app/bookmaker_odds.py`, `app/live_odds.py` | Retire legacy provider/odds logic | Replace with qualified V2 provider adapters and immutable observations. Exclude suspended or unlicensed providers. |
| `app/fixture_identity.py`, `app/historical_data.py`, `app/market_evidence.py`, `app/research_evidence.py`, `app/research_verification.py` | Audit individually; do not import into V2 | Preserve raw historical records only when source rights and provenance pass. Rebuild identity, feature and benchmark logic inside V2 contracts. |
| `app/paper_tracking.py`, `app/value_bets.py`, `app/value_bets_runtime.py`, `app/value_intelligence.py`, `app/value_intelligence_runtime.py`, `app/value_evidence_ledger.py`, `app/value_paper.py` | Retire legacy value/paper logic | Rebuild settlement, prospective ledger, ROI and CLV using V2 contracts and certification evidence. Value betting remains locked until every release gate passes. |
| `scripts/run_daily_predictions.py`, `scripts/backfill_history_gaps.py`, `scripts/filter_report_for_delivery.py`, `scripts/audit_historical_model.py`, `scripts/run_paper_tracking.py`, `scripts/send_telegram_report.py` | Keep disabled; replace with V2 orchestration | Do not reactivate or patch the legacy daily pipeline. Replace with one V2 orchestration path only after provider, model and publication acceptance. |
| Legacy daily prediction/watchdog workflows | Keep disabled until replacement | No schedule or Telegram delivery is re-enabled before the V2 controlled-release gate. Remove obsolete workflows after V2 replacement is verified. |

The existing repository's legacy tests may remain temporarily as archival regression tests for preserved infrastructure, but passing legacy-model tests do not qualify any legacy model for V2 reuse. The V2 import guard now rejects any `app.*` dependency from both `veltrix_v2/` and `scripts/veltrix_v2/`.


## 15. Script inventory and disposition — 2026-11-11

| Script group | Existing scripts | Disposition |
|---|---|---|
| V2 operational | `scripts/veltrix_v2/*` | Preserve. Five scripts are isolated from all `app.*` imports and are covered by the V2 import-boundary check. |
| Provider qualification | `scripts/verify_data_providers.py`, `scripts/verify_goal_api.py` | Preserve as read-only/manual qualification tools. The Odds API BTTS probe is opt-in and quota-capped. GOAL API results remain technical-only until rights are cleared. |
| Telegram infrastructure | `scripts/configure_telegram_webhook.py`, `scripts/test_telegram_webhook_live.py` | Preserve webhook setup/security testing. Keep live tests opt-in and never send production messages during CI. |
| Generic publishing/visibility | `scripts/publish_command_data.py`, `scripts/publish_model_validation.py`, `scripts/publish_verification_status.py`, `scripts/validate_fixture_visibility.py` | Preserve transport/validation mechanics only; adapt to immutable V2 schemas and the V2 report ID. |
| Historical data audit/import | `scripts/audit_historical_csv.py`, `scripts/import_open_dataset.py`, `scripts/import_womens_club_history.py` | Read-only or quarantined until source rights, lineage, timestamp semantics and retention permissions pass. |
| Legacy model/provider/value pipeline | `scripts/audit_historical_model.py`, `scripts/audit_historical_coverage.py`, `scripts/backfill_history_gaps.py`, `scripts/build_value_certificate.py`, `scripts/build_value_certificate_runtime.py`, `scripts/build_value_certificate_runtime_v2.py`, `scripts/enrich_oddspapi_odds.py`, `scripts/evaluate_paper_predictions.py`, `scripts/filter_report_for_delivery.py`, `scripts/rebuild_value_screen.py`, `scripts/reconcile_value_evidence_recovery.py`, `scripts/run_backtest.py`, `scripts/run_daily_predictions.py`, `scripts/run_paper_tracking.py`, `scripts/send_telegram_report.py`, `scripts/update_value_evidence_ledger.py`, `scripts/verify_multi_source_integration.py` | Retire or replace with V2 equivalents. Do not patch or import their legacy prediction, calibration, odds-selection, value-bet, settlement or paper-tracking logic. For `send_telegram_report.py`, only the generic Telegram HTTP transport may be considered for reuse after review. |

The script inventory confirms that the legacy daily prediction path is not a V2 adapter. The current V2 historical runner and provider verification harness are the only scripts approved for V2 data qualification; neither publishes predictions or writes production records.
