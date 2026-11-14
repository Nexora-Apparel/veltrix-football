# VELTRIX FOOTBALL 2.0 — Reliability and uncertainty diagnostics v1

## Calibration

- 1X2 calibration is reported one-vs-rest for HOME, DRAW and AWAY.
- BTTS Yes and Over 2.5 are binary calibration curves.
- Equal-width probability bins report count, mean predicted probability and observed frequency.
- Empty bins are omitted; bins are not interpreted as stable when sample counts are small.

## Uncertainty

Paired per-fixture score improvements are calculated as baseline loss minus model loss. Whole UTC kickoff dates are resampled with replacement, preserving within-day clustering. The evaluator reports percentile 95% intervals for Brier and log-loss improvement.

- Positive improvement means the model scored better than the baseline.
- A positive lower 95% bound is evidence of superiority on the evaluated sample only.
- Fewer than two distinct kickoff dates yields no interval.
- Bootstrap seed and replicate count are recorded for reproducibility.

## Boundaries

These diagnostics do not establish prospective skill or production readiness. They do not replace the minimum walk-forward and prospective sample requirements, bookmaker comparison, data provenance, calibration review, or independent release approval. They are descriptive evidence, not a mechanism to unlock publication.
