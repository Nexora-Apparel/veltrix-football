# VELTRIX 2.0 value-bet certification contract

Date: 2026-11-11

## Purpose

`veltrix_v2/evaluation/certification.py` is the fail-closed value-bet certification gate for the 1X2, BTTS and totals markets. Prediction publication has a separate gate, `certify_prediction_publication`, and does not inherit prospective ROI or odds requirements. It validates evidence records; it does not create evidence, run a backtest, settle selections, or infer missing values.

## Per-market requirements

Each of 1X2, BTTS and totals must independently provide:

- At least 1,000 chronological walk-forward matches.
- At least 300 prospective settled selections.
- At least 90 distinct prospective dates.
- At least 98% timestamped odds coverage.
- Net ROI strictly greater than zero.
- A lower 95% ROI confidence bound strictly greater than zero.
- ROI uncertainty method exactly `date_block_bootstrap_by_match_date`, calculated from source-backed match dates and source-observation provenance.
- Explicit source approval and point-in-time validation.

The 1X2 market must additionally beat the bookmaker benchmark on both multiclass Brier score and log loss on the exact same settled fixture sample.

## Fail-closed behavior

All three markets must be present exactly once. Missing evidence, duplicate markets, invalid values, non-positive ROI, insufficient samples, an unapproved source, missing point-in-time proof, missing source-backed match dates, IID-only ROI uncertainty or a failed 1X2 benchmark blocks the entire value-bet certification. No partial market is certified by this contract.

## Interpretation

A passing result means the supplied evidence satisfies the configured gates; it is not a guarantee of future profits or 80% hit rate. The evidence itself must be reproducible, source-audited, chronologically generated, and independently reviewable. A synthetic test can verify gate logic but cannot satisfy a production certification requirement.

## Separate prediction publication gate

Prediction publication requires, for each market, at least 1,000 chronological walk-forward matches, approved sources, point-in-time validation, passing leakage tests and passing calibration checks. It does not require 300 prospective bets, 90 prospective dates, positive ROI, 98% odds coverage or bookmaker superiority. These are intentionally excluded so a controlled predictions-only launch can occur without enabling value betting.

The report builder accepts a passing prediction certification and independently accepts the full value-bet certification. Without a passing value-bet certification, it forces every value-bet verdict to `LOCKED — NOT CERTIFIED`.

## Release boundary

No current VELTRIX market is certified by this file. The module does not activate forecasts, value bets, website publication, Neon writes, Vercel deployment or Telegram scheduling.
