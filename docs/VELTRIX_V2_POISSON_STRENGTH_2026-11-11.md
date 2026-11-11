# VELTRIX 2.0 — leakage-safe team Poisson estimator — 2026-11-11

## Added
- `veltrix_v2/models/poisson_strength.py`
- `tests/veltrix_v2/test_poisson_strength.py`

## Estimator
- Fits competition-season-specific attack and defence log strengths with a joint Poisson likelihood.
- Separate home-advantage parameter; recency-weighted observations; L2 shrinkage on team strengths and home advantage.
- Deterministic Adam optimization with centered attack/defence effects and explicit convergence status.
- Produces expected-goal rates for known teams only. Unseen teams fail closed; no global/home fallback is generated.
- Training requires a competition-season scope, timezone-aware kickoff, actual source-availability timestamp, valid quality state, unique fixture and observation IDs.
- Excludes matches not kicked off before cutoff, results not available by cutoff, quarantined rows, and other competitions/seasons.
- Minimum total matches and per-team coverage are enforced. Training provenance IDs and objective/convergence diagnostics are retained.

## Data boundary
Only synthetic test data is used by tests. No real provider dataset is fitted. The component is ready for controlled research after source data acceptance; this commit does not certify any source or remove third-party terms.

## Release boundary
No calibration, backtesting, Neon writes, production predictions, deployment or Telegram publication. Model parameters are not production approved.
