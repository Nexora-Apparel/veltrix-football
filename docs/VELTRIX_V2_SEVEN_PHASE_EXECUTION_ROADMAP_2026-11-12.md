# VELTRIX FOOTBALL 2.0 — Seven-Phase Execution Roadmap

**Baseline date:** 2026-11-12  
**Execution policy:** strict sequential completion; no phase is marked complete without verified evidence.

| Phase | Scope | Exit condition | Current status |
|---|---|---|---|
| 1 | Evidence-bound certification integrity | Immutable evidence manifests, raw-row recomputation, chronological/point-in-time checks, source-response hashes, signed-attestation verifier, fail-closed runtime/Telegram consumers and full CI | COMPLETE — PR #63, full CI passed (561 tests) |
| 2 | Provider rights and access | Current terms/licence evidence, source-specific permitted-use approvals, attribution rules, account endpoint entitlements and exclusions; rights/access tests pass | IN PROGRESS — PR #64 |
| 3 | Traceable data pipeline | Source-linked response bytes, entitlement snapshots, provenance/availability timestamps, versioned fixtures/results, quarantine, resumable isolated import, pagination/accounting and dry-run acceptance | NOT STARTED |
| 4 | Independent prediction engine | New model architecture built independently; no legacy prediction code, priors, feature logic or calibration reused; point-in-time feature contracts and model versioning | BLOCKED UNTIL PHASE 3 COMPLETE |
| 5 | Prospective paper trading | Immutable pre-kickoff selections/quotes, source-backed settlements, market-specific sample coverage and risk-controlled paper ledger | NOT STARTED |
| 6 | Website and Telegram integration | Dashboard/prediction/status/market experience, approved report format, paper tracking and same verified certificate decision across all consumers | NOT STARTED |
| 7 | Final release validation | Full walk-forward and prospective certification thresholds, regression/security tests, production/Telegram/scheduler parity and explicit release approval | NOT STARTED |

## Hard sequencing rules

1. Phase 1 must be complete before Phase 2 work is accepted.
2. Phase 2 must be complete before Phase 3 ingestion begins.
3. Phase 3 must be complete before any Phase 4 model implementation begins.
4. Phase 4 must pass independent model validation before Phase 5 paper trading begins.
5. Phase 5 must satisfy prospective sample and data-quality requirements before Phase 6 publication integration.
6. Phase 7 is the only phase that may authorize production deployment, Telegram activation or scheduling.

## Release invariants

- Preserve the existing website, APIs, Telegram infrastructure, credentials and valuable historical records.
- Do not reuse legacy prediction models, fallback priors, probability logic, feature engineering or calibration.
- Keep value betting locked until source-attested evidence satisfies every market-specific gate.
- Keep the daily prediction workflow disabled, Telegram delivery inactive and production deployment disabled until Phase 7.
- No production database writes or imports during provider rights qualification or isolated dry-run design.
- Do not spend on provider upgrades or historical odds access without an explicit approved budget and verified need.
- Avoid unnecessary Vercel deployments; preserve daily deployment quota.

## Certification gates carried into Phase 7

- Walk-forward: at least 1,000 settled fixtures per market.
- Prospective: at least 300 settled selections per market over at least 90 distinct WAT match dates.
- Pre-kickoff timestamped odds coverage: at least 98%.
- Net ROI positive and date-clustered 95% lower ROI confidence bound positive.
- 1X2 Brier score and log loss both beat de-vigged bookmaker comparison on identical fixtures for full and recent holdout.
- Source, fixture, model, calibration, quote and settlement lineage fully reconciled.
- Same verified release decision used by runtime, website and Telegram.

Phase 4 must not be opened while Phase 3 remains incomplete, even if later-phase work appears technically possible.
