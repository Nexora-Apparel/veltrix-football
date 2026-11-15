# VELTRIX FOOTBALL 2.0 — Stage 2 PIT Historical Data Acquisition
**Date:** 2026-11-15  
**Stage:** 2 — Rights-approved, genuine point-in-time historical observations  
**Status:** OPEN — no historical source is currently PIT-certified

## 1. Objective

Acquire historical observations that can be proven to have been available at the prediction cutoff. Preserve source publication/effective time, provider snapshot time, collector retrieval time, exact raw bytes, response hash, item hash, provider identity, rights approval and revision lineage.

A result downloaded after a match is not a pre-match feature. A current API response containing old match statistics is not automatically an as-of historical snapshot. Import time, kickoff time, inferred availability and first-observed time must never be substituted for source publication/effective time.

Keep non-PIT historical results available for permitted label/settlement and identity work, but exclude them from PIT feature sets and chronological walk-forward training.

## 2. Verified baseline

- Operational staging baseline last documented: 2,496 fixtures, 4,509 source observations, 72 provider responses, 25 prospective shadow ledger events, 0 odds quote observations.
- Historical result observations have no verified source publication timestamps and remain non-PIT.
- 5DollarFootballAPI is the primary source for bounded prospective fixture/result collection. Owner-approved personal-use scope covers collection, cache, historical import, model training, benchmarking, public display and storage for seven account-entitled competitions, subject to attribution and no raw-feed redistribution. This does not make previously captured result rows PIT.
- The Odds API owner authorization/Terms review covers personal-use storage and derived analytics/model training for five configured soccer keys and bounded markets. Existing account evidence is a sports catalogue response, not historical odds endpoint entitlement or bookmaker quote evidence.
- GOAL API and StrikerAPI remain blocked pending monthly reset and fresh authorization. Do not probe, retry or spend credits before reset.
- OpenFootball Nigeria archive and earlier OpenFootball/OpenPlay/PitchAPI research remain non-PIT; do not repeat that discovery work absent new evidence.
- No provider request, paid-plan change, credit spend, production write, schedule activation, Telegram send or production deployment is authorized by this document.

## 3. Candidate-source qualification

### A. The Odds API — strongest existing candidate for historical bookmaker snapshots

Official V4 documentation describes historical odds snapshots from 2020-06-06, initially at 10-minute intervals and at 5-minute intervals from September 2022. Historical endpoints return the closest snapshot equal to or earlier than the requested ISO-8601 timestamp. Historical odds endpoints are restricted to paid usage plans. Historical event odds and event-market availability endpoints are also documented.

Potential use:
- Timestamped bookmaker snapshots for 1X2 (h2h) and totals.
- BTTS only where the market was actually present in the returned bookmaker snapshot; never infer absent markets.
- Matched bookmaker benchmark and quote coverage, subject to exact event/fixture identity and market-level timestamp verification.

Qualification blockers:
1. Existing evidence is only a no-credit sports catalogue response; zero event-odds responses and zero historical odds responses are stored.
2. Confirm current account plan and endpoint access without a credit-consuming call.
3. Confirm current quota with a fresh no-credit preflight.
4. Confirm rights/market/region scope for intended personal-use historical retrieval; existing owner authorization is bounded and must be rechecked against the exact request.
5. Execute only the documented one-event, one-UK-region, three-market probe (h2h, totals, btts) with a hard cap of one credit-consuming request and at most 3 credits, no retries, staging-only persistence, exact raw response retention and post-commit reconciliation. Do not run until fresh quota and endpoint/rights checks pass.
6. Preserve the outer historical snapshot timestamp separately from each bookmaker market's last_update. A snapshot timestamp alone does not prove every contained quote's source update time.
7. Verify event identity against the exact provider event and canonical fixture crosswalk. Reject ambiguous matches.
8. Validate historical timestamp coverage by competition, market, bookmaker and prediction cutoff before certification.

Decision: **CONDITIONAL CANDIDATE — not yet demonstrated in this account.** Historical odds can supply PIT market-price observations, but cannot supply the full historical team/player feature set.

Official documentation: https://the-odds-api.com/liveapi/guides/v4/

### B. Sportradar Soccer API — retrospective match statistics, not yet PIT evidence

Official historical-data documentation says competition coverage varies, some data can extend to 2007, and historical seasonal statistics/schedules/summaries are accessible. It also notes data points may be added to newer API versions over time. Its FAQ states full match data is archived after one year and only basic score information remains; a separate historical statistics API is on the roadmap without an ETA.

Implication: retrospective season and match statistics may support descriptive analysis and identity research, but current historical feeds do not establish what exact data version was available before each historical kickoff. Current coverage metadata may also be applied to completed matches rather than the coverage that existed when played.

Decision: **NOT PIT-QUALIFIED.** Do not treat generated_at, season statistics or current historical endpoints as proof of point-in-time availability. Reconsider only if the provider can supply timestamped as-of snapshots/revisions or an explicitly licensed immutable historical feed with effective-time lineage.

Official documentation:
- https://developer.sportradar.com/soccer/docs/soccer-ig-historical-data
- https://developer.sportradar.com/soccer/reference/soccer-faq

### C. Sportmonks Premium Odds — short-retention odds change feed

Official documentation describes historical premium pre-match odds updates and bookmaker_update timestamps, but the price-history feed is retained only until seven days after the fixture starts. It is an update feed with a five-minute maximum query interval, not a multi-season historical odds archive.

Decision: **NOT SUITABLE FOR THE CURRENT MULTI-SEASON HISTORICAL BACKFILL.** Could only be reconsidered for near-term prospective capture if a separate rights/plan check and retention test pass.

Official documentation:
https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/premium-odds-feed/premium-pre-match-odds/get-updated-historical-odds-between-time-range

## 4. PIT admission contract

Every candidate observation must carry:
- provider, provider account scope, provider competition ID and provider event ID
- exact canonical fixture identity and valid-time crosswalk
- source_published_at or provider-defined source_effective_at
- provider snapshot timestamp where applicable
- bookmaker, market, selection, line, price and market-level last_update for odds
- retrieved_at (collector clock) and recorded_at (database commit clock)
- request parameters, endpoint, response status and immutable raw response bytes
- raw response SHA-256 and canonical item SHA-256
- rights approval ID, source terms evidence hash, purpose, competition/market/region scope and time-validity
- revision/version identity and supersession lineage where provider revisions exist

An observation may enter a feature set for cutoff T only when provider source effective/publication time is known and <= T, relevant market update time is <= T, identity is exact, rights were valid at collection/storage/use, and data is not a post-event result or retrospectively updated aggregate. Retrieval time is retained for audit and never substituted for source time.

If the provider cannot expose reliable source-effective time or revision history, store the observation as non-PIT and exclude it from PIT model training/evaluation.

## 5. Execution sequence

1. Preserve the current staging baseline and verify exact operational staging branch/database before any write.
2. Revalidate existing Odds API approval against historical endpoint, configured competitions, UK region, h2h/totals/btts, personal-use storage and model-training purpose.
3. Perform a fresh no-credit quota/account preflight only; do not call historical odds endpoints during preflight.
4. If plan entitlement, rights, remaining quota and immutable one-request/3-credit guard all pass, run exactly one future-event market probe in staging. No retries or batch backfill.
5. Reconcile raw response bytes, hashes, event identity, snapshot timestamp, bookmaker market timestamps, request cost and quota delta from a fresh read-only database connection.
6. Produce a competition × market × bookmaker × timestamp coverage matrix and PIT eligibility report. Missing coverage remains missing.
7. In parallel, request written technical confirmation from any candidate provider that can offer immutable as-of match/team/player observations and historical revision lineage; a marketing claim of historical data is insufficient.
8. Expand capture only after the one-event probe passes every evidence and usage check. Keep data provider-specific and append-only.
9. Re-run PIT leakage audits and chronological challenger evaluation only on admitted PIT rows. Keep all existing non-PIT records excluded.
10. Stage 2 remains open until a rights-approved PIT feature dataset has demonstrated usable competition coverage and passed independent provenance/chronology validation.

## 6. Explicit exclusions

- No synthetic timestamps, inferred publication times, kickoff-based availability proxies or retrospective backdating.
- No promotion of the 2,496 imported historical rows, the 671-row 5Dollar first-observed capture, or other current-result downloads into PIT features.
- No repeated OpenFootball/OpenPlay/PitchAPI discovery.
- No GOAL API or StrikerAPI calls before monthly reset and fresh authorization.
- No broad Odds API backfill, batch requests, retries or quota spending beyond the bounded one-event probe.
- No production DB writes/migrations, public predictions, value-bet unlock, 06:00 WAT schedule, Telegram delivery or Vercel production deployment.

## 7. Stage 2 exit criteria

- At least one provider contract/approval explicitly covers intended personal-use collection, storage, historical retrieval and model evaluation for each admitted dataset.
- Every admitted PIT row has exact raw-response/item hashes, exact fixture identity, valid source-effective timestamp and traceable rights evidence.
- Revision and correction behaviour is documented; records with unknown as-of state are excluded.
- Coverage is measured by competition, season, feature, market, bookmaker and cutoff time; missingness is not hidden or imputed as source evidence.
- Independent PIT audit passes with zero fabricated/backdated timestamps and zero post-cutoff leakage.
- Reproducible manifests and dataset hashes are persisted in isolated staging.
- No model or market is called certified solely because data acquisition or software tests passed.

## 8. Immediate next action

The highest-value bounded next action is the existing Odds API one-event historical/market qualification path, but **do not spend credits yet**: first inspect the account's current plan/remaining quota through the zero-credit endpoint and verify approval scope and the one-request/3-credit guard. Separately, the project still needs a provider capable of supplying immutable as-of team/player/match observations; Sportradar's currently documented retrospective feeds do not establish this requirement.
