# VELTRIX 2.0 held-out calibration diagnostics

Date: 2026-11-11

## Scope

`veltrix_v2/evaluation/calibration.py` computes one-vs-rest reliability
diagnostics for the three 1X2 outcomes (AWAY, DRAW, HOME). It consumes
chronological walk-forward fold forecasts and their exactly matched settled
outcomes. It does not fit calibration parameters, change forecast probabilities,
repair missing probabilities, or select a probability threshold.

## Reported measurements

For each class, the report includes sample size, class-wise Brier score,
equal-width reliability bins, expected calibration error (ECE), and maximum
observed bin gap. Fold-level and aggregate reports also include test fixture
count, forecast count, abstentions and coverage. Empty folds are retained as
full-abstention diagnostics; no class score is fabricated for an empty fold.

## Leakage controls

- Forecast and outcome fixture IDs must match exactly within each fold.
- Duplicate fixture IDs within a fold or across folds are rejected.
- Fold numbers must be unique.
- Diagnostics are computed only from the supplied held-out forecasts and
  settled outcomes; training rows and in-sample fitted probabilities are not
  accepted by this interface.
- The module never optimizes bins, calibrates probabilities, or uses outcomes
  to modify forecasts.

## Interpretation and limits

ECE and maximum bin gap depend on bin count and sample size. Sparse bins can
produce unstable observed frequencies. Always publish bin counts and sample
coverage beside calibration gaps. Compare models on identical held-out fixture
sets. This report is descriptive and is not proof of calibration quality or
future accuracy. Binary BTTS and totals calibration and chronological
multi-market orchestration remain separate implementation work.

## Release boundary

This is an offline evaluation component only. It does not approve model
training on unqualified sources, production forecasts, value-bet publication,
Neon writes, deployment, or Telegram delivery.


## Release gate policy

The release gate is implemented separately in
`veltrix_v2/evaluation/calibration_gate.py`. For each market it requires at
least 1,000 held-out forecasts, expected calibration error (ECE) no greater
than 0.05, and maximum reliability-bin gap no greater than 0.15. The 1X2 gate
applies independently to AWAY, DRAW and HOME; BTTS and totals each have their
own binary report. Missing or non-finite metrics fail closed. The thresholds
are constants in the gate module and cannot be weakened by caller arguments.

These are operational release tolerances, not claims of guaranteed future
calibration. The full reliability bins, sample coverage and per-fold reports
remain part of the audit record.
