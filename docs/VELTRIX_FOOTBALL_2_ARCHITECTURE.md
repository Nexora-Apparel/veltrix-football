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

This is foundational implementation only. It does not fit a model, generate a forecast, import legacy code or activate prediction delivery. Next modules are ingestion normalization and identity crosswalk contracts, followed by feature lineage and point-in-time feature snapshots after data acceptance.
