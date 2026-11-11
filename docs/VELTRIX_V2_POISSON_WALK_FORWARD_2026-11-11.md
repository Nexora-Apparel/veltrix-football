# VELTRIX 2.0 — Poisson/Dixon-Coles chronological runner — 2026-11-11

## Added
- `veltrix_v2/evaluation/poisson_walk_forward.py`
- `tests/veltrix_v2/test_poisson_walk_forward.py`

## Pipeline
1. Builds expanding chronological test folds with a settlement embargo.
2. Fits the independent team Poisson estimator separately inside each fold, using only valid rows whose results were available by that fold's label cutoff.
3. Estimates expected goals for known teams only.
4. Builds a coherent Dixon-Coles scoreline distribution and derives 1X2 probabilities from the same joint mass.
5. Scores only the held-out fixtures with strict fixture-ID matching and proper scoring metrics.
6. Reports fold-level training counts, convergence, objective, forecast coverage, abstentions and aggregate Brier/log-loss/RPS.

## Fail-closed behavior
- Unknown teams abstain; no fallback forecast is generated.
- Integer O/U lines are rejected until push settlement exists.
- Rho is an explicit research input and is not fitted by this runner.
- Only synthetic fixtures are used in tests; no production or provider dataset has been evaluated.
- This runner is not a certification backtest: real walk-forward sample thresholds and prospective validation still apply.

## Release boundary
No calibration, Neon writes, deployment or Telegram publication. The runner does not claim 80% accuracy or production readiness.
