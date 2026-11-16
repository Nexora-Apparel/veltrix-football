# VELTRIX FOOTBALL 2.0 — Integration acceptance record
**Date:** 2026-11-15  
**Repository:** Nexora-Apparel/veltrix-football  
**PR:** #120  
**Integration branch:** integration/v2-report-bundle-wiring-20261114

## Acceptance decision

**Software integration acceptance: PASS at commit dd502a37db9ca9fa65a3ef16059dbfe402d39685.**  
**Prospective data acceptance: PARTIAL / OPEN.**  
**Model validation and certification: NOT COMPLETE.**  
**Production publication, Telegram delivery and schedule: NO-GO.**

This record deliberately separates code integration from evidence accumulation and production authorization. A successful workflow is not treated as model certification or a successful new prediction admission.

## Exact-head CI evidence

GitHub PR #120 head was dd502a37db9ca9fa65a3ef16059dbfe402d39685, base main at 0ac4fe22d72b899bf873c470408bd7dbf44ce800. GitHub reported mergeable=true, draft=true, state=open.

All 11 expected check runs on that exact head completed:
- PostgreSQL 16 integration — success
- PostgreSQL 18 integration — success
- Foundation — success
- Reservation PostgreSQL 16 — success
- Reservation PostgreSQL 18 — success
- Shadow regression — success
- Audit tests — success
- PostgreSQL 16 acceptance — success
- PostgreSQL 18 acceptance — success
- Certification evidence — success
- Daily predictions — skipped intentionally; legacy/public scheduled prediction execution remains disabled

No failed or pending check remained at the final exact-head inspection.

## Manual 5Dollar capture acceptance

Run: 43703148921  
Job: 132778447654  
Workflow: VELTRIX Phase 5 — Manual 5Dollar Shadow Capture  
Result: success.

The execution completed 14 bounded provider requests and captured 660 first-observed rows. It mapped 25 upcoming targets and admitted 25 shadow candidates. Crucially:
- persisted shadow ledger events: 0
- duplicate predictions skipped: 25
- ledger chain verification: true
- independent post-commit verification: true
- publication status: LOCKED_PROSPECTIVE_OBSERVED_SHADOW_ONLY

**Interpretation:** this is a successful idempotency and post-commit verification acceptance run. It is not a new-cohort admission test. The 25 targets were already present in the append-only ledger; the correct behavior was to skip them. Do not delete or rewrite the old events, weaken the uniqueness key, or fabricate replacement forecasts to force a non-zero count.

A fresh-cohort acceptance requires genuinely new eligible future fixtures with exact provider identity, rights approval, pre-kickoff capture evidence and no existing ledger key. The current run does not prove such a cohort exists.

## Model implementation status

The new V2 model foundations have been started and are present under `veltrix_v2/models` and `veltrix_v2/evaluation`:
- Results-only Poisson baseline v1: implemented; produces 1X2, BTTS and Over 2.5 from point-in-time eligible results. Publication is hard-locked false.
- Elo ratings v1: implemented as a point-in-time rating feature; it is not by itself a calibrated probability model.
- Team-form/schedule features v1: implemented using certified point-in-time results.
- Batch forecast engine: implemented, capped at 25, kickoff ordered, excludes duplicate/invalid/past targets and targets without both teams' eligible history.
- Chronological walk-forward evaluator: implemented with same-training-set baseline comparisons and per-market Brier/log-loss metrics.
- Poisson/Elo/form challenger comparisons and reliability reporting: implemented as diagnostic comparisons, not automatic model promotion.
- Publication certification verifier and prospective settlement scorecard: implemented as fail-closed gates.

These are software implementations and unit/integration-tested foundations. They are **not trained, independently validated, or certified production models**. The current historical import set remains 0/2,496 point-in-time-certifiable, so it cannot support legitimate historical training/backtesting under the V2 temporal contract. No model should be described as complete.

Still outstanding for model development:
1. Acquire legally usable, item-level timestamped historical observations with source publication/availability, recorded-at, payload hashes and rights evidence.
2. Build and run chronological training/evaluation datasets per competition without legacy code or future leakage.
3. Compare Poisson, Dixon-Coles, Elo/form challengers and any approved extensions on identical chronological folds.
4. Add uncertainty intervals, date/competition stratification, calibration diagnostics and robust recent holdouts.
5. Add verified odds snapshots and bookmaker benchmark evidence where rights permit.
6. Complete prospective settled selections and required date coverage before any certification decision.

## Hard blockers that remain external to CI

1. The 25 currently captured target identities are duplicates; fresh unique eligible fixtures must be observed before new shadow entries can be accepted.
2. Results cannot be settled before actual kickoff and verified FINISHED status. The current 25 target cohort is scheduled for 18–21 November 2026.
3. Historical 2,496 rows remain non-PIT-certifiable; no fabricated timestamps or retrospective publication times are allowed.
4. 5Dollar benchmarking rights approval must be present and time-valid before benchmark settlement use.
5. Odds API bookmaker/region market rights and no-credit quota headroom must be verified before any one-event odds probe.
6. Certification thresholds remain unmet: at least 1,000 chronological walk-forward matches per market; 300 prospective settled selections; 90 distinct dates; 98% timestamped pre-kickoff odds coverage; positive net ROI with date-clustered 95% lower bound above zero; and 1X2 improvement over the de-vigged bookmaker on both Brier and log loss.
7. Production trusted attestation, source-rights verification, runtime wiring, staging migrations/operator controls, website/scheduled/Telegram parity and delivery acceptance remain separate release gates.

## Safety boundary

PR #120 remains draft and unmerged. Legacy prediction/publication/sender/scheduler workflows remain disabled. No production deployment, production database write, Telegram send, schedule activation, synthetic data, synthetic settlement or certification bypass is authorized by this acceptance record. Value betting remains locked.

## Next execution sequence

1. Keep the accepted code checkpoint intact.
2. Identify a genuinely new, rights-approved prospective fixture cohort; do not re-admit existing ledger keys.
3. Run bounded capture and require non-zero new events only when eligible unique targets actually exist; verify the committed ledger from a fresh connection.
4. After target kickoffs, run bounded settlement and verify exact result identity, rights, raw response/manifest hashes and post-commit event hashes.
5. Continue model data qualification and prospective accrual. Do not activate publication until each independent certification and delivery gate passes.


## Follow-up exact-head CI and remaining model work (2026-11-15)

The acceptance record above was first written against the earlier integration checkpoint. The branch has since advanced to `3bff26061f9e28c35b6e55769f283c46d2a2ed6a`. Exact-head check-runs for that commit were re-queried after completion:

- Foundation — success
- PostgreSQL 16 integration — success
- PostgreSQL 18 integration — success
- Certification evidence — success
- Audit tests — success
- Reservation PostgreSQL 16 — success
- Reservation PostgreSQL 18 — success
- PostgreSQL 16 acceptance — success
- PostgreSQL 18 acceptance — success
- Shadow regression — success
- Daily predictions — skipped intentionally (legacy scheduled publication remains disabled)

No failed or pending check remained on this exact head. This establishes CI completion for the integration branch; it does not establish data, model, market, or production certification.

### Two remaining model qualification workstreams

1. **Dixon-Coles challenger qualification.** The score-grid implementation currently accepts a configurable `dixon_coles_rho` and applies low-score tau adjustments, but the candidate is not yet independently estimated, tuned inside training folds, and reported as a distinct challenger against the independent Poisson baseline on identical per-competition chronological folds. A fixed caller-supplied rho is not a trained/qualified Dixon-Coles model. Next: estimate rho using training-only observations inside each fold, constrain tau positivity, freeze the fitted parameter at each prediction cutoff, report per-competition and aggregate Brier/log-loss plus date-clustered paired confidence intervals, and reject promotion unless the independent holdout supports it.

2. **Probability calibration/reliability qualification.** Current reliability code supplies calibration bins and date-clustered paired loss intervals; it is diagnostic, not a fitted calibration layer. Next: implement leakage-safe calibration candidates (multiclass temperature/vector scaling for 1X2 and separate binary calibration for BTTS/O2.5), fit only on an earlier chronological calibration window, evaluate on a later untouched window, compare raw versus calibrated probabilities, preserve probability simplex/monotonicity, and report calibration error, Brier, log loss, confidence intervals, sample counts and date/competition strata. Do not calibrate from the evaluation fold or from non-PIT records.

Both workstreams remain **NOT QUALIFIED**. They cannot be honestly completed using the current historical import: 0/2,496 observations are point-in-time certifiable. No synthetic training data or retrospective publication timestamps are permitted.

### Cohort and certification state

The latest successful 5Dollar capture still recorded 25 duplicate target identities and zero new ledger admissions. A genuinely new cohort must be proven from provider response evidence and checked against the complete ledger before another bounded capture; rerunning the same 25 identities is not a new cohort. The 25 already-observed fixtures must be settled only after kickoff and independently verified final results. Market certification remains blocked until the previously stated thresholds are met independently for each market, including 1,000 chronological walk-forward matches, 300 prospective settled selections, 90 distinct dates, 98% timestamped odds coverage, positive net ROI with positive date-clustered 95% lower bound, and 1X2 improvement over the de-vigged bookmaker on both Brier and log loss.

**Updated decision:** integration CI PASS; fresh-cohort admission OPEN; prospective settlement OPEN; Dixon-Coles qualification OPEN; probability calibration qualification OPEN; independent market certification NOT ACHIEVED; production release NO-GO.
