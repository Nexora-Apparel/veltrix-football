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
| 5DollarFootballAPI Free (user's existing primary) | Five major European leagues; 60 requests/hour and 20/minute; last 3 months of historical results/odds. Upcoming/live data is available across plans. | Read-only API; UTC timestamps; fixture/result status contract; current freshness/status and per-league data-quality dashboards; Bet365 odds; event/stat/odds endpoints. | Three months is insufficient by itself for 1,000+ historical evaluations per market. Free tier does not grant the broad competition scope. Public-facing $0-plan use requires attribution. | Primary current fixtures/results candidate for the five accessible leagues, subject to exact API probes, completeness and reconciliation. Not the sole historical training source. |
| 5DollarFootballAPI Community Access | Top five European leagues plus one selected country's whitelisted leagues; 12 months of results/odds; 300 requests/hour and 20/minute. | Broader country-specific coverage without a paid plan; more history and quota than Free. | Country pack availability and exact competition IDs must be confirmed on the account. Twelve months still does not independently establish 1,000+ chronological test rows for every market. | Optional qualification route. No account-plan change is assumed or performed. |
| 5DollarFootballAPI Pro / Ultra | Pro documented as 137 competitions and 12 months; Ultra broader historical access back to 2014 and wider competition coverage. | Broad coverage, measured quality dashboards, deeper historical access, odds/event/stat endpoints. | Paid; no purchase is authorized. Per-competition completeness and endpoint entitlements still need testing. | Technically strong candidate; blocked pending budget authorization and data-quality tests. |
| StrikerAPI | 17 competitions; public docs list 500 free credits/month, with per-call costs: fixtures 2, stats/odds 5, events 10. | Long historical coverage; lineups, box scores, event and shot-location data; odds archives; broad Tier A/B/C league coverage. | Existing VELTRIX credential previously returned HTTP 402 (credits exhausted). No record-level revision history. Events/box scores refresh daily. Published xG is not point-in-time: its model is fitted across seasons including later seasons and may be refitted. Upstream source list is not published. | Secondary research and cross-check candidate. Do not use its published xG as a leakage-safe historical feature; use raw shot locations to fit V2 xG. Re-probe the existing account before ingestion. |
| GOAL API | User confirms GOAL_API_KEY is active; prior request returned 403. Current official docs for api.goal-api.com specify Authorization: Bearer authentication, matching the existing probe. | Potential additional fixture/match data source; public site advertises 1,000+ competitions, fixtures/results, lineups, statistics, events and odds. | Prior 403 remains unexplained. Current docs list 401, 429 and 500 but do not explain 403; coverage depth, free-plan quota and historical completeness still need account-level probes. | Blocked until a bounded read-only probe succeeds. Investigate key scope/plan, endpoint path, account restrictions and full sanitized response; do not change to X-AUTH-APIKEY or label the key invalid. |
| StatsBomb Open Data | Selected competition/season research datasets. | Detailed event data and useful event-level research. | Selective coverage, user-agreement/registration and attribution requirements; not a universal live feed. | Research-only adapter source after current agreement and per-season rights/coverage checks. |
| OpenPlay data-v0.1.0 | Historical big-five/UEFA and selected international competition tables; release declares CC BY 4.0. | Large player/match/lineup/shot history and useful technical coverage. | Maintainer discloses WhoScored/Opta/Stats Perform upstream; upstream rights chain is not independently verified. Scraped-at values do not prove pre-kickoff availability. | Quarantined historical research candidate. No production training until upstream rights and point-in-time availability are proven. |
| Football-Data.co.uk | Historical results and odds snapshots for selected competitions. | Useful supplementary historical results/odds. | Personal/academic-use restrictions; manual or light automated use no more than twice weekly; cannot be a high-frequency automated feed. | User-downloaded/manual snapshot path only, with source capture timestamp and licence metadata. |
| OpenFootball | CC0 historical fixtures/results supplement. | Open licence and simple structured data. | Prior 90-day EPL reconciliation: 45/100 exact score agreements, 6 date conflicts, 49 missing scores. | Supplemental cross-check only; never authoritative primary results. |
| FootballAPI.org | Complimentary plan: current-season Premier League only, 50 calls/day; paid plan documented at $29/month for 68 competitions. | Documented 40-endpoint API and stable match/team IDs. | Free plan too narrow for VELTRIX target and no budget approval for paid plan. | Not selected for current architecture. |

## 3. Important provider findings

### 5DollarFootballAPI

The current public documentation says all timestamps are UTC ISO-8601. It distinguishes scheduled, in-play, finished and unknown fixtures; only finished is a valid settlement state. A fixture that has not been confirmed finished after four hours becomes unknown, with a reason distinguishing unconfirmed kickoff from unconfirmed result. The feed does not expose explicit postponed/cancelled/abandoned states; rescheduled fixtures may receive a new fixture ID. V2 must preserve this behavior and reconcile rescheduled identities rather than guessing a settlement.

The Free plan's 3-month historical window means it cannot by itself provide the requested 1,000+ chronological evaluation rows per market. Do not misrepresent current/upcoming feed access as deep historical coverage.

Free/Community/Education public-facing output must visibly attribute: "Football data by 5DollarFootballAPI" and link to https://5dollarfootballapi.com. Raw data feed resale/redistribution is prohibited.

### StrikerAPI

The public docs now advertise 500 free credits every month. The user's earlier HTTP 402 remains a valid historical account observation and means the prior request was credit-blocked; it does not prove the current monthly balance. A read-only account probe is needed before any planned usage.

StrikerAPI's public docs describe fixtures/results and lineups from 2001-02 for the big-five and Champions League, and 17 competitions overall. Calls cost credits: fixtures and results 2, team stats/odds 5, events 10. Therefore, the free allocation can support limited targeted checks, not broad daily event-level enrichment across 25 fixtures. No paid plan is assumed.

Its published xG is explicitly not point-in-time: the provider says its location model is fitted using every season, including later seasons, and can be refitted. It must not be used as an historical pre-match feature. If shot coordinates are obtained, train and freeze a separate V2 xG model using only shots available before each evaluation cutoff. The provider also states it does not retain record-level revision history; preserve VELTRIX's own immutable observation snapshots.

### GOAL API

The user confirms the key is active. The existing VELTRIX probe targets `https://api.goal-api.com/v1` and sends `Authorization: Bearer ...`, which matches the current official documentation. A different project named GoalAPI.com uses a different hostname and an `X-AUTH-APIKEY` header; do not conflate those products or change the VELTRIX header based on the unrelated documentation.

The prior 403 therefore remains unexplained and should be investigated through account/key scope, endpoint permission, request path, plan entitlements, provider-side restrictions and the complete sanitized error body/request ID. The current GOAL API documentation lists 401 for missing/invalid key, 429 for rate limits/plan quota and 500 for server errors but does not document 403. Public pages advertise 1,000+ competitions, but per-competition endpoint coverage, free quota and historical completeness must be verified against the account and sample data.

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

1. Probe 5Dollar account status and the exact five permitted league IDs; capture quotas and current plan response.
2. Probe StrikerAPI monthly credit balance and one fixture/results request; if still 402, defer until balance refresh.
3. Probe GOAL API with the documented Authorization: Bearer header on a documented read-only endpoint; capture the sanitized 403 response and request/correlation ID.
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
