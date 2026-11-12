# Raw certification evidence contract — implementation v1

This contract is intentionally stricter than the existing aggregate report/ledger. The verifier consumes exact byte-hashed files listed in the evidence manifest, then recomputes metrics from row-level records. It never treats summary fields as evidence and never authorizes release.

## Artifact row schemas

- `walk_forward_rows`: `rows[]` with `fixture_id`, `settlement_id`, `market`, `kickoff`, `prediction_at`, `model_commit`, `feature_schema_version`, `features[]` (each with a unique name, value, timezone-aware `observed_at`, rights-approved `source_id`, source response ID and source pointer), `model_version`, `split` (`full` or `recent_holdout`), `outcome`, and probability maps. For every market, `model_probabilities` must contain the complete outcome set. For 1X2, raw `bookmaker_odds` must contain decimal home/draw/away prices; the verifier derives proportional de-vigged probabilities itself. Other markets use yes/no or over/under.
- `prospective_ledger`: `rows[]` with unique fixture/market, selection, kickoff, quote timestamps, odds snapshot ID, settlement ID, model version, outcome, won, stake, decimal odds, fees and recorded net profit.
- `odds_snapshots`: `rows[]` with unique snapshot ID, fixture, market, bookmaker, rights-approved source ID, source response ID and source pointer, kickoff, observed timestamp, quote-updated timestamp and exact decimal odds.
- `settlement_records`: `rows[]` with unique settlement ID, fixture ID, rights-approved source ID, source response ID and source pointer, settlement timestamp, final status (`FT`, `AET` or `PEN`), final `home_goals`/`away_goals` and immutable settlement version. Settlement identity is independent of model version. Market outcomes are derived from these final scores; caller-supplied win/loss flags are never authoritative.
- `model_manifest`: object with immutable `model_version`, full Git `code_commit`, timezone-aware `training_data_cutoff`, `feature_schema_version` and the allowed `calibration_versions` list.
- `source_responses`: `rows[]` must retain exact base64 response bytes, and the verifier recomputes every body SHA-256.\n- `coverage_audit`: must explicitly declare `rights_status: APPROVED_FOR_INTENDED_USE`, `commercial_use_eligible: true`, and the exact `approved_source_ids` used by feature, quote and settlement rows. Summary metric values are not trusted by the raw metric calculator.

All timestamps must be timezone-aware. Training-data cutoff and every feature observation must precede prediction time; prediction time must precede kickoff. Model code commit and feature schema must match the pinned model manifest. Quotes must be ordered quote-update ≤ snapshot-observed ≤ kickoff and no older than 24 hours. Both walk-forward and prospective rows must join to the exact fixture settlement ID; the verifier derives 1X2, BTTS and totals outcomes directly from the source final score. Settlement joins must match exact fixture and version references. Every feature, odds and settlement source ID must be included in the approved source list. Each row must point to a retained response from the same source; feature response fetches must precede prediction time, odds response fetch time must equal quote observation time, and settlement response fetch time must not predate settlement.

## Recomputed metrics

The verifier derives unique walk-forward fixture counts, same-fixture full/recent 1X2 Brier and log-loss comparisons, prospective selection count, distinct kickoff dates, timestamped-odds join coverage, net ROI after fees, and a deterministic 4,000-draw date-clustered percentile lower bound.

A statistical pass is only diagnostic. It is not proof of provider rights, source authenticity, cryptographic signing, deployment equivalence, or operational safety. Runtime release remains fail-closed.


## Execution

Run `python scripts/verify_certification_evidence.py --manifest PATH` to recompute raw evidence diagnostics. Once the real bundle is committed to `reports/certification/evidence-manifest.json` on `main`, dispatch `.github/workflows/certification-evidence-attestation.yml`; it attests the exact manifest only after all raw statistical gates pass. Verify with `python scripts/verify_certification_evidence.py --manifest PATH --require-attestation`. `scripts/build_value_certificate.py --evidence-manifest PATH` requires the pinned GitHub/Sigstore attestation and attaches the diagnostic audit while keeping all release markets locked.\n