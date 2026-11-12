# VELTRIX FOOTBALL 2.0 — Phase 1: Evidence-Bound Certification Integrity

**Status:** IN PROGRESS — forged-certificate release paths are contained; hash-bound manifests and raw-row statistical recomputation are implemented; trusted artifact attestation and a real source-qualified evidence bundle remain outstanding.

## Objective

Prevent caller-supplied JSON fields, status labels, booleans, market lists or synthetic metrics from authorizing value-bet alerts. Certification must be derived from authentic, immutable model-evaluation artifacts and the prospective paper ledger, with exact model/calibration version binding and independently recomputed thresholds.

## Verified defect

The previous runtime predicate `app.value_bets._certificate_allows` accepted a mapping when `status` was `VALIDATED`/`PARTIALLY_VALIDATED`, `schema_version` was `1`, the requested market appeared in `approved_markets`, and `betting_validation` was `true`. Those fields can be fabricated by any caller; the predicate did not verify the underlying report bytes, ledger rows, hashes, model versions, timestamped odds, or CI calculation. Telegram also treated report-level status labels (`PASSED`, `CERTIFIED`, `APPROVED`) as release authority.

## Implemented containment and verification components

- `app.value_bets._certificate_allows` fails closed for every externally supplied certificate object.
- Certificate summary fields can no longer produce `VALIDATED` or `PARTIALLY_VALIDATED`; they remain diagnostics only.
- Telegram report formatting no longer treats report-supplied status labels as authority to release value candidates.
- Both core and runtime value-screen consumers keep release candidates disabled; paper-only research candidates remain explicitly separate.
- Added a SHA-256 evidence manifest verifier. It rejects altered bytes, unsafe paths, symlinks, duplicate/unknown roles, missing artifacts and malformed hashes.
- Added a raw-row recomputation engine for walk-forward metrics, point-in-time feature observations, approved source IDs, exact quote/settlement joins, model/calibration versions, duplicate fixture-market selections, net profit after explicit fees, date-clustered ROI confidence bounds, timestamped-odds coverage, and same-fixture 1X2 bookmaker comparisons.
- Added `scripts/verify_certification_evidence.py` and optional raw-audit attachment to `scripts/build_value_certificate.py`. A raw statistical pass still cannot authorize release.
- Added a dedicated GitHub Actions certification workflow. The focused certification/release-consumer suite passed on run 21; the full repository regression suite is still running.
- The daily prediction workflow was triggered by PR activity but its prediction job was skipped. No production schedule, database write, Telegram delivery or Vercel deployment was activated.

## Remaining Phase 1 acceptance work

1. Complete source-response byte capture and bind every feature, odds quote and settlement row to exact response hashes and source-observation identifiers.
2. Add GitHub/Sigstore artifact-attestation verification with a pinned trusted signer workflow; a self-declared manifest hash is not source attestation.
3. Prove the verifier rejects forged source identities, altered response bodies, missing response links, stale/post-kickoff quotes, mismatched fixture joins, model/calibration mismatch and cross-market evidence reuse.
4. Run the complete repository regression suite and verify all website, runtime and Telegram consumers use the same verified decision.
5. Produce a real evidence bundle from rights-approved, point-in-time source records. Existing aggregate backtest summaries and the current paper ledger do not satisfy the raw contract.
6. Only after those checks pass, implement the signed-attestation release token path. Keep runtime and Telegram locked until then.

## Mandatory thresholds

- At least 1,000 chronological walk-forward settled matches per market.
- At least 300 prospective settled selections per market.
- At least 90 distinct match dates per market.
- At least 98% timestamped pre-kickoff odds coverage per market.
- Net ROI greater than zero and date-clustered 95% lower ROI confidence bound greater than zero.
- 1X2 must beat the de-vigged bookmaker baseline on both Brier score and log loss in full and recent-holdout same-fixture comparisons.

No threshold is waived by this containment patch. Value betting remains locked until Phase 1 verification and the downstream certification gates pass.
