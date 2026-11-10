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

### 3. Goal-count model family — next
- Independent home/away goal-rate estimators.
- Poisson scoreline matrix as a baseline.
- Dixon-Coles low-score dependence correction as a separately fitted challenger, not inherited legacy logic.
- Derive 1X2, BTTS and totals probabilities from the joint score distribution.
- Validate tail mass, scoreline calibration and low-score correction stability.

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
