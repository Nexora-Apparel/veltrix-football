# VELTRIX 2.0 shared-scoreline multi-market walk-forward

Date: 2026-11-11

## Evaluation contract

The `run_multi_market_walk_forward` evaluator builds chronological expanding folds, fits the independent Poisson team-strength estimator on each fold's eligible training rows, and creates one Dixon-Coles joint scoreline distribution for each forecastable test fixture. The same distribution supplies 1X2 home/draw/away probabilities, BTTS yes/no probabilities, and Over/under probabilities for one explicitly selected half-goal line.

The evaluator does not independently fit three market models. This prevents market forecasts from silently using inconsistent goal assumptions.

## Coverage and scoring

Every fold retains its complete test-fixture ID universe. If a fixture cannot be forecast (for example, an unseen team), it is abstained from all three markets. Binary market scoring receives the full eligible test IDs, so BTTS and totals coverage denominators include those abstentions. Each market reports its own score sample and report. A fold with zero forecastable fixtures keeps its abstention IDs and has no fabricated score report.

Integer totals lines are rejected until explicit push-aware binary settlement and scoring contracts are implemented. Quarter-goal Asian lines remain unsupported pending split-stake settlement.

## Leakage and limitations

Training labels are restricted by each fold's `training_label_cutoff_utc`. Test outcomes are used only after each test fixture's forecast is formed. Chronological folds are disjoint; aggregate scorers reject duplicate fixture identities. This module does not perform calibration, compare bookmakers, calculate ROI, or certify value betting.

The current 1X2 score report contains Brier, log loss and RPS. Binary reports contain Brier, log loss, hit rate and Wilson interval. Calibration diagnostics are a separate held-out-only step. Benchmark comparison must use the identical settled fixture set for each market.

## Release boundary

This remains an offline evaluation primitive. It does not authorize real-data training from unqualified sources, production forecasts, value-bet publication, Neon writes, deployment, or Telegram delivery.
