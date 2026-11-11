# VELTRIX 2.0 held-out binary-market calibration

Date: 2026-11-11

## Scope

`veltrix_v2/evaluation/binary_calibration.py` reports reliability diagnostics for BTTS and non-push totals forecasts. It accepts chronological held-out folds, forecast probabilities and exactly matched settled YES/NO outcomes. It never fits or applies a calibration mapping.

## Measurements

The report includes sample size, Brier score, equal-width reliability bins, expected calibration error, maximum bin gap, fold count, test fixture count, forecast count, abstentions and coverage. Empty folds are preserved as full-abstention rows and do not receive fabricated scores.

## Leakage and identity controls

- Forecast and outcome fixture IDs must match exactly within each fold.
- Duplicate fixture IDs across folds are rejected.
- One report cannot mix BTTS and totals markets.
- Probabilities are taken as supplied; the evaluator does not adjust them using outcomes.
- The calibration set must consist only of forecasts generated before their respective kickoffs and outcomes settled afterward.

## Interpretation

ECE and maximum bin gap depend on bin count and sample size. Publish bin counts and coverage with the metric. Compare models and market baselines on identical held-out fixtures. This diagnostic is not a proof of future calibration and does not certify an edge.

## Release boundary

Offline evaluation only. No production forecasts, value-bet publication, database writes, deployment or Telegram delivery are authorized by this module.
