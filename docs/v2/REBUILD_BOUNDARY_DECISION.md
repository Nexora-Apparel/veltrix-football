# VELTRIX FOOTBALL 2.0 — Rebuild Boundary Decision

**Status:** Accepted project constraint  
**Branch:** `v2/foundation`  
**Decision:** Preserve delivery and external integration infrastructure; replace the complete prediction stack.

## 1. Retain

The following are infrastructure to preserve, not prediction logic to inherit:

- Existing website, domain, hosting and user-facing shell.
- Existing API provider accounts, credentials, access arrangements and provider connectivity, where valid.
- Existing Telegram bot, channel/chat configuration, delivery credentials and message transport.
- Existing historical match, odds, result and settlement records, including source IDs, timestamps and provenance.
- Existing production deployment and report artifacts as a read-only legacy/rollback reference during the rebuild.

Preserving API connectivity does **not** mean preserving old API-to-feature transformations, old fixture matching, old model inputs, or old prediction decisions. Those are part of the rebuild.

## 2. Retire and rebuild from a clean V2 boundary

No V1 prediction component is an implementation dependency of V2. Rebuild all of the following as new V2 modules:

- Provider ingestion normalization and source-record validation.
- Fixture, competition, team and squad identity resolution.
- Historical data access, deduplication, quality assessment and point-in-time snapshots.
- Feature engineering and team-strength estimation.
- Training datasets, temporal splitting, model training and model selection.
- Every predictive model and market-specific probability generator, including 1X2, BTTS and totals.
- Probability calibration and uncertainty estimation.
- Eligibility, confidence, value and price/odds evaluation.
- Backtesting, walk-forward evaluation, prospective paper tracking and release certification.
- Forecast generation, immutable report creation, publication gates and delivery payload construction.

The old Poisson, Dixon-Coles, Elo, neutral/global-prior and other legacy model implementations are not to be copied, wrapped, imported, or silently reused. V2 may independently evaluate a known statistical method as a new implementation, but it must earn admission through V2's own data, tests and validation. Similarity of algorithm name is not permission to port old code.

## 3. Hard isolation rules

1. V2 must not import from V1 prediction modules or call V1 prediction functions.
2. V1 model outputs may be retained only as historical audit/comparison data. They must never become V2 features, priors, labels, calibration inputs or fallback probabilities.
3. No generic, global, competition-only or neutral probability vector may be published as a fixture-specific forecast.
4. Missing, stale, ambiguous, failed or insufficient evidence results in an explicit withheld status—not a fabricated prediction.
5. Each market has independent eligibility and validation. Passing one market does not authorize another.
6. Website and Telegram must render the same immutable V2 report ID and content hash. They are delivery clients, not model engines.
7. The existing production system and original data remain untouched until the V2 replacement is independently tested and a controlled cutover is approved. This preserves rollback and auditability; it does not authorize V1 logic inside V2.

## 4. API and data boundary

Retain provider credentials and transport integrations where usable. Build new V2 adapters that preserve the raw provider payload, provider fixture ID, competition ID, team identifiers, timestamps, market identifiers, bookmaker and source provenance. Never rewrite or discard original provider identity.

Do not change, expose, rotate or test the suspended `API_FOOTBALL_KEY` as part of this decision. The selected current provider strategy remains subject to a fresh availability and coverage audit before V2 ingestion is enabled.

Historical records are immutable source material. Migration must be additive, reproducible, checksummed where practical, and traceable back to original records. No production database is selected until the real V1 storage location and data inventory are verified.

## 5. Acceptance criteria for V2 replacement

- A clean dependency graph proves no V1 prediction imports or runtime calls.
- All new models have reproducible training data, feature definitions, training cutoffs and version identifiers.
- Chronological walk-forward evaluation prevents future-data leakage.
- Each market passes its own minimum sample, prospective settlement, date coverage, timestamped odds coverage, ROI confidence and/or proper-scoring-rule gates.
- Calibration is measured on held-out chronological data.
- Every forecast is traceable to source records, identity decisions, feature snapshots, model version and calibration version.
- Website and Telegram are verified against the exact same immutable report.
- A failed gate withholds that market; it never triggers a legacy fallback.

## 6. Immediate implementation order

1. Complete V1 call-graph and storage audit without modifying V1.
2. Freeze the V2 module contracts and create the isolated V2 data schema only after the source inventory is verified.
3. Build provider adapters and canonical identity resolution.
4. Build historical evidence and point-in-time feature pipelines.
5. Implement new baseline models as independent V2 code, then progressively test more capable model families.
6. Build calibration, validation and market-specific release gates.
7. Build immutable report generation and connect the retained website/Telegram delivery surfaces.
8. Run shadow and prospective paper validation before any production cutover.

**Non-negotiable:** VELTRIX FOOTBALL 2.0 is a new prediction system behind retained delivery infrastructure—not a refactor of V1.
