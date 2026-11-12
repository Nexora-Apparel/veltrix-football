# VELTRIX FOOTBALL 2.0 — Phase 1: Evidence-Bound Certification Integrity

**Status:** IN PROGRESS — release gate hardened; full source-attested evidence verifier remains outstanding.

## Objective

Prevent caller-supplied JSON fields, status labels, booleans, market lists or synthetic metrics from authorizing value-bet alerts. Certification must be derived from authentic, immutable model-evaluation artifacts and the prospective paper ledger, with exact model/calibration version binding and independently recomputed thresholds.

## Verified defect

The previous runtime predicate `app.value_bets._certificate_allows` accepted a mapping when `status` was `VALIDATED`/`PARTIALLY_VALIDATED`, `schema_version` was `1`, the requested market appeared in `approved_markets`, and `betting_validation` was `true`. Those fields can be fabricated by any caller; the predicate did not verify the underlying report bytes, ledger rows, hashes, model versions, timestamped odds, or CI calculation. Telegram also treated report-level status labels (`PASSED`, `CERTIFIED`, `APPROVED`) as release authority.

## Implemented containment

- `_certificate_allows` now fails closed for every externally supplied certificate object.
- Telegram report formatting no longer treats a report-supplied status label as authority to release value candidates.
- Runtime tests assert that forged `VALIDATED` and `PARTIALLY_VALIDATED` objects cannot release candidates; candidates remain paper-only.
- No model, prediction, database, deployment, Telegram delivery or schedule activation was performed.

## Remaining Phase 1 acceptance work

1. Define an evidence manifest schema binding exact immutable backtest report, coverage audit, prospective ledger and odds-snapshot artifact hashes.
2. Recompute per-market walk-forward sample counts, prospective settled selections, distinct dates, timestamped odds coverage, net ROI and date-clustered 95% lower bound from raw rows; reject caller-supplied summary numbers.
3. Verify point-in-time feature availability, pre-kickoff quote timestamps, settlement provenance, fixture/model/calibration version consistency, and no duplicate fixture-market selections.
4. Bind 1X2 Brier/log-loss comparisons to the same fixtures and same cutoff against de-vigged bookmaker consensus for both full and recent holdout windows.
5. Add adversarial tests for fabricated counts, fabricated ROI/CI, duplicated dates, stale/post-kickoff odds, altered hashes, model-version mismatch, leakage, and cross-market evidence reuse.
6. Require source-attested artifact verification before any certificate can enable runtime or Telegram value output.
7. Run the complete CI suite and verify all downstream consumers use the same verified certificate result.

## Mandatory thresholds

- At least 1,000 chronological walk-forward settled matches per market.
- At least 300 prospective settled selections per market.
- At least 90 distinct match dates per market.
- At least 98% timestamped pre-kickoff odds coverage per market.
- Net ROI greater than zero and date-clustered 95% lower ROI confidence bound greater than zero.
- 1X2 must beat the de-vigged bookmaker baseline on both Brier score and log loss in full and recent-holdout same-fixture comparisons.

No threshold is waived by this containment patch. Value betting remains locked until Phase 1 verification and the downstream certification gates pass.
