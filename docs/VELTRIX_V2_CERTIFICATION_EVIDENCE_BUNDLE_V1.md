# VELTRIX FOOTBALL 2.0 — Certification Evidence Bundle v1

**Status:** Specification established; raw-row verifier and CI acceptance remain incomplete. This document does not authorize value betting.

## Trust boundary

A certificate must never trust JSON summary fields for sample counts, distinct dates, ROI, confidence intervals, odds coverage, model versions, or benchmark metrics. Those values must be recomputed from the underlying records. A SHA-256 match proves byte identity only; it does not prove that the source data are lawful, complete, point-in-time valid, or statistically sufficient.

## Manifest contract

A UTF-8 JSON manifest is stored beside its evidence files:

- `schema_version`: integer `1`
- `purpose`: exact string `VELTRIX_VALUE_CERTIFICATION`
- `artifacts`: array of unique entries
  - `role`: one of the required evidence roles below
  - `path`: safe relative POSIX path, resolved beneath the manifest directory
  - `sha256`: lowercase 64-character SHA-256 digest of the exact file bytes

Required roles (exactly one artifact per role):

1. `walk_forward_rows` — fixture-level, chronological out-of-sample predictions, outcomes, market probabilities, model/calibration versions, fold and cutoff timestamps.
2. `coverage_audit` — source and row coverage audit, including excluded/rejected rows and dataset fingerprint.
3. `prospective_ledger` — append-only prospective selection, quote reference, stake, settlement and payout records.
4. `odds_snapshots` — raw bookmaker quote snapshots with provider, bookmaker, market, selection, decimal price, observed timestamp and fixture kickoff.
5. `settlement_records` — source-attested final scores/results with source identifiers, observation timestamps and correction/version lineage.
6. `source_responses` — raw provider response bodies encoded as base64, with source IDs, fetch timestamps, request fingerprints and recomputed response SHA-256 hashes. Feature, quote and settlement rows point to the exact retained response and JSON record pointer.\n7. `model_manifest` — immutable model code commit, model family/version, feature schema, calibration version and training-data cutoff.

Artifact paths must be unique, relative, traversal-free, non-symlink files. Missing roles, duplicate roles, malformed hashes, path escape, unreadable files and hash mismatches invalidate the bundle.

## Raw-row acceptance rules

The certification engine must reject the bundle unless all of the following can be derived from raw rows:

- Walk-forward samples are settled, out-of-sample, strictly chronological, and at least 1,000 unique fixtures per market.
- Prospective selections are timestamped before kickoff, settled by an approved source, unique by fixture/market/selection policy, and at least 300 per market across at least 90 distinct match dates.
- Timestamped odds coverage is calculated over every eligible prospective selection; quote observation must precede kickoff and satisfy the configured maximum quote age. Coverage must be at least 98%.
- Net ROI is recomputed from stake, payout, commission and any recorded fees. Its date-clustered 95% lower confidence bound must be recomputed from date-level clusters, not accepted from the ledger.
- Feature observation timestamps must not exceed the prediction cutoff. Settlement data and post-match fields must never appear as pre-match features.
- Fixture identity, model version, calibration version, odds quote, selection and settlement references must join exactly. Unmatched or multiply matched records fail closed.
- Full and recent-holdout 1X2 model and de-vigged bookmaker Brier/log-loss metrics must be recomputed over identical fixture IDs and identical evaluation cutoffs.

## Runtime contract

The current `app.value_bets._certificate_allows` remains fail-closed. A future release path must accept only a verifier-produced result bound to the manifest digest and artifact digests; a caller-supplied status, boolean, market list, or certificate JSON is never authority. Telegram must consume the same verified release decision, not parse report-level labels.

## Current limitation

The repository's current backtest workflow is explicitly disabled and its existing backtest report is aggregate/diagnostic output. The current paper-ledger path also does not provide a demonstrated, complete set of raw quote, selection and settlement rows for this contract. Therefore Phase 1 cannot be marked complete and no release certificate can be issued yet.
