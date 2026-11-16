# VELTRIX FOOTBALL 2.0 — Comparative closing-odds provider qualification

**Review timestamp:** 2026-11-15 23:26 WAT  
**Stage:** 2 — historical odds, prospective quote evidence and settlement  
**Disposition:** NO NEW PROVIDER APPROVED; 5DOLLAR ULTRA ENTITLEMENT IS THE LOWEST-COST DIRECT TICK-HISTORY PATH; RIGHTS / ACCOUNT ACCESS MUST BE VERIFIED BEFORE USE

## Executive decision

The refreshed comparison does not justify onboarding a new provider or spending money. The most economical direct bookmaker-level route remains the existing 5DollarFootballAPI account **if** its Ultra entitlement can be independently verified: published Ultra pricing is $25/month and includes 19 bookmakers, full odds tick history and broad league coverage. The current key's Ultra entitlement is not evidenced; the history endpoint is explicitly Ultra-only. No upgrade, payment or restricted endpoint request is authorized.

The strongest alternative technical candidates are Odds-API.io (bulk bookmaker closing lines) and SockOdds (recorded tick changes, opening/closing snapshots and graded results). Their documented coverage does not establish the required Brazil Série B or full seven-competition universe: Odds-API.io's public coverage table names Brazil Série A but not Série B; SockOdds' current league catalogue lists no Brazil competition. OddsPapi has historical snapshots, score and settlement endpoints but still has the 100-day / 250-request free-tier constraint and unresolved data rights. The Odds API remains blocked by a direct HTTP 401 paid-historical-plan response.

No new API key was requested, no provider account was created, no provider request or credit was consumed, no subscription was purchased, and no source-approval row or odds observation was written.

## 1. Existing staging state — read-only verification

Neon project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`:

### AI Midas identity and quarantine invariants

- 20 TEAM crosswalks are RESOLVED, with 20 distinct source IDs and 20 distinct canonical IDs.
- 369 FIXTURE crosswalks are RESOLVED, with 369 distinct source IDs and 369 distinct canonical IDs.
- No duplicate source IDs or canonical IDs in either entity type.
- Every resolved row has reviewer and evidence references (zero gaps).
- The two canonical fixtures absent from the source still have zero AI Midas fixture crosswalks.
- Exactly two unresolved `SOURCE_TEAM_STAT_SCORE_CONFLICT` quarantine rows remain open. Both are for the 2026-11-07 Náutico 0–3 CRB source discrepancy, with original source commit, file path, line number, row fingerprint and contradictory observed/expected values retained. No normalized feature admission or correction was made.

### Odds and prospective paper evidence

- The frozen historical acquisition universe remains 763/763 timestamped Bet365 1X2 opening observations (100% opening coverage for that fixed universe).
- A separate prospective capture has added 25 more timestamped Bet365 1X2 opening observations for the 25 shadow-ledger targets. Across those historical and separate prospective opening captures, the staging odds-observation table contains 788 unique fixtures with provider-timestamped opening observations.
- The separate 25 latest-pre-match snapshots are explicitly different: `source_timestamp_basis=unknown`, `availability_basis=collector_first_observed_v1`, `point_in_time_certifiable=false`, `market_selection_eligible=false`, `clv_eligible=false`, `final_close_observed=false`, and `captured_after_associated_prediction_cutoff=true`. The provider's `closing` field on a scheduled match is only the latest pre-match price so far, not the final close. These 25 rows must not be counted as closing prices, PIT quotes, selections or CLV observations.
- The prospective paper ledger still contains 25 `SHADOW_PREDICTION` events, all non-PIT. There are zero linked timestamped odds snapshots and zero settlements. Their kickoff window is 2026-11-18 22:30 UTC through 2026-11-21 15:00 UTC (four Africa/Lagos match dates).
- The 2,496 existing canonical result rows remain source-observation- and rights-linked, with conservative four-day availability. They are not a substitute for the 25 prospective target settlements.
- No feature snapshots, feature links or feature-eligibility events were created in this review. No normalized fixtures/results, paper ledger events or odds rows were written.

## 2. Direct bookmaker-level providers

### 5DollarFootballAPI Ultra — preferred pending entitlement evidence

Published pricing lists Ultra at **$25/month** on monthly billing, with all 1,600+ leagues, 19 bookmakers and full odds tick history back to 2014. The API docs say the fixture-level odds response is Bet365 by default; other bookmakers and the historical tick route require Ultra. The `/fixtures/{id}/odds/history?market=1x2` route returns price ticks ordered oldest first.

Advantages:
- Existing provider, credentials and approved seven-competition scope already exist for 5Dollar opening-odds evidence.
- Direct bookmaker identity and individual timestamped price changes; strongest match to the raw certification evidence contract.
- Lowest published monthly cost among the direct bookmaker-history alternatives reviewed.
- Historical coverage depth is materially better than the newer archives.

Blockers:
- Current API key/account Ultra entitlement is not evidenced; no request has been made to the restricted route.
- The current approved odds source approval is non-commercial and only covers collection, storage, historical import, model training and benchmarking; any use outside those approved uses remains blocked.
- Before any tick-history request, verify actual account plan/entitlement and revalidate exact rights, competition scope, quota and rate limits. Do not upgrade or pay without separate authorization.

Disposition: **PREFERRED TECHNICAL PATH / NOT ENTITLED / NOT ADMITTED**.

### Odds-API.io — strong bulk historical close alternative, coverage gap

Published API information describes:
- `/v3/historical/closing-lines`: settled fixtures with bookmaker closing odds and final scores, up to 366 days, 10 leagues, 30 bookmakers and 100 events per page.
- The response example includes bookmaker, per-market `updatedAt`, and decimal 1X2 prices.
- Closing odds begin in December 2025.
- The bulk closing-lines endpoint is paid-plan only; the cheapest published plan is Solo at €59/month for two bookmakers.
- Per-event `/v3/historical/odds` is described as available on every plan, but new free keys are paused; the cheapest way to start is a paid plan.
- Its public coverage table explicitly lists Brazil Série A (since 28 Jan 2026, 339 matches, median 100 bookmakers) but does not list Brazil Série B.

The public page says closing odds are stored for every settled match in leagues tracked, but does not identify the exact VELTRIX Brazil Série B slug or prove event coverage for the seven frozen competitions. The public sample is CC BY 4.0 but is only Premier League, NBA and NHL, not the complete API archive.

Before qualification: obtain written confirmation of Brazil Série B coverage and exact 763-fixture coverage, provider-specific retention/model/backtest rights, and whether the per-event endpoint supplies a true bookmaker-specific pre-kickoff close with quote-level `updatedAt`. Do not assume that the advertised broad league count implies this specific competition is covered.

Disposition: **STRONG ALTERNATIVE / BRAZIL SÉRIE B AND RIGHTS UNVERIFIED / PAID ACCESS REQUIRED FOR BULK**.

### SockOdds — good tick/settlement design, wrong current competition coverage

SockOdds documents a high-integrity model:
- Pro history records every price change it observes, with `observed_at`, bookmaker, market, selection, decimal price and change kind.
- Separate opening and closing snapshots are available.
- `/results` returns official-source graded outcomes (won/lost/void/dead heat/half results).
- Gaps are explicitly missing; unobserved stretches are not filled in.
- History is Pro-only; the free Developer tier has current prices but no history.
- A seven-day Pro trial is advertised with 10,000 objects and no card; Pro is $299/month after trial.
- History begins 8 Oct 2026 for most leagues, and 22 Dec 2025 for a small explicit list.
- Its current published league catalogue lists EPL, La Liga, Bundesliga, Ligue 1, Serie A, MLS and UCL, but no Brazil Série A or Série B; it explicitly lists Brazilian Série A only as a catalogue key with no prices delivered.

The provider's own historical page confirms no Brazil Série B history coverage in the published league list. A trial does not solve the required seven-competition archive or licensing/retention scope.

Disposition: **TECHNICALLY GOOD / CURRENT COVERAGE FAILS REQUIRED BRAZIL SCOPE / NOT APPROVED**.

## 3. Derived consensus close providers

### OddsIntel Data — possible secondary benchmark only

OddsIntel publishes consensus fair closing prices with `close_ts`, `close_is_final`, number of independent sources and price age. It does not publish bookmaker names or individual bookmaker lines; it prohibits reconstructing individual source prices. Therefore it cannot replace the row-level bookmaker-specific quote evidence required by the current raw certification contract. It may be useful as a secondary market consensus benchmark only if terms and intended use are confirmed.

Plan details:
- Free Sample: yesterday's matches, 200 requests/day, up to 300 rows/answer, internal testing/evaluation only; current/live data delayed two hours.
- Starter: €49/month, 90-day history from 10 Oct 2026, bulk daily closes and internal business use.
- Pro: €149/month, history from 10 Oct 2026, derived figures can be shown inside the user's product.
- Business: from €399/month with written licence/order.
- The terms state the service is for businesses only and not for betting operators or their affiliates. They also prohibit reverse-engineering source bookmaker lines and presenting CLV grades as proof of a betting record.

VELTRIX is a football analytics/value-betting research project. Do not assume the business-only / not-for-betting-operators eligibility condition is met; request written provider clarification before obtaining or using a key. Even if accepted, the product provides derived consensus only, so keep it out of bookmaker-specific certification rows.

Disposition: **SECONDARY BENCHMARK CANDIDATE / USER ELIGIBILITY AND RIGHTS CLARIFICATION REQUIRED / NOT BOOKMAKER-LEVEL EVIDENCE**.

## 4. Other previously reviewed providers

### OddsPapi

The v4 historical endpoint has bookmaker-specific timestamped snapshots, with `createdAt`, `price`, `limit`, `active`; separate scores and settlements endpoints exist. Brazil Série B is listed in the provider's tournament catalogue, but exact historical event coverage is not proven. The vendor material advertises 250 requests/month and up to 100 days of history per fixture. 748 requests are needed for 98% of the frozen 763-fixture universe, so the free quota is insufficient. The public terms do not clearly authorize VELTRIX's required raw retention, model training, backtesting and derived display. No request or approval exists.

Disposition: **TECHNICALLY PROMISING / QUOTA AND RIGHTS BLOCKED**.

### The Odds API

The current account's historical endpoint returned HTTP 401 explicitly stating historical odds require a paid usage plan. The no-credit catalogue probe and 274 remaining ordinary requests did not establish historical entitlement. Brazil Série B is outside the existing five-competition approval. No retry until paid historical access and expanded rights are independently verified.

Disposition: **HISTORICAL ENDPOINT BLOCKED BY DIRECT 401 / DO NOT RETRY**.

### OddsRelay

Historical odds exist from 17 Oct 2026 and its archive is added daily; bookmaker and exchange data are available. However, paid self-serve data is restricted to personal use. Its terms state a business needs an Enterprise Order even for in-house use, with Enterprise starting at £750/month; the free plan/trial is a limited evaluation route. The current 763-fixture historical universe substantially predates its archive start. It is not a practical Stage 2 historical-backfill solution.

Disposition: **NOT FIT FOR HISTORICAL DEPTH; BUSINESS LICENCE WOULD BE REQUIRED FOR PRODUCT USE**.

### TheRundown

The provider advertises tick-level open/change/close/reopen data across 25+ bookmakers. Starter is $49/month with a seven-day history window; backtesting or validation requires prior written permission. Seven days cannot backfill the frozen 90-day archive. It may be considered for prospective capture only after written permission and full seven-competition coverage checks.

Disposition: **PROSPECTIVE-ONLY CANDIDATE / WRITTEN BACKTEST PERMISSION REQUIRED / NOT APPROVED**.

## 5. Recommended provider decision sequence

1. Verify the existing 5Dollar account's actual Ultra entitlement through account evidence or written provider confirmation, without changing the plan. If already entitled, run a strictly bounded no-write parser/coverage pilot on representative fixtures from every approved competition, including Brazil Série B. Do not request history while entitlement is unproven.
2. If not entitled, request a written quote/coverage/rights statement from 5Dollar before any upgrade. No payment is authorized by this document.
3. In parallel, request Odds-API.io written confirmation for Brazil Série B and exact competition/fixture coverage, plus data-retention/model-training/backtest rights. Do not pay before the response.
4. Treat OddsIntel only as a possible secondary consensus benchmark after eligibility clarification; never substitute it for bookmaker-specific raw odds.
5. Do not spend credits on The Odds API historical endpoint; do not use OddsPapi before rights approval; do not use SockOdds for the current Brazil scope; do not onboard OddsRelay without its business licence.
6. For prospective evidence, preserve a fresh provider market timestamp and collector retrieval timestamp separately. A collector timestamp is not a source timestamp. Only a final pre-kickoff bookmaker quote (or explicitly labelled near-close snapshot under an accepted contract) can enter the appropriate market/CLV denominator.
7. Keep score evidence and settlement-grade evidence distinct. Settle only after provider FINISHED status and a valid source response; reconcile score and outcome. Do not treat the existing 2,496 historical result rows as the 25 prospective target settlements.

## 6. Market certification and release status

Per-market certification targets remain unchanged:
- ≥1,000 chronological walk-forward fixtures.
- ≥300 timestamped prospective settled selections across ≥90 distinct Africa/Lagos kickoff dates.
- ≥98% timestamped odds coverage over the predeclared eligible selection universe.
- Net ROI >0 and date-clustered 95% ROI lower confidence bound >0.
- 1X2 Brier score and log loss both better than the de-vigged bookmaker benchmark on identical fixtures and cutoffs.
- Row-level source, fixture, quote, model, selection and settlement provenance.

Current prospective ledger: 25 legacy `veltrix-results-poisson-v1` forecasts; 0 PIT-certified, 0 quote-linked, 0 settled. These cannot count toward certification. The 25 separate latest-pre-match values have unknown source timestamps and are explicitly excluded. No new V2 forecast series is created in this provider review.

Value betting remains LOCKED. Production deployment, prediction publication, Telegram delivery, schedule activation and PR #120 merge remain disabled.

## Public references

- 5Dollar docs: https://5dollarfootballapi.com/docs
- 5Dollar pricing: https://5dollarfootballapi.com/pricing
- 5Dollar odds-history: https://5dollarfootballapi.com/docs/odds-history
- Odds-API.io historical odds: https://odds-api.io/historical-odds-api
- Odds-API.io pricing: https://odds-api.io/pricing
- SockOdds historical API: https://sockodds.com/docs/history/
- SockOdds league catalogue: https://sockodds.com/leagues/
- SockOdds pricing: https://sockodds.com/pricing/
- OddsIntel closes: https://data.oddsintel.app/football-closing-odds-api
- OddsIntel pricing: https://data.oddsintel.app/pricing
- OddsIntel beta terms: https://data.oddsintel.app/terms
- OddsPapi historical API: https://oddspapi.io/en/docs/get-historical-odds
- OddsPapi terms: https://oddspapi.io/en/legal/terms
- The Odds API historical coverage: https://the-odds-api.com/historical-odds-data/
- OddsRelay historical terms: https://oddsrelay.io/products/historical-odds
- OddsRelay terms: https://oddsrelay.io/terms
- TheRundown historical odds: https://therundown.io/historical-odds-api


## 7. Account entitlement read-back — 2026-11-15 23:31 WAT

Read-only query of `provider_entitlement_observations` found exactly one 5Dollar account observation: `plan_code=community`, `entitlement_status=ACTIVE`, seven approved competition IDs, `checked_at=2026-11-12T22:51:54.745Z`, `quota_remaining=299`. No Ultra entitlement observation exists. The last verified plan is therefore Community, not Ultra. Because the observation is dated 12 November, it is not proof of the live account state on 15 November; however, it is sufficient to keep the Ultra-only history route blocked. No plan change, payment or history request was made. A fresh entitlement check must be performed using an authorized no-credit account-status mechanism or provider confirmation before any Ultra route is called.


## 6. Fresh public-documentation re-audit — 2026-11-16

This re-audit used public provider documentation only. No provider account was created, no plan was changed, no API key was requested, and no historical endpoint was called.

### The Odds API — coverage is materially stronger than the earlier comparison recorded

The current historical-odds documentation confirms:
- featured-market historical snapshots from 6 June 2020, sampled every 10 minutes initially and every 5 minutes from September 2022;
- historical snapshots are available for all sports/bookmakers the provider covers, but the historical endpoint is paid-plan only;
- all seven required VELTRIX competition families appear in the historical coverage table, with these earliest dates:
  - England Premier League: 2020-06-06
  - Spain La Liga: 2020-06-06
  - Germany Bundesliga: 2020-06-06
  - Italy Serie A: 2020-06-06
  - France Ligue 1: 2020-07-16
  - Brazil Série A: 2020-07-28
  - Argentina Primera División: 2020-10-30
  - Brazil Série B: 2022-06-30
- The API's snapshot timestamp is an as-of time; bookmaker/market last_update timestamps must still be preserved and compared with scheduled kickoff. A closing proxy is the last valid pre-kickoff snapshot only when its age is within a predeclared maximum. It is not continuous tick history.

This makes The Odds API a strong historical-coverage candidate, not an admitted source. The prior live account test returned HTTP 401 on the historical endpoint with a paid-plan restriction. The existing source approval is still narrower than the seven-competition scope. No paid upgrade is authorized. Do not retry the restricted endpoint unless existing account entitlement and expanded rights are independently verified.

Public references:
- https://the-odds-api.com/historical-odds-data/
- https://the-odds-api.com/sports-odds-data/sports-apis.html

### Odds-API.io — possible no-upgrade per-event route, but bulk close remains paid

Current docs state:
- GET /v3/historical/odds returns a finished event's closing odds and final score and is described as available on every plan;
- GET /v3/historical/closing-lines is the bulk route, up to 366 days, 10 leagues, 30 bookmakers and 100 events per page, and is paid-plan only;
- closing odds coverage begins December 2025;
- new free API keys are paused; the published cheapest plan is Solo at £49/month;
- the documented response includes bookmaker-specific updatedAt timestamps.

This route is worth a no-purchase check only if VELTRIX already has a valid key. Repository search found no ODDS_API_IO_KEY / ODDSAPI_IO_KEY configuration, so there is no evidence that an existing key is available. The seven-league coverage list, bookmaker depth, exact Brazil Série B event availability and storage/model-training rights remain unverified. Do not purchase or create an account for this test.

Public reference: https://odds-api.io/historical-odds-api

### SockOdds — good recorded-tick semantics, still a scope failure

Current docs describe every observed price change with observed_at, opened/changed/withdrawn event type, opening/closing snapshots and graded results. History is Pro-only. Its documented archive begins 22 December 2025 for a small list and 8 October 2026 for other listed leagues. Its current league catalogue still does not establish Brazil Série A/B coverage; its docs explicitly caution that missing history means no recorded observation, not that the market never moved.

Disposition remains NOT APPROVED / NOT SUFFICIENT FOR THE SEVEN-COMPETITION BACKFILL.

Public reference: https://sockodds.com/use-cases/historical-odds-data-api/

### OddsIntel — still not bookmaker-specific evidence

OddsIntel exposes derived consensus closes, close timestamps, price age and source count, but deliberately omits bookmaker names and individual source prices. It cannot satisfy the bookmaker-specific close/CLV evidence contract. Its archive begins 10 October 2026. Do not use it as a substitute for source-level prices.

Public reference: https://data.oddsintel.app/football-closing-odds-api

### OddsRelay — archive too recent and commercial rights incompatible without Enterprise

The current docs say its historical archive begins 17 October 2026 and is appended daily; historical requests consume a shared token pool. Its public terms distinguish personal research from business use and require Enterprise for business/in-house use and publishing. The frozen historical universe predates the archive. No purchase or request.

Public references:
- https://oddsrelay.io/products/historical-odds
- https://oddsrelay.io/docs/reference

### iSports API — one-year opening/latest pre-match window and short in-play history

Current documentation describes a football odds-modification record with bookmaker/company IDs and an operateTime timestamp. It documents in-play history for the past month and opening/latest pre-match odds for up to one year, across 18 agencies; access requires the Odds or Odds Pro product. Exact seven-competition event coverage, timestamp semantics, rights and no-purchase entitlement are unverified. Keep as a prospective-only research candidate; no account or paid plan.

Public references:
- https://www.isportsapi.com/en/docs.html?id=245
- https://www.isportsapi.com/products/detail/football-api-product-53.html

### Updated ranking — no purchase and no source admission

1. 5Dollar Ultra remains the preferred direct tick-history path only if the current key is verified Ultra through the isolated status-only endpoint.
2. The Odds API is the strongest long-history coverage candidate across all seven required competitions, but the historical route is paid-only and the current key's 401 remains a hard block.
3. Odds-API.io is the best potential no-upgrade per-event candidate only if an existing valid key can be located; bulk closing lines remain paid and new free keys are paused.
4. OddsPapi remains technically promising but quota/rights constrained.
5. SockOdds has strong tick/settlement semantics but insufficient current Brazil competition scope.
6. AI Midas remains authorised for historical statistics and additional odds, not certified bookmaker-specific closing quotes or CLV.
7. OddsIntel is a consensus benchmark only; OddsRelay and iSports remain non-admitted due archive, licensing, pricing or coverage gaps.

**No provider is newly approved. No subscription, upgrade, API call, quota spend or data import resulted from this review.**


## 7. 5Dollar live entitlement result — 2026-11-16

A one-request status-only probe was executed in GitHub Actions run 43775297650. It called only GET /v1/status. The response was HTTP 200 and the exact plan field was community. The provider reported a 300/hour rate limit, a 20/minute burst limit, and no daily quota value. The response headers reported 299 remaining in the current hourly window.

The raw response and hashes were retained as a workflow artifact and persisted to staging:
- provider response ID: 1292
- entitlement observation ID: 5
- checked_at: 2026-11-15T23:33:27.239Z
- evidence SHA-256: 93dcca6cc11aa872e48b9651f0806b884ceff7d5c174152639ce6a382ab494b2

Result: COMMUNITY / ACTIVE; ULTRA NOT VERIFIED. The status-only probe made no league, fixture, odds or odds-history calls. The staging provider-response audit confirms zero 5Dollar odds-history requests. No upgrade was purchased or attempted.

### Prospective quote capture — current gate

The Odds API owner authorization remains active for the five approved European competitions and the provider sports catalogue previously confirmed all five sport keys. Its last no-cost /v4/sports probe (2026-11-15 13:21 UTC) recorded 295 credits remaining and 205 used. The account plan is undisclosed, monthly allowance is null and billing-period boundaries are NOT ESTABLISHED. Therefore the credit-reservation service has no valid monthly budget snapshot. Do not spend live odds credits until the billing period and hard caps are established and a budget snapshot is recorded.

The 788 existing 5Dollar observations remain timestamped OPENING quotes. They are not closing quotes and are not eligible for CLV. The dedicated odds_quote_observations relation is currently The Odds API-specific and contains zero rows. No new live odds snapshots were collected in this run.


### AI Midas temporal-evidence audit — 2026-11-16

AI Midas remains an authorised historical-statistics and additional-odds source under the user's approval, including the Brazil Série B identity work. The staging audit currently finds 14 dataset-asset observations (7 season-match CSVs, 6 historical-match CSVs, 1 advanced-team-match CSV), all first recorded by VELTRIX at 2026-11-15T19:41:43.265Z. Their source timestamp basis is unknown and their current point_in_time_certifiable flag is false. The identity reconciliation has 369 resolved fixture mappings and 20 resolved team mappings; it does not by itself certify time availability or bookmaker closing odds.

Disposition: retain and use the assets for authorised historical research, but do not silently promote them to PIT_CERTIFIED historical training features or bookmaker-specific closing-odds evidence. A separate prospective-only archive-as-of-import eligibility class could be evaluated for future fixtures, but it must remain distinct from historical walk-forward certification and must preserve the actual VELTRIX import timestamp. The current seven-forecast OpenPlay series does not consume AI Midas data.


### The Odds API historical quota economics

The current official V4 documentation specifies a historical sport-odds request cost of 10 credits per region per market; historical event-odds requests are also charged at 10 credits per region per market per event. Empty snapshots may return no data, but the historical endpoint remains paid-plan only. This makes a seven-competition, bookmaker-specific multi-market backfill expensive even before pagination and coverage gaps. The existing 295 live credits are not a historical entitlement and must not be spent on this route.

Public references:
- https://the-odds-api.com/historical-odds-data/
- https://the-odds-api.com/liveapi/guides/v4/
