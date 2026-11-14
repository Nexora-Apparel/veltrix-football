# VELTRIX FOOTBALL 2.0 — chronological Elo challenger evaluation

## Purpose

Measure whether competition-specific Elo expected-home-score features improve on a simple pre-cutoff competition home-score baseline.

## Evaluation contract

- Expanding chronological evaluation; no random splits.
- Target must be explicitly point-in-time-certifiable.
- Training rows must be certified, same competition, unique fixture IDs, and have kickoff, availability and recording times before target cutoff.
- The target result must be available and recorded by evaluation_as_of.
- Duplicate fixture IDs are excluded as a group.
- Missing team history is skipped, never imputed.
- The Elo state is reconstructed from training rows at each target cutoff.

## Metric and interpretation

The metric is mean squared error for expected home score (home win=1, draw=.5, away win=0). The baseline is the historical same-competition home-score mean available at the target cutoff.

This is not a 1X2 Brier score, not a probability calibration test, and not certification for publication or betting. Positive improvement is a research signal only. Full model selection must still use the existing chronological 1X2, BTTS and totals evaluation with sufficient prospective samples and uncertainty bounds.

## Boundaries

No paid provider, network access, database write, migration, publication, website, Telegram, or schedule activation.
