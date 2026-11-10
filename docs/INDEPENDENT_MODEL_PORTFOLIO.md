# VELTRIX Football 2.0 — Independent Model Portfolio

**Status:** Architecture and initial Elo feature component in development. No model is certified or publishable.

## Design objective

Improve probability quality through independent model families, strict point-in-time data, chronological evaluation and market-specific calibration. Do not maximize raw hit rate at the expense of probability calibration or price value. Evaluate log loss, Brier score, calibration error, discrimination and ROI only where timestamped odds support it.

## Candidate model portfolio

### 1. Results-history logistic baseline — implemented, diagnostic only
- Separate 1X2 multinomial, BTTS binary and Over 2.5 binary heads.
- Regularized deterministic fitting.
- Results-derived rolling attack/defence, form, rest, competition baselines and Elo-difference features.
- Purpose: transparent baseline and benchmark, not assumed champion.

### 2. Chronological Elo strength model — feature engine implemented
- Competition-scoped rating histories.
- Settled-match chronology, home advantage and goal-margin update.
- No cross-league transfer or default strength borrowing.
- Produces rating difference and history counts as model features, not market probabilities.
- Must be tested against static and alternative K-factor variants in walk-forward evaluation.

### 3. Goal-count model family — fitted shadow implementation added
- `app/poisson_dixon_coles_model.py` fits separate competition-scoped home/away scoring intercepts and team attack/defence effects from settled training rows.
- L2 regularization and within-competition identifiability constraints; optional exponential time-decay weights.
- Dixon-Coles rho is estimated by deterministic profile-likelihood grid search on training rows only.
- Uses `app/poisson_dc_head.py` to derive 1X2, BTTS and half-goal totals from the corrected scoreline matrix; material Poisson tail mass fails closed.
- Artifacts bind dataset digest, train/validation/test fixture manifests, training cutoff, training timestamp, source digest and configuration.
- Inference verifies artifact integrity and point-in-time ordering. Unknown competitions/teams abstain.
- Research-only; no publication or value betting. Unit/CI tests do not constitute real-data training or accuracy certification.

### 4. Nonlinear tabular challenger — next
- Gradient-boosted trees (candidate: LightGBM or CatBoost) for 1X2, BTTS and totals.
- Dependency and deterministic training environment must be pinned before adoption.
- Competition-aware validation and leakage-safe feature availability required.
- Compare against logistic and goal-count models; reject if gains do not persist across time origins.

### 5. Market-specific ensemble — later
- Combine only independently evaluated out-of-fold predictions.
- Learn ensemble weights on chronological validation data only.
- No in-sample stacking, test-set tuning or fixed hand-picked weights.
- Allow a market to select a different champion; do not force one universal model.

### 6. Calibration layer — implemented, diagnostic only
- Temperature scaling for 1X2.
- Platt scaling for BTTS and Over 2.5.
- Fit on validation partitions only; calibration time must precede test prediction cutoffs.
- Compare reliability diagrams, Brier and log loss before and after calibration.

### 7. Drift and uncertainty layer — planned
- Detect competition/team data sparsity, feature drift and calibration drift.
- Estimate uncertainty and abstain when evidence is insufficient.
- No generic priors, default-home probabilities or favourite-only publication.

## Shared data and evaluation requirements

- Exact fixture identity and provenance-bound raw payloads.
- Point-in-time features strictly before kickoff.
- Labels available only after their independently evidenced availability time.
- Chronological train/validation/test splits with embargo.
- Multi-origin walk-forward testing, per-competition and per-market reporting.
- Baselines: empirical training frequency, market-implied probabilities where timestamped odds exist, and simple goal-rate models.
- Report sample counts, date coverage, Brier, log loss, calibration and confidence intervals.
- Compare every candidate on identical fixture sets and cutoffs.
- No model promotion based on synthetic fixtures or one random split.

## Current blockers

1. No historical training dataset has been assembled.
2. Current 5Dollar and StrikerAPI documented schemas lack an exact wall-clock settlement timestamp.
3. The prospective availability ledger/collector are not yet connected to persistent storage or scheduled polling.
4. StrikerAPI 17-competition qualification remains blocked by HTTP 402.
5. No actual model training, real-data calibration, or real-data walk-forward comparison has occurred.

## Promotion policy

A model remains a challenger until it beats the current champion on repeated chronological out-of-sample origins, by market and competition, with sufficient samples and statistically defensible improvement. Value betting remains separately locked to its certification thresholds. Predictions, Telegram and schedules remain paused until all release gates pass.

## Release certification evaluator

`app/market_release_certification.py` provides a pure, fail-closed evaluator for the release thresholds. It consumes a complete evidence bundle for each of 1X2, BTTS and Over 2.5 and reports each gate independently:
- At least 1,000 chronological walk-forward fixtures per market.
- At least 90 distinct WAT dates in both walk-forward and prospective samples.
- At least 300 prospective settled selections per market.
- At least 98% of walk-forward fixtures with timestamped bookmaker decimal odds captured no later than kickoff.
- Positive net prospective ROI and a positive lower 95% confidence bound using a 5,000-replicate WAT-date cluster bootstrap.
- 1X2 Brier score and log loss must both beat the de-vigged bookmaker probabilities on the same odds-covered fixture set.

Every walk-forward label and prospective settlement/odds record must carry a SHA-256 evidence reference. This evaluator validates digest shape and chronology; upstream ingestion must independently resolve each digest to verified, provenance-bound source evidence before certification is trusted. It does not verify archive receipts itself.

A successful evaluator result can mark the value-betting evidence thresholds as met, but never authorizes publication. Human release approval, model promotion, operational readiness and the separate public prediction gates remain mandatory. It performs no provider requests, database writes, publication, Telegram delivery or schedule activation.

Synthetic unit tests exercise threshold boundaries and integrity failures only. They are not model performance evidence and cannot certify VELTRIX.

### Timestamped bookmaker odds evidence

`app/bookmaker_odds_evidence.py` adds a network-free, append-only observation ledger for 1X2, BTTS and Over 2.5 decimal prices. It validates complete selection sets, timezone-aware capture times, capture-before-kickoff ordering, source payload digests, overround and de-vigged implied probabilities. It supports idempotent append and selects the latest captured snapshot before kickoff for an exact fixture/market/bookmaker key.

The module intentionally does not poll an odds provider or claim fixture identity reconciliation. Provider adapters must preserve the raw response in the encrypted evidence archive, independently verify the referenced payload digest, map the provider event to a canonical fixture using a reviewed crosswalk, and then append the observation. A missing or ambiguous fixture mapping must be quarantined, not guessed.

### The Odds API evidence adapter

`app/the_odds_api_evidence_adapter.py` converts a single already-retrieved The Odds API event response into the odds evidence ledger. It supports h2h (1X2), BTTS and totals at exactly 2.5. It requires an explicit reviewed crosswalk with exact provider event ID, canonical fixture ID, kickoff and teams; ID, team or kickoff mismatch is rejected. It never guesses fixture identity. Quotes after retrieval, after kickoff or older than the configured freshness window are quarantined. The canonical event-object digest and a separately supplied SHA-256 of the exact archived HTTP response bytes, plus the crosswalk evidence digest, are bound into each observation. The offline CLI requires the exact-response digest as an explicit argument; it must be computed from the original response bytes and verified against the encrypted archive, not guessed from re-serialized JSON.

This is a pure adapter and does not call The Odds API. It is not yet connected to a scheduled acquisition worker or durable evidence archive. Provider credentials and endpoint access do not by themselves establish historical odds availability; actual timestamped quote coverage still has to be measured.

### Offline odds evidence ingestion

`scripts/ingest_the_odds_api_evidence.py` is a manual, network-free CLI that accepts one archived event JSON file plus its reviewed crosswalk and the SHA-256 of the exact archived HTTP response bytes, converts the response through the strict adapter, and atomically appends observations to a local ledger. It refuses symlink destinations, preserves the previous ledger if validation fails, and is idempotent on repeated ingestion. It never reads API credentials, calls a provider, writes Neon, publishes predictions or sends Telegram. This is a local evidence-preparation tool, not a scheduled production collector.
