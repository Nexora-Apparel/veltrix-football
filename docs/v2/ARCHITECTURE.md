# VELTRIX FOOTBALL 2.0 — Architecture Baseline

Status: proposed implementation contract for the isolated `v2/foundation` branch.
Production status: NOT deployed. V1 remains the production system until V2 passes release acceptance.

## 1. Goals

Build a reliable football intelligence platform with independently testable data ingestion, canonical fixture identity, historical evidence, market-specific modelling, validation, publication, website delivery and Telegram delivery.

The primary objective is forecast integrity. Fixture volume is secondary. No system component may manufacture evidence or turn missing data into a fixture-specific forecast.

## 2. Non-negotiable invariants

1. Preserve the website/API/Telegram delivery infrastructure, original data, V1 source and production artifacts for audit/rollback. Do not reuse V1 prediction logic in V2. Keep `main`, production storage and `command-data` unchanged during development.
2. Never delete, rewrite or migrate production records in place. All migration work begins with read-only inventory, backup/export verification and a versioned migration plan.
3. Every provider record retains provider name, provider fixture ID, provider competition ID, raw payload reference/hash, ingestion timestamp and source timestamps.
4. A canonical fixture is created only when identity is sufficiently certain. Ambiguous candidates are quarantined with explainable match evidence; they are not silently merged or dropped.
5. Team identity includes squad category (senior men, women, youth, reserve and age group). Aliases require explicit verification and provenance.
6. Historical evidence lookup must return an explicit result: FOUND, NOT_FOUND, QUERY_FAILED, IDENTITY_MISMATCH or INSUFFICIENT_COVERAGE. These states must never collapse into a generic empty result.
7. No global/competition prior, default probability, placeholder or copied probability distribution may be published as a fixture-specific forecast.
8. Every forecast stores its fixture identity, model name/version, feature snapshot/version, training cutoff, generation timestamp, input evidence references, calibration version and eligibility decision.
9. Every market is evaluated independently. A failure in one market does not imply a pass or failure in another.
10. One immutable report artifact is the source of truth for the website and Telegram. Both channels must identify the same report ID and content hash.
11. Past-kickoff, live, postponed, cancelled and completed fixtures cannot receive a pre-match forecast.
12. Value publication remains locked until its market-specific release certificate passes.
13. Provider failure must be observable. Primary fixture/result ingestion failure blocks report generation; optional odds-provider failure is recorded and does not fabricate prices.
14. All times are stored in UTC and rendered in Africa/Lagos (WAT).
15. No bookmaker execution or automated betting is in scope.

## 3. Rebuild boundary\n\nV2 is a clean replacement of the complete prediction stack, not an incremental edit of V1. No V1 model, feature pipeline, identity matcher, probability generator, calibration routine, value calculator, eligibility implementation or report-generation prediction logic may be imported or called by V2. Existing website, API transport/provider credentials and Telegram delivery infrastructure are retained as integration surfaces only. Their prediction-facing adapters and data contracts are replaced with V2 contracts. Legacy models and reports remain read-only audit material and are not inputs, priors, labels, calibration data or fallback paths for V2. See `docs/v2/REBUILD_BOUNDARY_DECISION.md` for the binding decision.\n\n## 4. Target architecture

Use a modular monolith first, with strict domain boundaries and ports/adapters. Avoid premature microservices. Each module has explicit input/output contracts and can be tested without network access.

- `ingestion/`: provider adapters, request budgets, raw response capture, retry policy and idempotent ingestion.
- `identity/`: competition/team/fixture resolution, verified aliases, candidate scoring and quarantine.
- `history/`: historical dataset import, normalized match records, coverage diagnostics and evidence queries.
- `features/`: reproducible, timestamp-safe feature snapshots; no post-kickoff leakage.
- `models/`: independent 1X2, BTTS and totals model interfaces and versioned implementations.
- `calibration/`: market/model-specific calibration trained only on chronological training windows.
- `eligibility/`: single authoritative publication eligibility decision shared by all markets and report paths.
- `validation/`: chronological walk-forward tests, benchmark comparisons, calibration diagnostics and prospective paper ledger.
- `value/`: de-vigging, quote matching, edge/EV screening and market-specific release certificates.
- `reports/`: immutable report generation, schema validation, content hashing and publication manifest.
- `delivery/`: website data adapter and Telegram sender consuming the exact same report artifact; transactional/outbox-style retry and idempotency.
- `operations/`: health checks, provider diagnostics, run manifests, audit logs and alerting.

## 5. Prediction lifecycle

`provider payload -> normalized source record -> canonical identity decision -> historical evidence result -> point-in-time feature snapshot -> market model -> calibration -> market eligibility -> forecast record -> immutable report`

The shared eligibility gate runs before market forecasts are publishable. A model may be evaluated in research mode when evidence is insufficient, but its output is explicitly research-only and cannot enter a public forecast field.

Recommended explicit forecast states:
- `ELIGIBLE`
- `UNSUPPORTED_COMPETITION`
- `INSUFFICIENT_HISTORY`
- `HISTORY_NOT_FOUND`
- `HISTORY_QUERY_FAILED`
- `HISTORY_IDENTITY_MISMATCH`
- `AMBIGUOUS_FIXTURE_IDENTITY`
- `INVALID_FEATURES`
- `MODEL_ERROR`
- `CALIBRATION_UNAVAILABLE`
- `PAST_KICKOFF`

No probability fields are emitted for withheld states. The API/report schema must make invalid combinations impossible or reject them during validation.

## 6. Data and provider strategy

Retain existing provider credentials as secret references, not source-code values:
- `FIVEDOLLARFOOTBALL_API_KEY`: intended primary fixture and recent-results provider.
- `THE_ODDS_API_KEY`: supplementary bookmaker prices.
- `ODDSPAPI_API_KEY`: optional independent market enrichment.
- InferSports remains disabled unless live market coverage is demonstrated.
- Open historical dataset/imports are retained as historical evidence with dataset version and license provenance.
- API-Football/API-Sports is not an active runtime dependency. Do not call or modify `API_FOOTBALL_KEY` as part of the V2 runtime.

Provider adapters must not share provider-specific IDs as canonical IDs. Provider-specific mappings live in explicit source-link tables.

## 7. Storage model (logical)

Core entities:
- `provider_sources`
- `provider_competitions`
- `provider_teams`
- `provider_fixtures`
- `canonical_competitions`
- `canonical_teams`
- `team_aliases` (verified, scoped and audited)
- `canonical_fixtures`
- `fixture_identity_decisions`
- `historical_matches`
- `ingestion_runs`
- `feature_snapshots`
- `model_versions`
- `forecasts`
- `market_quotes` (timestamped, source/bookmaker/event identity)
- `eligibility_decisions`
- `validation_runs`
- `paper_selections` and `paper_settlements`
- `release_certificates`
- `reports` and `report_deliveries`
- `audit_events`

All source IDs and original payload references are retained. Database migrations are additive and reversible where practical. V1 tables are not repurposed in place.

## 8. Validation and release controls

A market is released independently. Preserve the established minimum evidence requirements:
- At least 1,000 chronological walk-forward matches per market.
- At least 300 settled prospective selections across at least 90 distinct dates.
- At least 98% timestamped pre-kickoff odds coverage.
- Positive cumulative flat-stake ROI and a positive lower 95% confidence bound using match-date-cluster bootstrap.
- 1X2 additionally beats the de-vigged bookmaker benchmark on both Brier score and log loss.
- Evidence must match the exact deployed model/calibration version.

Existing value-screen thresholds (minimum 4 percentage-point edge, 5% theoretical expected return, probability at least 45%, decimal odds 1.50–4.00) are retained as research-screen settings, not a release guarantee. They do not override release certificates.

## 9. Report and delivery contract

A report is immutable and has:
- `report_id`
- `report_date` in Africa/Lagos
- `generated_at_utc`
- `schema_version`
- `pipeline_version`
- `model_versions`
- `input_run_ids`
- `fixture_count`
- per-fixture identity, kickoff, eligibility status and market forecast status
- source/odds coverage diagnostics
- `content_sha256`

Website and Telegram read the same published report ID. Telegram delivery is idempotent per report/channel/recipient. Retries may resend a failed delivery but may not create a different report or duplicate a successful delivery.

## 10. Deployment strategy

- Develop only on `v2/foundation` and subsequent `v2/*` branches.
- Keep `main` and `command-data` unchanged until V2 is accepted.
- Use a separate V2 preview deployment and isolated database branch/schema.
- Do not point V2 at the production write database during development.
- Promote only through reviewed pull requests and explicit release checks.
- Preserve the current V1 deployment as rollback target.

## 11. Delivery schedule and timezone

Target Telegram report delivery remains approximately 06:00 Africa/Lagos. Schedulers use UTC (05:00 UTC corresponds to 06:00 WAT). A run manifest records scheduled time, actual start, completion and delivery timestamps.

## 12. Definition of done

V2 is not production-ready until:
1. Data migration is reconciled with zero unexplained source-record loss.
2. Identity and history diagnostics are auditable.
3. All no-history and ambiguous fixtures are withheld from public forecast fields.
4. Fixture-specific probabilities are demonstrably non-generic and reproducible.
5. Model tests and chronological validation pass.
6. Market release certificates pass independently.
7. Website and Telegram consume one identical immutable report.
8. Scheduled delivery, retries, idempotency and rollback are tested.
9. No production secrets or live writes are exposed in preview environments.

Until then, V2 is development/research only. V1 prediction code is legacy and excluded from V2; its production artifacts remain preserved for audit and rollback until the controlled cutover is complete.


## Source-rights enforcement

Every source must have a versioned `SourceRights` record before V2 ingestion, training, calibration, caching or public display. `veltrix_v2/domain/rights.py` provides `evaluate_source_use` and `require_source_use`; unknown or incomplete terms evidence, an ungranted purpose, prohibited commercial use or missing required attribution fails closed. Each decision carries the terms URL/version and evidence SHA-256 for traceability.

The rights gate is currently a tested domain primitive (34 hosted V2 tests pass), not yet integrated into provider ingestion. Integration is a prerequisite to the first V2 data import. The active 5DollarFootballAPI and The Odds API terms permit commercial model/app use within their stated restrictions; their actual account plans and data depth remain unverified. Football-Data.co.uk-derived history remains excluded from V2 commercial training unless a commercial licence or written permission is obtained.
