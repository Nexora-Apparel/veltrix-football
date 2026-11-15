# VELTRIX FOOTBALL 2.0 — OddsPapi historical odds qualification

**Review date:** 2026-11-15  
**Stage:** 2 — data foundation  
**Disposition:** TECHNICALLY PROMISING; NOT RIGHTS-APPROVED; NO DATA ADMITTED

## Executive determination

OddsPapi is now the strongest newly identified technical candidate for timestamped bookmaker-specific historical 1X2 prices and per-outcome settlement evidence. Its v4 API documents a fixture-level historical timeline with individual `createdAt` timestamps, decimal prices, limits and active flags; a separate score endpoint returns period scores with `updatedAt`; and a settlement endpoint returns per-outcome grades.

This does **not** qualify OddsPapi as a VELTRIX source. The published terms prohibit standalone resale/repackaging/redistribution but do not clearly grant the project's required rights for internal storage, model training, backtesting, derived research, public display or retention. No OddsPapi source-approval row exists in the staging database. No OddsPapi response has been requested or persisted by this qualification review. Written provider clarification and a source-specific approval are mandatory before any API request or ingestion.

## 1. Technical capability documented by the provider

### Historical odds

Official endpoint: `GET /v4/historical-odds?fixtureId=...&bookmakers=...`

The documented response contains bookmaker → market → outcome → player → snapshot rows. Each snapshot includes:

- `createdAt`: timestamp when the historical price record was created;
- `price`: offered price;
- `limit`: available stake limit where supplied;
- `active`: whether the price was active;
- `exchangeMeta`: optional exchange metadata.

The endpoint accepts up to three bookmaker slugs per request. It has a documented five-second endpoint cooldown. Finished/cancelled fixtures may return an ETag and `Cache-Control: private, max-age=259200`; the ETag is tied to the exact query. The provider's documentation says historical odds have been available since January 2026. A provider blog describes a rolling history of up to 100 days per fixture and warns that depth varies by fixture; that more restrictive operational window must be used until the provider confirms retention in writing.

For soccer, provider guides identify Full Time Result market ID 101 and home/draw/away outcome IDs 101/102/103. The collector must still resolve market and outcome definitions from the API's market catalogue rather than treating these IDs as immutable assumptions.

**Close definition:** use the last active snapshot with `createdAt < scheduled_start_time`, separately for each bookmaker and outcome. Never take the last row unfiltered: the historical stream continues into in-play. Preserve the scheduled kickoff and any provider actual-start timestamp separately. A missing pre-kickoff leg makes that bookmaker's 1X2 close incomplete.

### Football coverage signals

The provider's live football coverage page reports hundreds of active tournaments and current bookmaker boards. Its Brazilian football guide identifies:

- Brasileiro Série A: tournament ID 325;
- Brasileiro Série B: tournament ID 390.

The Brazilian guide demonstrates historical-odds inspection on played Série A fixtures and states the same endpoint is used for historical price timelines. This is useful coverage evidence, but it is **not** fixture-level historical coverage proof for the VELTRIX 763-fixture universe. In particular, no historical response has yet been inspected for a VELTRIX Brazil Série B fixture. Treat every competition's historical 1X2/bookmaker depth as unverified until a permitted, bounded fixture-level pilot proves it.

### Scores and settlements

The provider documents two separate endpoints:

- `GET /v4/scores?fixtureId=...`: period score values with an `updatedAt` timestamp for each period;
- `GET /v4/settlements?fixtureId=...`: per-market, per-outcome grades such as `WIN`, `LOSE`, `HALFWIN`, `HALFLOSS`, `PUSH`, `CANCELLED` and `UNDECIDED`.

These are useful independent settlement signals, but they are not interchangeable. The score response should be retained as the score evidence; the settlement response should grade the exact market/outcome. For 1X2, derive the 90-minute outcome from the agreed full-time score period and reconcile the provider grade. Extra-time/result scores must not silently replace the 90-minute full-time score for ordinary 1X2 markets. Preserve response timestamps, hashes, fixture identity, market/outcome IDs and corrections.

## 2. Request economics and feasibility

Published provider material states the free tier includes 250 requests per month. The historical endpoint is fixture-level and supports up to three bookmakers in one call.

- One historical response for each of 763 fixtures requires at least 763 requests for one selected bookmaker set.
- The 98% threshold (748/763) requires at least 748 fixture requests.
- 25 prospective fixtures per day would require about 750 fixture-level requests per 30-day month for one capture per fixture, before additional polling or retries.
- The 250-request free allowance is therefore insufficient for full 763-fixture historical backfill in one month or 25-fixture-per-day prospective capture.
- Three months of sequential requests would overlap the provider's blog-described rolling 100-day history window; early fixtures could age out before the final batch. Do not assume a complete 763-row backfill is possible on the free tier.
- One response can include at most three bookmaker slugs. The actual bookmaker list must be selected only after per-competition coverage and independent-price deduplication are measured. Multiple regional slugs may be clones; deduplicate by exact fixture/market/selection/price/timestamp tuples, not slug count alone.

No paid plan, custom plan, API key, quota increase or subscription has been requested or purchased.

## 3. Rights and approval gap

Published Terms: https://oddspapi.io/en/legal/terms

The current public terms:
- prohibit reselling, repackaging or redistributing data as a standalone product;
- reserve the provider's right to revoke access for misuse;
- state that the provider does not guarantee data accuracy or completeness.

The public terms do not clearly specify:
- internal storage and retention period for historical raw responses;
- model training, validation, benchmarking and backtesting rights;
- whether non-commercial derived probabilities, ROI/CLV statistics and performance summaries may be displayed in VELTRIX;
- whether raw historical response bytes may be retained in private staging for audit;
- whether the free plan's 250-request allowance applies to the historical endpoint in the same way as ordinary API requests.

The project-wide non-commercial restriction is an additional VELTRIX constraint; it does not replace or expand the provider's license. Before onboarding, obtain written provider confirmation covering the intended non-commercial uses, raw-response storage/retention, derived output display, seven competition scope and the applicable plan/quotas. Then create a dedicated `source_approvals` record with the exact terms version, evidence URL/hash, scope, permitted uses and expiry. Until then: no request, no staging import, no model use.

## 4. Existing VELTRIX source position

### 5DollarFootballAPI

Independent staging read-back on 2026-11-15 confirms 763/763 timestamped Bet365 1X2 **opening** observations across the seven approved competitions. All 763 have provider `opened_at`, retrieval time, rights approval and canonical fixture identity; all are marked PIT-eligible for their opening-quote timestamp.

The fixture odds response exposes `opened_at` for the opening object, but its documented closing object does not expose a quote-level timestamp. Therefore the closing value in that response cannot be admitted as a timestamped close merely because it is labelled `closing`. The full tick-history endpoint `/v1/fixtures/{id}/odds/history?market=1x2` supplies `recorded_at` ticks but requires Ultra. The current account has no evidenced Ultra entitlement. The official pricing page currently lists Ultra at $25/month on monthly billing (or $250 billed annually); this is a plan fact, not authorization to upgrade. No plan change or payment is authorized by this review.

### The Odds API

The current key's historical price pilot returned HTTP 401 with the paid-plan-only restriction. The existing approval covers five European competitions only; Brazil Serie A and Série B are outside its scope. No historical prices are admitted. Do not retry the paid endpoint without independently confirmed entitlement and an expanded rights approval.

### Other candidates

Odds-API.io remains a technical candidate with paid bulk closing lines and a £49/month entry plan, but exact Brazil Série B historical coverage and VELTRIX rights are unverified. ParlayAPI, SockOdds, OddsRelay and OddsIntel retain their previously documented blockers. No provider is promoted by this OddsPapi review.

## 5. Prospective and settlement evidence — staging read-back

Read-only queries against Neon project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging` found:

- 389 accepted AI Midas crosswalk versions remain present: 20 TEAM + 369 FIXTURE, with no missing reviewer/evidence references. The two absent canonical fixtures have zero AI Midas fixture-crosswalk rows.
- 763/763 5Dollar opening-odds observations remain present and PIT-eligible as opening quotes only.
- 2,496 canonical `fixture_results` rows are linked to source observations and rights approvals. Their availability basis is `provider_finished_status_conservative_4d`; this is a conservative post-match settlement-label availability rule, not pre-match feature availability.
- The prospective paper ledger contains 25 `SHADOW_PREDICTION` events, all from `veltrix-results-poisson-v1`, all with `point_in_time_certifiable=false`, no odds snapshot link and no settlement link. Their kickoff dates span 18–21 November 2026. These legacy/non-PIT records must not count toward any market certification threshold or be silently upgraded. They require a new independently validated V2 model and a new valid prospective evidence series.
- No OddsPapi provider response, source observation or source-approval record exists.
- No prospective selection or settlement has been admitted from these 25 shadow records.

The two contradictory AI Midas team-stat rows remain excluded by the source reconciliation/import audit. They are not admitted to normalized feature rows. Do not resolve them by averaging, selecting a side, or inferring a corrected value.

## 6. Certification gates remain unchanged

For each market, the existing acceptance contract requires:
- at least 1,000 chronological walk-forward fixtures;
- at least 300 timestamped prospective settled selections across at least 90 distinct Africa/Lagos match dates;
- at least 98% timestamped odds coverage against the predeclared eligible selection universe;
- net ROI greater than zero and a date-clustered 95% ROI lower bound greater than zero;
- for 1X2, Brier score and log loss better than the de-vigged bookmaker benchmark on identical fixtures and cutoffs;
- exact source, fixture, quote, model, selection and settlement provenance.

No summary label or aggregate report can replace row-level verification. The release path remains fail-closed. Value betting remains LOCKED.

## 7. Next gated actions

1. Preserve all 389 AI Midas crosswalks; preserve both absent fixtures as unresolved; keep both contradictory team-stat rows quarantined.
2. Obtain written OddsPapi rights/retention/derived-display clarification before any API request. If approval is not obtained, do not use the source.
3. In parallel, resolve whether the 5Dollar account can obtain Ultra tick-history access without violating the no-payment/no-upgrade control. No plan change is authorized.
4. Once a source is rights-approved and entitled, run a no-write, bounded fixture-level pilot across all seven competitions. Include Brazil Série B specifically. Verify exact event identity, active 1X2 legs, pre-kickoff timestamp semantics, bookmaker independence, settlement-score agreement, retention and quota.
5. Implement an immutable quote/settlement evidence writer only after the provider-specific schema and approval are accepted. Keep provider response bytes/hashes, source timestamps, retrieval timestamps, request parameters, rights IDs, fixture crosswalk versions and exact source pointers.
6. Keep the V2 model rebuild and certification infrastructure separate from the legacy 25 non-PIT shadow predictions. Do not count legacy records toward 300 prospective selections or 90 dates.

## Public source references

- OddsPapi historical odds endpoint: https://oddspapi.io/en/docs/get-historical-odds
- OddsPapi scores endpoint: https://oddspapi.io/en/docs/get-scores
- OddsPapi settlements endpoint: https://oddspapi.io/en/docs/get-settlements
- OddsPapi terms: https://oddspapi.io/en/legal/terms
- OddsPapi pricing: https://oddspapi.io/en/pricing
- OddsPapi historical odds guide (100-day rolling-window and 250 requests/month statements): https://oddspapi.io/blog/historical-odds-api/
- OddsPapi Brazil football guide (Série A 325, Série B 390): https://oddspapi.io/blog/brasileirao-odds-api/
- 5Dollar odds endpoint: https://5dollarfootballapi.com/docs/odds
- 5Dollar odds-history endpoint: https://5dollarfootballapi.com/docs/odds-history
- 5Dollar pricing: https://5dollarfootballapi.com/pricing
