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
