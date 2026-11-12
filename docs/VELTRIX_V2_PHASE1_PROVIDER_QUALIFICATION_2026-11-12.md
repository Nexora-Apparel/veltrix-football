# VELTRIX FOOTBALL 2.0 — Phase 1 Provider Qualification

**Date:** 2026-11-12  
**Working branch:** `phase1/provider-final-qualification`  
**Phase status:** FINAL MANUAL VERIFICATION PENDING  
**Scope:** provider discovery, credential/endpoint access, competition coverage, data rights, historical depth, timestamps, and source selection.  
**Safety:** read-only qualification only. No production imports, database writes, model changes, prediction publication, Telegram delivery, deployment, or scheduling.

## 1. Phase 1 exit decision

The provider inventory is reconciled and a usable initial source stack is identified. Phase 1 is **not yet marked complete** because the consolidated final qualification workflow has not been manually dispatched against the current repository secrets. The workflow is on this branch and is designed to run once.

The project will not treat a successful HTTP response, an SDK licence, a public dataset label, or an API key as blanket data-use permission. Approval is scoped by provider, endpoint, data type, competition, season, retention, model training, public display, and commercial use.

## 2. Selected source stack

| Lane | Selected source | Decision | Limits / controls |
|---|---|---|---|
| Fixtures and results | 5DollarFootballAPI | Primary, account/competition scoped | Seven competitions were live-qualified; the exact plan is checked again by the final workflow. Preserve provider IDs and UTC kickoff values. |
| Odds and market benchmark | The Odds API | Approved supplemental benchmark | Current odds carry provider `last_update`; historical events/markets discovery is available on all plans at one credit per request but returns no prices. Historical odds snapshots require a paid plan and are charged by region/market. Do not substitute local retrieval time for provider quote time. |
| Historical shot events for xG research | Pappalardo et al. / Wyscout public event dataset | Approved under CC BY 4.0 with attribution | 1,941 matches across seven competitions; historical only. Train a VELTRIX-owned xG model; do not represent it as provider xG. |
| Non-live player, lineup and shot-event enrichment | StrikerAPI | Preferred conditional candidate; not currently available to ingest | Free allowance is 500 credits/month; the last recorded account response was HTTP 402. Do not buy credits or spend more until the free balance refreshes. Confirm the applicable Terms version for the account. |
| Supplemental odds | OddsPapi | Technical candidate; final live and historical quote check pending | API documents BTTS/totals and historical prices with per-price `createdAt` timestamps since January 2026. Its Terms prohibit raw-feed resale but do not expressly grant model-training, retention or commercial-display rights; keep excluded from model training/publication until clarified. |
| InferSports | Not selected | Discovery/odds adapter exists, but previous probes found no usable quotes | Keep disabled unless a future bounded probe returns actual price rows with timestamps. |

## 3. Verified 5DollarFootballAPI evidence

### 3.1 Credential and plan evidence

Run [#43268314432 — Standard vs Community credential comparison](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43268314432) completed successfully.

- Both `FIVEDOLLARFOOTBALL_API_KEY` and `FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY` authenticated.
- Both reported a rate-limit header of 300 requests/hour; remaining values were 289 and 286 at the time of the probe.
- Both returned seven competition rows on catalogue page 1, and the bounded history and fixture-odds checks returned `OK`.
- The 300/hour limit is consistent with Community Access, not the Free plan's 60/hour limit. The new Phase 1 workflow calls `GET /v1/status` directly to verify the plan rather than relying only on rate-limit inference.

Official Community Access documentation describes the top-five leagues plus one country pack, 300 requests/hour, 20 requests/minute, and 12 months of results/odds. See [Community Access](https://5dollarfootballapi.com/community), [pricing](https://5dollarfootballapi.com/pricing), and [changelog](https://5dollarfootballapi.com/docs/changelog).

### 3.2 Fixture qualification

Run [#43269388120 — seven-competition qualification](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43269388120) passed:

- 786 accepted historical fixtures across seven competitions.
- Brazil Serie A: 124; Brazil Serie B: 161; Italy Serie A: 110; France Ligue 1: 90; England Premier League: 100; Spain La Liga: 120; Germany Bundesliga I: 81.
- 12 requests used from a hard budget of 20.
- Zero invalid fixtures, duplicate fixture IDs, or missing team IDs.
- Window: 2026-08-14 through 2026-11-12.

This qualifies fixture retrieval and identity fields for the observed window. It does not establish full-season coverage or advanced-stat completeness.

### 3.3 Statistics endpoint qualification

Run [#43272673240 — statistics capability probe](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43272673240) passed:

- Seven of seven sampled competition statistics requests returned HTTP 200 and the expected field names.
- 15 requests used from a hard budget of 20.
- The probe selected only one finished fixture per competition.
- The probe checked field presence, not numeric completeness, range validity, match-to-match completeness, or full historical coverage.

The official endpoint is explicitly documented as **live match statistics**: attacks, dangerous attacks, shots on/off target, possession and first-half splits. It is not an xG, player-statistics, injury or confirmed-lineup feed. A successful finished-fixture sample is evidence that those seven records still returned a statistics block; it is not proof that the endpoint supplies a complete historical pre-match feature archive. See [official statistics documentation](https://5dollarfootballapi.com/docs/statistics).

### 3.4 Data rights and timestamp limits

The October 2026 Terms permit use in the customer's own commercial websites, apps, models and internal tools, including caching and end-user display. Free and Community public-facing products must visibly include linked attribution: **Football data by 5DollarFootballAPI**. Raw-feed resale or redistribution as a competing feed is prohibited. See [Terms](https://5dollarfootballapi.com/terms).

Community includes 12 months of Bet365 odds history with opening, closing and in-play prices, but the public plan matrix reserves full tick history for higher tiers. The fixture-odds response documents `opened_at` for 1X2 opening; it does not show a timestamp on every market's opening/closing object. Therefore, Community access alone does not prove the required 98% timestamped coverage for every selected market. The final Phase 1 probe samples one finished fixture per competition and counts timestamped market blocks. Preserve actual provider quote timestamps when present; never substitute local retrieval time. The dedicated `/v1/fixtures/{id}/odds/history` endpoint returns per-price `recorded_at` ticks but explicitly requires Ultra or above; Free and Pro receive HTTP 403. Community is not listed as an eligible tier, so the final probe makes one BTTS history request to verify the actual account response. The full per-price movement history is not assumed available on Community.

## 4. Other provider decisions

### The Odds API

The current Terms permit indefinite storage, commercial display, derived values, and training statistical/ML models, while prohibiting raw-feed resale. Historical odds are timestamped snapshots (10-minute intervals from June 2020, 5-minute intervals from September 2022) but the historical odds endpoint is paid-plan only. Historical events/markets discovery is available on all plans but does not return prices.

Decision: use as an independent odds benchmark and prospective quote source. The 1,000-match benchmark and value-bet gates remain blocked until sufficient approved timestamped odds are available. References: [Terms](https://the-odds-api.com/terms-and-conditions.html), [historical odds](https://the-odds-api.com/historical-odds-data/), [API guide](https://the-odds-api.com/liveapi/guides/v4/).

### StrikerAPI

The provider documents 17 competitions, 500 free credits per month, daily refreshed match data and odds refreshed hourly for upcoming matches. It has no in-play/live match feed, which is aligned with VELTRIX's non-live analysis requirement. Its endpoints cover fixtures/results, lineups, box scores, events and shot locations. The provider's own xG is not point-in-time safe; if later approved, use raw shot locations to train a separate VELTRIX xG model.

The provider's published terms permit storage, research, backtesting, proprietary model training and commercial derived outputs while the account is open, and prohibit raw-feed resale. The provider does not publish a per-dataset upstream source list and does not grant league/club/player marks. The applicable Terms version also depends on when the account was created. Last recorded VELTRIX account response: HTTP 402 (monthly credits exhausted). The Phase 1 workflow deliberately does not call StrikerAPI or consume credits.

Decision: keep it as the preferred conditional enrichment source; do not ingest until the free balance is available and account Terms version/source-use conditions are documented. References: [official documentation](https://strikerapi.com/docs), [timing and rights](https://strikerapi.com/docs/timing-and-rights), [terms](https://strikerapi.com/terms).

### GOAL API

The 2026-11-11 bounded read-only probe passed for Argentina Liga Profesional and Brazil Serie A fixtures/results using Bearer authentication. This verifies technical access only. The provider's Terms do not grant the underlying sports-data IP rights and place third-party rights clearance on the customer.

Decision: preserve the credential, but exclude GOAL API from V2 training, persistent history and public display until upstream rights and permitted uses are documented. References: [documentation](https://goal-api.com/documentation), [Terms](https://goal-api.com/terms).

### Wyscout public event dataset

The Pappalardo et al. public dataset contains approximately 1,941 matches and 3.25 million events across five European first divisions, the 2018 World Cup and Euro 2016. The paper identifies CC BY 4.0 licensing. This is a viable historical shot-event source for training a VELTRIX-owned xG model with required attribution and change notices; it is not a current-season feed. Reference: [Scientific Data paper](https://www.nature.com/articles/s41597-019-0247-7).

### OpenPlay

The v0.1.0 release reports 26,536 in-scope matches, 41.6 million events and 669,404 shots with xG, plus player-match statistics and lineups. It declares CC BY 4.0, but its upstream WhoScored/Opta/Stats Perform lineage is not independently established. Keep it quarantined from production training and display pending upstream rights confirmation. Reference: [OpenPlay release](https://github.com/nlbair/openplay/releases).

### Excluded / not selected sources

- **PitchAPI:** technical candidate; service-data rights, upstream lineage, storage and training permission not verified. No ingestion.
- **StatsBomb Open Data:** research-only under its published agreement; no blanket commercial training approval.
- **OpenFootball:** supplemental fixtures/results only. Prior 90-day EPL comparison had 45/100 exact score matches, six date conflicts and 49 missing scores; not accepted as primary results.
- **OpenMatchday:** repository states non-commercial use; excluded from commercial training/publication.
- **Football-Data.co.uk:** personal/academic-use restrictions; excluded from commercial model training.
- **OpenFootAPI:** source-specific upstream licence controls; top-five samples were labelled FotMob Unlicensed-Beta, so not approved for those competitions.
- **FPL public API:** excluded after terms review.
- **API-Football/API-Sports:** do not depend on it; prior key suspensions.
- **Highlightly:** excluded due limited coverage and rate-limit failures.
- **InferSports:** previous bounded probes did not return usable quotes; not selected.
- **Club-Football-Match-Data:** do not admit into the training corpus until the exact upstream data rights and per-source licence are cleared.

## 5. Known data gaps

No currently approved source provides the full current-season combination of xG, confirmed lineups, player-level statistics, injuries, PPDA, shot conversion and travel/rest context across all seven qualified competitions.

- 5Dollar covers fixtures/results and selected match/odds fields, but does not claim xG, injuries, transfers, player profiles or player-level statistics.
- The Wyscout event dataset is historical (2017/18, World Cup 2018, Euro 2016).
- StrikerAPI is the intended non-live enrichment candidate, but its account credits are exhausted and its applicable Terms version must be confirmed.
- The Odds API historical price archive requires a paid plan. Until adequate timestamped prices are available, bookmaker benchmark and value-bet certification remain incomplete.
- Missing data must remain explicitly missing. Do not infer xG from odds, call a predicted lineup confirmed, or fabricate fatigue/travel values.

## 6. Consolidated final qualification workflow

The branch updates the existing `Multi-Source Provider Verification` workflow and adds:

- a read-only 5Dollar `/status` + `/leagues` plan/country-pack check, plus at most one finished-fixture odds/timestamp sample per competition and one BTTS tick-history entitlement check (17-request cap, 4-second pacing);
- a sanitized OddsPapi soccer-market/quote probe;
- the existing bounded The Odds API / InferSports integration checks;
- the existing GOAL API read-only probe when its secret exists;
- a machine-readable, SHA-256-checked provider report artifact;
- an explicit StrikerAPI credit-safe deferral (zero requests).

Workflow dispatch is manual only. It does not write to the database, import historical data, train models, change predictions, publish command data, send Telegram messages, deploy Vercel, or schedule jobs.

## 7. Phase 1 acceptance gates

Phase 1 can be marked complete only after:

1. The consolidated workflow passes its offline test suite.
2. The manual run verifies the 5Dollar account plan and competition catalogue.
3. The manual run captures current provider-authentication and market-quote results without leaking credentials.
4. The provider matrix above is committed as the controlling source register, including explicit exclusions and known gaps.
5. No unapproved source is admitted into the production training corpus.

The next phase is the historical data foundation. It must not begin until these Phase 1 gates are verified. No production deployment, Telegram activation or schedule is authorized by Phase 1 completion.
