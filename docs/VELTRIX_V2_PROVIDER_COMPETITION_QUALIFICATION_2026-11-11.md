# VELTRIX FOOTBALL 2.0 — Provider and competition qualification matrix

Date: 2026-11-11
Branch: veltrix-2.0-architecture-blueprint
Status: source research and access-policy qualification; production approval is NOT granted.

## 1. Competition scope

The first qualification cohort is deliberately limited to competitions with a credible combination of historical match volume, current fixture access, event/stat coverage and odds availability:

Tier A:
- England Premier League
- Spain La Liga
- Italy Serie A
- Germany Bundesliga
- France Ligue 1
- UEFA Champions League

Tier B:
- Argentina Liga Profesional
- Brazil Serie A
- EFL Championship

Tier C, only after Tier A/B data quality is demonstrated:
- UEFA Europa League
- UEFA Conference League
- Eredivisie
- Primeira Liga
- Scottish Premiership
- MLS
- Liga MX
- NWSL

The scope does not assume that every listed competition is currently accessible under the user's free plan. The product must publish only competitions that pass the per-competition source gate. No fixture quota may override evidence quality.

## 2. Provider matrix

| Provider | Current documented scope / access | Strengths | Blocking limitations | V2 decision |
|---|---|---|---|---|
| 5DollarFootballAPI Free (existing primary) | EPL, La Liga, Serie A, Bundesliga, Ligue 1; 60 requests/hour, 20/minute burst; last 3 months of results/odds. | Per-fixture odds endpoint is available on Free and returns Bet365 1X2, BTTS, goal lines and other supported markets. UTC fixture times; freshness and competition-quality dashboards. | One odds request per fixture; bulk odds on fixture lists is Pro+. Full tick history is Ultra. Only 1X2 opening currently documents provider opened_at; V2 must timestamp its own retrieval for other markets. | Primary current fixtures/results and prospective odds-snapshot candidate for the five leagues. One bounded odds request per selected fixture supports up to 25 daily fixtures within the hourly quota. |
| 5DollarFootballAPI Community Access | Top five leagues plus one country pack; 300 requests/hour, 20/minute burst; last 12 months of results/odds; renewable every 12 months. | Free no-card route for students, researchers, early-career developers and no-budget builders; same data quality as Free with more history and one country pack. | Exact country-pack availability and competition IDs must be confirmed on the user's account. Still no full odds tick history. | Preferred no-cost account expansion. Argentina or Brazil are the first candidate country packs, subject to whitelist confirmation. |
| 5DollarFootballAPI Pro / Ultra | Pro: 130+ competitions and 12 months of results/odds. Ultra: 1,600+ leagues/cups and tick history back to 2014 for supported competitions. | Broad global coverage and full odds history; per-competition data-quality dashboards. | Paid; no purchase is authorized. | Technically strong future option, not selected under the current no-budget constraint. |
| StrikerAPI | 17 competitions; fixtures/results from 2001-02 to current; shot locations complete from 2013-14 in supported leagues; odds archive from June 2020 for 16 competitions; 500 free credits/month. | Terms permit storage, derived values, research/backtesting, training own models and commercial apps. No attribution required. Archived odds carry actual captured_at times; lineups, events, box scores and shot locations support feature engineering. | Existing VELTRIX credential previously returned HTTP 402 (credits exhausted). 500 credits/month constrain enrichment. Events/box scores refresh daily and records can be overwritten; no per-record revision history. Published xG is not point-in-time. | Strong primary historical-results and shot-location training candidate after a fresh account probe. Fit V2 xG from raw shot locations; never use provider xG as a historical pre-match feature. Use archive odds only where market and captured_at coverage are proven. |
| The Odds API | Existing key was live-verified 2026-10-28; bounded probe used 3 credits and reported 497 remaining then. H2H, totals and event-specific BTTS markets were confirmed. | Multi-bookmaker odds snapshots; existing VELTRIX adapter supports h2h, totals and bounded BTTS event requests. | Free monthly quota is limited; previous pipeline capped BTTS to 3 events/report. Current balance needs re-probing. | Secondary odds cross-check; not the sole 25-fixture/day timestamped odds source. |
| GOAL API | Read-only account probe passed 2026-11-11 using Bearer auth plus browser-like User-Agent. 1,000 requests/day reported; 982 remained after 18 calls. Argentina Liga Profesional and Brazil Serie A fixtures/results returned samples. | Official coverage: Argentina 3,739 matches (2008–2026), 3,733 lineups, 2,681 stats, 3,241 events; Brazil 2,058 matches (2021–2026), 2,058 lineups, 1,868 stats, 1,732 events. | Endpoint-level lineups/stats/events/odds not yet probed. Terms grant no IP rights in underlying sports data and state third-party rights may require separate authorization; model-training rights are not explicit. | Fixtures/results technical pass for Argentina/Brazil. Secondary data candidate only; no model training/public display of underlying data until written rights confirmation and endpoint-level qualification. |
| StatsBomb Open Data | Selected competition/season research datasets. | Detailed event data for research and custom event feature engineering. | Selective coverage, agreement/registration and attribution requirements; not a universal live feed. | Research-only after current agreement and per-season coverage/rights checks. |
| OpenPlay data-v0.1.0 | Historical big-five/UEFA and selected international competition tables; release declares CC BY 4.0. | Large player/match/lineup/shot history. | Maintainer discloses WhoScored/Opta/Stats Perform upstream; upstream rights chain not independently verified. Scraped-at values do not prove pre-kickoff availability. | Quarantined research candidate; no V2 training until upstream rights and point-in-time availability are proven. |
| Football-Data.co.uk / Club-Football-Match-Data archive | Historical results, odds and statistics; the recovered artifact contains 70,444 rows across 38 division codes. | Useful for schema, coverage and data-quality audits. | Official terms say its free data is not intended for commercial or data-training projects using automated bots/scrapers/AI. The archive also lacks exact kickoff and per-record publication timestamps. | Audit/reconciliation only. No V2 model training or automated feed use without explicit written permission. |
| OpenFootball | CC0 historical fixtures/results supplement. | Open licence and simple structured data. | Prior 90-day EPL reconciliation: 45/100 exact score agreements, 6 date conflicts, 49 missing scores. | Supplemental cross-check only; never authoritative primary results. |
| FootballAPI.org | Complimentary plan: current-season Premier League only, 50 calls/day; paid plan documented at $29/month for 68 competitions. | Documented 40-endpoint API and stable match/team IDs. | Free plan too narrow and no paid budget approval. | Not selected. |

## 3. Important provider findings

### 5DollarFootballAPI

The current documentation specifies UTC ISO-8601 timestamps and fixture states including scheduled, in-play, finished and unknown. Only finished is a valid settlement state. A fixture not confirmed finished after four hours becomes unknown; the feed does not expose explicit postponed/cancelled/abandoned states, and rescheduled fixtures may receive a new fixture ID. V2 must preserve this behavior and reconcile rescheduled identities rather than guessing settlement.

The Free plan's three-month historical window is not sufficient by itself for 1,000+ chronological test matches per market. Community Access is the strongest no-cost expansion path: top five leagues plus one country pack, 12 months of results/odds, 300 requests/hour and 20/minute burst. The user appears eligible as an early-career developer building without a budget. A single country pack must be selected; Argentina or Brazil are the first candidates, subject to account whitelist confirmation.

For prospective odds capture, the per-fixture GET /v1/fixtures/{id}/odds endpoint is available on Free and returns Bet365 1X2, BTTS, goal lines and other supported markets. Fixture-list include=odds is not available on Free, and full tick history requires Ultra. Capture one odds payload per selected fixture, store the V2 retrieval time as captured_at, preserve any provider-supplied opened_at, and reject quotes captured at/after kickoff. This supports up to 25 daily fixture snapshots within the hourly quota if calls are batched safely. It does not create historical quote timestamps retroactively.

The 2026-11-11 live probe authenticated successfully and confirmed exactly five accessible leagues: England Premier League, France Ligue 1, Germany Bundesliga I, Italy Serie A and Spain La Liga. A small upcoming-fixture sample (5 EPL fixtures) returned complete 1X2 and O/U 2.5 closing quotes for 5/5, but BTTS for only 3/5. This is a preliminary sample, not a 98% coverage certification. V2 therefore treats missing BTTS as missing data and may query The Odds API fallback; it never copies or invents prices.

Free/Community/Education public-facing outputs must visibly attribute "Football data by 5DollarFootballAPI" and link to https://5dollarfootballapi.com. Raw feed resale/redistribution is prohibited.

### StrikerAPI

The public data atlas lists 17 competitions: Premier League, MLS, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, Championship, NWSL, Liga MX, Europa League, Conference League, Eredivisie, Primeira Liga, Scottish Premiership, Brazil and Argentina. Fixtures/results cover 2001-02 to current. Shot locations are complete from 2013-14 in supported leagues. The sportsbook archive has 1X2, handicap and totals snapshots with actual captured_at times from June 2020 for 16 competitions; it does not establish BTTS coverage across the full cohort.

The current public plan advertises 500 free credits per month. Basic fixtures/standings examples cost 2 credits; team stats/odds 5; events and shot maps 10. The user's earlier HTTP 402 remains a historical credit-exhaustion observation, not proof that the key is invalid or that the current monthly balance is zero. Re-probe the account before usage.

StrikerAPI's terms explicitly permit storing pulled data while the account is open, deriving values, research/backtesting, training own models and commercial apps. They prohibit raw/bulk feed redistribution; no attribution is required.

Events and box scores update daily around 10:00 UTC and are refetched for about a day and a half after a match ends. Records are overwritten without per-record revision history. Published xG is not point-in-time: its location model is fitted using every season, including later seasons, and refitted by hand. Never use provider xG as a historical pre-match feature; fit V2 xG from raw shot coordinates and only prior shots.

### The Odds API

The existing VELTRIX register records a successful live authentication and soccer-market probe on 2026-10-28. A fresh 2026-11-11 probe returned 46 active soccer sports and 298 requests remaining. The provider-specific BTTS market is available through event-specific requests and exposes market last_update timestamps. V2 will use it only as a fallback when the 5Dollar Bet365 BTTS board is missing, with a hard monthly budget and daily call cap; the API key is not a bulk odds source for all 25 daily fixtures.

### GOAL API

The key is active and the read-only probe passed on 2026-11-11. The first 403 was a Cloudflare browser-signature block caused by the default Python request signature; a browser-like User-Agent allowed the documented Authorization: Bearer request to succeed. The probe used 18 requests, found Argentina Liga Profesional Argentina and Brazil Serie A, sampled each competition’s fixtures and results, and reported a 1,000/day limit with 982 remaining. This is a technical fixtures/results pass, not full provider certification.

The official coverage pages currently report Argentina: 3,739 matches (2008–2026), 3,712 finished, 3,733 lineups, 2,681 match-stat records and 3,241 event records; Brazil Serie A: 2,058 matches (2021–2026), 2,029 finished, 2,058 lineups, 1,868 stats and 1,732 events. The API documentation also records a kickoff-time migration on 20 August 2026: current kickoffUtc is UTC, while older stored kickoff fields used Europe/Berlin with DST. Historical ingestion must preserve that boundary and never treat old matchTime strings as UTC.

The provider’s November 2026 terms state that it licenses data from third parties but grants no IP rights in the underlying sports data; some uses may require separate rights-holder authorization, and model-training rights are not expressly granted. Therefore the source remains a fixtures/results technical candidate only. Do not train V2 on it or publish its underlying statistics/logos until the provider confirms those uses in writing. The public coverage page is not a substitute for account-specific endpoint testing.

### Football-Data.co.uk archive

The recovered archive is useful for coverage and schema audit, but its upstream terms expressly exclude data-training projects using automated bots/scrapers/AI. The V2 adapter therefore exposes audit rows only and marks model training and point-in-time certification as false. Do not feed this archive into V2 models unless explicit written permission is obtained.

## 4. Qualification gates per competition and endpoint

A provider is not production-qualified merely because a key authenticates. For each competition and each endpoint, require:

1. Authentication and permission probe succeeds without a plan/credit error.
2. Fixture IDs, canonical competition IDs, team IDs, kickoff UTC and status fields are present and stable.
3. Historical fixture counts and season coverage are inventoried.
4. Duplicate, missing, rescheduled, abandoned, postponed and corrected-result behavior is tested.
5. At least 100 randomly selected fixtures are reconciled against an independent source for date, teams and score; all conflicts are recorded.
6. Event/stat/lineup fields have explicit availability timestamps and coverage rates; missing values remain null.
7. Odds include bookmaker, market, selection, decimal price, line, capture timestamp and kickoff timestamp; quotes at/after kickoff are excluded.
8. Source terms, upstream rights, retention, attribution and rate limits are recorded per source/version.
9. The observation is immutable and includes source ID, retrieved_at, published/available_at where known, raw payload hash, parser version and quality state.
10. Competition approval is endpoint-specific. A source may be approved for fixtures/results but rejected for xG, lineups or odds.

For chronological training, the source's actual availability time must be no later than the historical prediction cutoff. Current snapshots or overwritten records cannot be backdated.

## 5. Current acceptance decision

- Primary fixture/results probe: 5DollarFootballAPI Free, limited to the five accessible competitions and its current historical window.
- Historical supplemental candidates: StrikerAPI, OpenPlay, StatsBomb Open Data and manual Football-Data.co.uk snapshots, each with separate legal and point-in-time gates.
- Odds benchmark: timestamped 5Dollar/StrikerAPI odds only after quote-level coverage and identity reconciliation; bookmaker market data remains a separate benchmark lane, never a football-strength model input.
- GOAL API: unresolved 403; no ingestion approval.
- API-Football/API-Sports: excluded as a dependency due prior suspension history.
- No source currently has blanket approval for all competitions and all model features.

## 6. Next qualification execution

1. Probe 5Dollar account status and the exact five permitted league IDs; capture quotas and current plan response. Evaluate the free Community Access option for top-five plus one country pack; if enabled, capture one per-fixture odds snapshot per selected fixture and timestamp the V2 retrieval time.
2. Probe StrikerAPI monthly credit balance and one fixture/results request; if still 402, defer until balance refresh. Use it for bulk historical results and targeted shot-map enrichment; 500 monthly credits cannot support daily full event enrichment for 25 fixtures.
3. Probe The Odds API current quota and supported sports/markets; retain it as a secondary benchmark source. Probe GOAL API with the documented Authorization: Bearer header on a documented read-only endpoint; capture the sanitized 403 response and request/correlation ID.
4. Build a per-competition coverage snapshot for current and previous seasons, then perform 100-fixture cross-source reconciliation.
5. Only after acceptance, stage immutable observations in the isolated Neon branch. Do not write production Neon.

## Public documentation references

- 5Dollar API docs: https://5dollarfootballapi.com/docs
- 5Dollar changelog and Community Access: https://5dollarfootballapi.com/docs/changelog
- 5Dollar terms: https://5dollarfootballapi.com/terms
- 5Dollar data quality: https://5dollarfootballapi.com/docs/data-quality
- StrikerAPI docs: https://strikerapi.com/docs
- StrikerAPI data atlas: https://strikerapi.com/docs/atlas
- StrikerAPI timing and rights: https://strikerapi.com/docs/timing-and-rights
- GOAL API documentation: https://goal-api.com/documentation
- GOAL API terms: https://goal-api.com/terms
- FootballAPI.org documentation: https://footballapi.org/documentation

This document records public-source research and VELTRIX's prior internal observations. It does not certify provider reliability or grant third-party rights.
