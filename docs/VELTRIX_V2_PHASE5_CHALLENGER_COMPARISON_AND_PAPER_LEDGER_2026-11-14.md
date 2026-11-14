# VELTRIX FOOTBALL 2.0 — Phase 5 challenger evaluation and paper ledger

## Evaluation design

- team_form_challenger.py evaluates a transparent form expected-score feature with expanding chronological cutoffs against the same-competition historical home expected-score baseline.
- elo_challenger.py evaluates Elo expected home score against the same baseline.
- model_challengers.py evaluates Poisson 1X2 probabilities, Elo expected score converted using the pre-cutoff draw rate, and a form expected-score mapping on one identical target set.
- Every candidate is scored on the intersection where all required inputs are point-in-time eligible and both teams have certified competition history.
- Duplicate fixture IDs are excluded as a group. Uncertified, invalid, future and history-deficient targets are counted separately.
- Competition reports are isolated; metrics are never pooled across competitions to conceal weak subgroups.

## Candidate probability interpretation

Poisson uses its own results-only score model. Elo's expected home score is decomposed into 1X2 using the pre-cutoff competition draw rate and the identity E(home score) = P(home win) + 0.5 * P(draw). Form uses the explicit, un-fitted mapping 0.5 + (home PPM - away PPM) / 6, bounded to [0,1], then the same draw-rate decomposition.

These Elo/form probability mappings are transparent research baselines, not fitted or calibrated models. Equal-weight blends are diagnostic only. No candidate or blend is promoted automatically.

## Metrics and reliability

- Multiclass 1X2 Brier score and log loss.
- One-vs-rest reliability bins for HOME, DRAW and AWAY at 0.10 probability widths.
- Per-competition sample counts and the same metrics.
- All candidates and blends use identical fixture IDs within each report.

This work does not claim market-level certification. It does not replace the required 1,000+ chronological match tests, 300 prospective settlements, 90 distinct dates, odds coverage, positive date-clustered ROI confidence interval, or bookmaker benchmark.

## Prospective paper ledger

veltrix_v2/ledger/paper_predictions.py provides an append-only event builder with SHA-256 hash chaining. It accepts only point-in-time-certifiable predictions recorded before kickoff, validates normalized 1X2 probabilities, rejects duplicate model/fixture entries, and appends settlements as separate events after results become available.

The implementation is storage-agnostic and in-memory by design. A later persistence adapter must use append-only database constraints and verify the hash chain on read. It must not backfill historical forecasts or mutate prior prediction events.

## Release boundaries

No production database writes, migrations, real provider calls, paid services, Vercel deployment, live publication, Telegram activation, schedule activation, or value-bet unlock are included.
