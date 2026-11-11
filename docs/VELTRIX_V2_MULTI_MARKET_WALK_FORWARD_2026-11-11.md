# VELTRIX 2.0 shared-scoreline multi-market walk-forward

Date: 2026-11-11

## Evaluation contract

The `run_multi_market_walk_forward` evaluator builds chronological expanding folds, fits the independent Poisson team-strength estimator on each fold's eligible training rows, and creates one Dixon-Coles joint scoreline distribution for each forecastable test fixture. The same distribution supplies 1X2 home/draw/away probabilities, BTTS yes/no probabilities, and Over/under probabilities for one explicitly selected half-goal line.

The evaluator does not independently fit three market models. This prevents market forecasts from silently using inconsistent goal assumptions.

## Coverage and scoring

Every fold retains its complete test-fixture ID universe. If a fixture cannot be forecast (for example, an unseen team), it is abstained from all three markets. Each market has an explicit coverage record (eligible, forecasted, abstained, coverage ratio), including folds with zero forecasts. Binary score reports are omitted for all-abstention folds rather than fabricating metrics.

Integer totals lines are rejected until explicit push-aware binary settlement and scoring contracts are implemented. The cross-competition aggregate rejects duplicate fixture IDs across scopes and retains per-scope reports so aggregate scores cannot hide a weak or sparse competition. Quarter-goal Asian lines remain unsupported pending split-stake settlement.

## Leakage and limitations

Training labels are restricted by each fold's `training_label_cutoff_utc`. Test outcomes are used only after each test fixture's forecast is formed. Chronological folds are disjoint; aggregate scorers reject duplicate fixture identities. This runner does not perform calibration, fetch odds, calculate ROI, or certify value betting. Separate components provide calibration diagnostics, binary bookmaker comparison, 1X2 benchmark comparison and ROI summaries.

The current 1X2 score report contains Brier, log loss and RPS. Binary reports contain Brier, log loss, hit rate and Wilson interval. Held-out calibration diagnostics now exist separately for 1X2 and binary markets; they report reliability bins, Brier, ECE and maximum calibration gap without fitting a calibrator. Binary bookmaker comparisons use normalized complete bookmaker markets and the exact common settled fixture intersection, with model and bookmaker coverage reported separately. The 1X2 benchmark comparator also requires identical fixture sets. Benchmark comparisons must never use odds as model-strength features.

## Release boundary

This remains an offline evaluation primitive. It does not authorize real-data training from unqualified sources, production forecasts, value-bet publication, Neon writes, deployment, or Telegram delivery.
