# VELTRIX FOOTBALL 2.0 — Walk-forward evaluator v1

## Evaluation design

The evaluator uses an expanding chronological window. Each target fixture receives a forecast cutoff at kickoff minus a configurable non-negative buffer (one second by default). The model independently admits only same-competition observations explicitly marked point_in_time_certifiable=true whose match kickoff (or conservative date-only boundary), result-availability timestamp and ingestion/recorded timestamp are all at or before that cutoff. Non-certifiable inputs are counted and excluded from both model and baseline training folds.

A target outcome is scored only when the target kickoff, result-availability timestamp and recorded timestamp are all no later than the explicit timezone-aware `evaluation_as_of`. Duplicate fixture IDs are excluded in full, rather than selecting whichever conflicting row happens to appear first.

## Metrics

- 1X2: multiclass Brier score and log loss.
- BTTS Yes: binary Brier score and log loss.
- Over 2.5: binary Brier score and log loss.
- Each market compares the model with an independent same-competition home/away scoring-rate Poisson baseline built from the exact same pre-kickoff training set.
- Positive improvement means the model score is lower (better) than baseline.

## Auditability

The report includes every scored fixture, its kickoff and cutoff, actual score/outcome, model probabilities, baseline probabilities, total input count and explicit skip counts for missing history, invalid targets, duplicate IDs and outcomes not yet known by evaluation_as_of.

## Limitations and release boundary

This is an initial evaluator, not certification. It does not yet compute confidence intervals, calibration curves, date-clustered uncertainty, season/competition stratification, prospective paper-trading results or bookmaker comparisons. The model's publication flag remains hard-locked false. No results with unknown historical availability are backdated or imputed. The Phase 3 imported historical dataset currently has no point-in-time certification and therefore cannot be treated as eligible merely because a final score exists.
