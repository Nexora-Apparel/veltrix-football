# VELTRIX 2.0 release certification contract

Date: 2026-11-11

## Purpose

`veltrix_v2/evaluation/certification.py` is the fail-closed release gate for the 1X2, BTTS and totals markets. It validates evidence records; it does not create evidence, run a backtest, settle selections, or infer missing values.

## Per-market requirements

Each of 1X2, BTTS and totals must independently provide:

- At least 1,000 chronological walk-forward matches.
- At least 300 prospective settled selections.
- At least 90 distinct prospective dates.
- At least 98% timestamped odds coverage.
- Net ROI strictly greater than zero.
- A lower 95% ROI confidence bound strictly greater than zero.
- ROI uncertainty method exactly `chronological_block_bootstrap_by_match_date`.
- Explicit source approval and point-in-time validation.

The 1X2 market must additionally beat the bookmaker benchmark on both multiclass Brier score and log loss on the exact same settled fixture sample.

## Fail-closed behavior

All three markets must be present exactly once. Missing evidence, duplicate markets, invalid values, non-positive ROI, insufficient samples, an unapproved source, missing point-in-time proof, IID-only ROI uncertainty or a failed 1X2 benchmark blocks the entire release. No partial market is certified by this release contract.

## Interpretation

A passing result means the supplied evidence satisfies the configured gates; it is not a guarantee of future profits or 80% hit rate. The evidence itself must be reproducible, source-audited, chronologically generated, and independently reviewable. A synthetic test can verify gate logic but cannot satisfy a production certification requirement.

## Release boundary

No current VELTRIX market is certified by this file. The module does not activate forecasts, value bets, website publication, Neon writes, Vercel deployment or Telegram scheduling.
