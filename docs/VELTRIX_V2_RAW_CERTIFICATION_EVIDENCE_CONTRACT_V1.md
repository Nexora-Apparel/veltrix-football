# Raw certification evidence contract — implementation v1

This contract is intentionally stricter than the existing aggregate report/ledger. The verifier consumes exact byte-hashed files listed in the evidence manifest, then recomputes metrics from row-level records. It never treats summary fields as evidence and never authorizes release.

## Artifact row schemas

- `walk_forward_rows`: `rows[]` with `fixture_id`, `market`, `kickoff`, `prediction_at`, `feature_max_observed_at`, `model_version`, `split` (`full` or `recent_holdout`), `outcome`, and probability maps. For 1X2, both `model_probabilities` and de-vigged `bookmaker_probabilities` must contain home/draw/away. Other markets use yes/no or over/under.
- `prospective_ledger`: `rows[]` with unique fixture/market, selection, kickoff, quote timestamps, odds snapshot ID, settlement ID, model version, outcome, won, stake, decimal odds, fees and recorded net profit.
- `odds_snapshots`: `rows[]` with unique snapshot ID, fixture, market, observed timestamp and quote-updated timestamp.
- `settlement_records`: `rows[]` with unique settlement ID, fixture ID, source ID, settlement timestamp, outcome and model version.
- `model_manifest`: object with immutable `model_version`.
- `coverage_audit`: retained and hash-bound as source/coverage evidence; summary values are not trusted by the raw metric calculator.

All timestamps must be timezone-aware. Prediction time and latest feature-observation time must precede kickoff. Quotes must be ordered quote-update ≤ snapshot-observed ≤ kickoff and no older than 24 hours. Settlement joins must match exact fixture and version references.

## Recomputed metrics

The verifier derives unique walk-forward fixture counts, same-fixture full/recent 1X2 Brier and log-loss comparisons, prospective selection count, distinct kickoff dates, timestamped-odds join coverage, net ROI after fees, and a deterministic 4,000-draw date-clustered percentile lower bound.

A statistical pass is only diagnostic. It is not proof of provider rights, source authenticity, cryptographic signing, deployment equivalence, or operational safety. Runtime release remains fail-closed.
