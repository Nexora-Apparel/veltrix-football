# VELTRIX Football 2.0 — Independent Model Portfolio

**Status:** Architecture and initial Elo feature component in development. No model is certified or publishable.

## Design objective

Improve probability quality through independent model families, strict point-in-time data, chronological evaluation and market-specific calibration. Do not maximize raw hit rate at the expense of probability calibration or price value. Evaluate log loss, Brier score, calibration error, discrimination and ROI only where timestamped odds support it.

## Candidate model portfolio

### 1. Results-history logistic baseline — implemented, diagnostic only
- Separate 1X2 multinomial, BTTS binary and Over 2.5 binary heads.
- Regularized deterministic fitting.
- Results-derived rolling attack/defence, form, rest, competition baselines and Elo-difference features.
- Purpose: transparent baseline and benchmark, not assumed champion.

### 2. Chronological Elo strength model — feature engine implemented
- Competition-scoped rating histories.
- Settled-match chronology, home advantage and goal-margin update.
- No cross-league transfer or default strength borrowing.
- Produces rating difference and history counts as model features, not market probabilities.
- Must be tested against static and alternative K-factor variants in walk-forward evaluation.

### 3. Goal-count model family — fitted shadow implementation added
- `app/poisson_dixon_coles_model.py` fits separate competition-scoped home/away scoring intercepts and team attack/defence effects from settled training rows.
- L2 regularization and within-competition identifiability constraints; optional exponential time-decay weights.
- Dixon-Coles rho is estimated by deterministic profile-likelihood grid search on training rows only.
- Uses `app/poisson_dc_head.py` to derive 1X2, BTTS and half-goal totals from the corrected scoreline matrix; material Poisson tail mass fails closed.
- Artifacts bind dataset digest, train/validation/test fixture manifests, training cutoff, training timestamp, source digest and configuration.
- Inference verifies artifact integrity and point-in-time ordering. Unknown competitions/teams abstain.
- Research-only; no publication or value betting. Unit/CI tests do not constitute real-data training or accuracy certification.

### 4. Nonlinear tabular challenger — next
- Gradient-boosted trees (candidate: LightGBM or CatBoost) for 1X2, BTTS and totals.
- Dependency and deterministic training environment must be pinned before adoption.
- Competition-aware validation and leakage-safe feature availability required.
- Compare against logistic and goal-count models; reject if gains do not persist across time origins.

### 5. Market-specific ensemble — later
- Combine only independently evaluated out-of-fold predictions.
- Learn ensemble weights on chronological validation data only.
- No in-sample stacking, test-set tuning or fixed hand-picked weights.
- Allow a market to select a different champion; do not force one universal model.

### 6. Calibration layer — implemented, diagnostic only
- Temperature scaling for 1X2.
- Platt scaling for BTTS and Over 2.5.
- Fit on validation partitions only; calibration time must precede test prediction cutoffs.
- Compare reliability diagrams, Brier and log loss before and after calibration.

### 7. Drift and uncertainty layer — planned
- Detect competition/team data sparsity, feature drift and calibration drift.
- Estimate uncertainty and abstain when evidence is insufficient.
- No generic priors, default-home probabilities or favourite-only publication.

## Shared data and evaluation requirements

- Exact fixture identity and provenance-bound raw payloads.
- Point-in-time features strictly before kickoff.
- Labels available only after their independently evidenced availability time.
- Chronological train/validation/test splits with embargo.
- Multi-origin walk-forward testing, per-competition and per-market reporting.
- Baselines: empirical training frequency, market-implied probabilities where timestamped odds exist, and simple goal-rate models.
- Report sample counts, date coverage, Brier, log loss, calibration and confidence intervals.
- Compare every candidate on identical fixture sets and cutoffs.
- No model promotion based on synthetic fixtures or one random split.

## Current blockers

1. No historical training dataset has been assembled.
2. Current 5Dollar and StrikerAPI documented schemas lack an exact wall-clock settlement timestamp.
3. The prospective availability ledger/collector are not yet connected to persistent storage or scheduled polling.
4. StrikerAPI 17-competition qualification remains blocked by HTTP 402.
5. No actual model training, real-data calibration, or real-data walk-forward comparison has occurred.

## Promotion policy

A model remains a challenger until it beats the current champion on repeated chronological out-of-sample origins, by market and competition, with sufficient samples and statistically defensible improvement. Value betting remains separately locked to its certification thresholds. Predictions, Telegram and schedules remain paused until all release gates pass.

## Release certification evaluator

`app/market_release_certification.py` provides a pure, fail-closed evaluator for the release thresholds. It consumes a complete evidence bundle for each of 1X2, BTTS and Over 2.5 and reports each gate independently:
- At least 1,000 chronological walk-forward fixtures per market.
- At least 90 distinct WAT dates in both walk-forward and prospective samples.
- At least 300 prospective settled selections per market.
- At least 98% of walk-forward fixtures with timestamped bookmaker decimal odds captured no later than kickoff.
- Positive net prospective ROI and a positive lower 95% confidence bound using a 5,000-replicate WAT-date cluster bootstrap.
- 1X2 Brier score and log loss must both beat the de-vigged bookmaker probabilities on the same odds-covered fixture set.

Every walk-forward label and prospective settlement/odds record must carry a SHA-256 evidence reference. The evaluator also requires the caller to supply an explicit set of source digests produced by successful signature-verified archive restores and approved crosswalk verification. Every walk-forward label, bookmaker odds payload, fixture crosswalk, prospective settlement and prospective odds digest must be present in that verified set; missing or unverified evidence fails certification. The evaluator validates digest shape and membership but does not itself download or decrypt archives. It does not verify archive receipts itself.

A successful evaluator result can mark the numeric value-betting evidence thresholds as met, but it always leaves `value_betting_authorized=false` and `publication_authorized=false`. Source digests must be resolved against verified archive receipts and approved crosswalk records, followed by human release approval, model promotion, operational readiness and the separate public prediction gates. No evaluator output alone can unlock value betting. It performs no provider requests, database writes, publication, Telegram delivery or schedule activation.

Synthetic unit tests exercise threshold boundaries and integrity failures only. They are not model performance evidence and cannot certify VELTRIX.

### Timestamped bookmaker odds evidence

`app/bookmaker_odds_evidence.py` adds a network-free, append-only observation ledger for 1X2, BTTS and Over 2.5 decimal prices. It validates complete selection sets, timezone-aware capture times, capture-before-kickoff ordering, source payload digests, overround and de-vigged implied probabilities. It supports idempotent append, rejects conflicting quotes for the same fixture/market/bookmaker at an identical timestamp, and selects the latest captured snapshot before kickoff for an exact fixture/market/bookmaker key.

The module intentionally does not poll an odds provider or claim fixture identity reconciliation. Provider adapters must preserve the raw response in the encrypted evidence archive, independently verify the referenced payload digest, map the provider event to a canonical fixture using a reviewed crosswalk, and then append the observation. A missing or ambiguous fixture mapping must be quarantined, not guessed.

### The Odds API evidence adapter

`app/the_odds_api_evidence_adapter.py` converts a single already-retrieved The Odds API event response into the odds evidence ledger. It supports h2h (1X2), BTTS and totals at exactly 2.5. It requires an explicit reviewed crosswalk with exact provider event ID, canonical fixture ID, kickoff and teams; ID, team or kickoff mismatch is rejected. It never guesses fixture identity. Quotes after retrieval, after kickoff or older than the configured freshness window are quarantined. The canonical event-object digest and a separately supplied SHA-256 of the exact archived HTTP response bytes, plus the crosswalk evidence digest, are bound into each observation. The offline CLI requires the exact-response digest as an explicit argument; it must be computed from the original response bytes and verified against the encrypted archive, not guessed from re-serialized JSON.

This is a pure adapter and does not call The Odds API. It is not yet connected to a scheduled acquisition worker or durable evidence archive. Provider credentials and endpoint access do not by themselves establish historical odds availability; actual timestamped quote coverage still has to be measured.

### Offline odds evidence ingestion

`scripts/ingest_the_odds_api_evidence.py` is a manual, network-free CLI that accepts one archived event JSON file plus its reviewed crosswalk and the SHA-256 of the exact archived HTTP response bytes, converts the response through the strict adapter, and atomically appends observations to a local ledger. It refuses symlink destinations, preserves the previous ledger if validation fails, and is idempotent on repeated ingestion. It never reads API credentials, calls a provider, writes Neon, publishes predictions or sends Telegram. This is a local evidence-preparation tool, not a scheduled production collector.

### Walk-forward to certification evidence bridge

`app/multi_origin_walk_forward.py` now emits its pooled out-of-sample records with fixture kickoff, label-availability timestamp, label-source digest and feature-snapshot digest. These are the point-in-time records required by the release certification layer; aggregate metrics alone are not enough to reconstruct a trustworthy certification sample.

`app/walk_forward_certification_adapter.py` verifies the pooled-record digest, joins each fixture/market to the latest pre-kickoff quote from one explicitly named benchmark bookmaker in the The Odds API evidence ledger, and preserves missing quotes as missing. It does not substitute another bookmaker or select the most favorable quote for benchmark scoring. Prospective selections are passed as a separate market-partitioned evidence set and must still be independently provenance-verified. This bridge performs no provider requests or persistence.

### Prospective paper value-selection ledger

`app/prospective_value_selection_ledger.py` provides a separate paper-only selection and settlement ledger to feed the 300-selection prospective certification gate. It requires an explicit, versioned selection policy; there are no default thresholds. The policy specifies allowed bookmakers, minimum model probability, minimum edge, minimum expected return, decimal-odds bounds and fixed stake units. The module records the exact model/feature digests, quote observation ID, odds source digest, fixture-crosswalk digest, decision timestamp, policy digest and derived expected value. It only uses quotes captured by the explicit decision timestamp; later pre-kickoff price movements cannot leak into a paper selection.

One selection per fixture/market is allowed, and conflicting re-selections are rejected rather than silently replacing history. Settlements are append-only, must occur after kickoff and carry an independent source-evidence digest. Settled rows can be exported directly into the certification evaluator's prospective input format. It has no real-money order, database, publication or Telegram capability. No selection strategy has been activated and no prospective sample exists yet; a policy must be reviewed and pre-registered before collection begins.

### Offline certification runner

`scripts/evaluate_market_release_certification.py` joins the multi-origin walk-forward report, point-in-time odds ledger, settled prospective-selection ledger and a verified-source-digest registry, then writes one atomic certification report. It is network-free and cannot write databases, execute orders, publish predictions or send Telegram.

The verified-source registry is emitted by the restore CLI and is itself signed with the same allowlisted KMS key. It contains `schema_version: 1`, the `veltrix-evidence-archive-receipt-v2` schema, the union of `verified_source_evidence_sha256` digests, and a non-empty `verified_archive_receipts` list. The registry signature covers the digest set and all receipt attestations; the runner verifies that signature through a KMS client selected only from the configured out-of-band ARN-to-region allowlist. A hand-edited registry fails signature verification. Each receipt attestation records `archive_receipt_signature_verified: true`, `receipt_sha256`, `receipt_signing_key_arn` and `run_id`. Missing crosswalk or archive digests fail the provenance gate.

Example invocation (evidence inputs are local; the registry signature is checked using the configured AWS KMS trust key):

```sh
export VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON='{"arn:aws:kms:us-east-1:123456789012:key/REPLACE":"us-east-1"}'
python scripts/evaluate_market_release_certification.py \
  --walk-forward-report walk-forward-report.json \
  --odds-ledger bookmaker-odds-ledger.json \
  --prospective-ledger prospective-value-ledger.json \
  --verified-digests verified-source-digests.json \
  --benchmark-bookmaker <qualified-bookmaker-key> \
  --evaluated-at 2026-11-10T20:00:00Z \
  --output market-release-certification.json
```



For multi-batch acquisition, merge the per-restore signed registries before certification:

```sh
python scripts/merge_verified_source_digest_registries.py \
  --output verified-source-digests-merged.json \
  restore-batch-001/verified-source-digests.json \
  restore-batch-002/verified-source-digests.json
```

The merger verifies every input registry using the out-of-band KMS allowlist, unions the source digests, deduplicates receipt attestations by receipt SHA-256, rejects conflicting identities, and signs the aggregate registry with the current allowlisted signing key. This supports explicit key rotation: old receipt registries remain verifiable through their old trusted keys, while the merged registry is signed by the current key. The certification runner verifies the aggregate signature and accepts receipt attestations from multiple trusted historical keys. The allowlist must include every key needed to verify the inputs and the current signing key.

### Exact-byte The Odds API response capture

The existing `TheOddsAPIClient` now has explicit `odds_for_sport_with_raw` and `event_btts_with_raw` methods. They preserve the exact HTTP response bytes, compute SHA-256 over those bytes, record retrieval time and quota headers, and return the parsed event payload alongside the bytes. The existing JSON-only client methods retain their original return contract. Raw capture is bounded to one request per method call and disables automatic retries to avoid hidden duplicate quota consumption. The returned bytes must be written to the encrypted evidence archive before observations are treated as certification evidence; this change does not itself call the provider or archive the response.

### Prediction-independent team identity utility

The canonical team-name normalizer now lives in `app/team_name_normalization.py`, an identity-only module with no prediction/model dependencies. The legacy `live_predictions._name_key` remains as a compatibility wrapper, while `provider_adapters.py` imports the standalone normalizer directly. This removes the provider adapter's direct import dependency on the legacy prediction pipeline without changing its alias behavior. Women's/reserve suffixes remain distinct; unknown names are normalized but never fuzzy-merged.
