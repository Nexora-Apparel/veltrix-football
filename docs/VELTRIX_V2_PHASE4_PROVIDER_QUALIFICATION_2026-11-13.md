# VELTRIX FOOTBALL 2.0 — Phase 4 Provider Qualification Register

**Assessment date:** 2026-11-13  
**Branch:** `phase4/provider-qualification-20261113`  
**Purpose:** qualify independent, rights-approved, point-in-time feature sources before any new prediction-engine implementation.

## 1. Governing rule

Phase 1's merged provider qualification is the authoritative baseline. This Phase 4 register extends it; it does not silently reverse prior decisions. Every provider is scoped by endpoint, competition, season, data type, retention, model training, display and commercial use.

A provider is not approved by a successful HTTP response or a marketing claim. Each observation must retain exact raw response bytes and SHA-256, provider/product/endpoint identity, redacted request parameters, HTTP status, retrieval timestamp, source event/publication timestamp where supplied, stable entity identifiers, rights evidence and immutable revision history.

A pre-match feature is eligible only when source availability is provably no later than the frozen prediction cutoff. Post-match xG, shots, lineups and other statistics are retrospective descriptors/labels, not pre-match features. Missing timestamps cannot be repaired by inference or current web pages.

## 2. Existing authoritative source decisions

| Data lane | Existing decision | Verified limitations |
|---|---|---|
| Fixtures/results | 5DollarFootballAPI Community — qualified primary for the seven observed competitions | Account reports 300 requests/hour and 20/minute burst. The seven qualified competitions are Brazil Serie A, Brazil Serie B, Italy Serie A, France Ligue 1, England Premier League, Spain La Liga and Germany Bundesliga I. The 786-fixture qualification covered 2026-08-14 to 2026-11-12, not complete historical seasons. Later staging import has 2,496 traceable settled-result labels, not point-in-time feature snapshots. |
| Prospective odds / bookmaker benchmark | The Odds API — approved supplemental source | Current odds response has provider `last_update`; historical odds are paid-plan snapshots (10-minute cadence from June 2020, 5-minute cadence since September 2022). Historical event/market discovery on free plans returns no prices. The source is selected for prospective timestamped capture, but 98% timestamp coverage has not been achieved. |
| Historical shot events / xG research | Pappalardo et al. / Wyscout public event dataset — approved under CC BY 4.0 with attribution | Approximately 1,941 matches across seven competitions. Historical research data only, not a current-season feed. Train a VELTRIX-owned xG model from raw shot events; do not present it as provider-supplied xG. |
| Non-live enrichment | No active provider selected; StrikerAPI is conditional future candidate | The VELTRIX account's last recorded check returned HTTP 402 with zero credits. Do not buy credits. Reconsider only after free-credit refresh, a successful bounded probe and accepted Terms-version verification. |
| OddsPapi | Excluded pending explicit rights clarification | Terms do not expressly grant model-training, retention or commercial-display rights. A local script issue was corrected, but this does not change the rights decision. |
| InferSports | Supplemental live-odds discovery candidate only | Bounded probe returned 63 same-day events and 1X2/totals. No BTTS, historical archive or source-created quote timestamps were verified. Not a historical benchmark or value-bet source. |
| GOAL API | Excluded from V2 training, persistent history and public display pending rights clearance | Latest HTTP 403 was a Cloudflare browser-signature block, not proof of an invalid key. Underlying sports-data rights remain unresolved. |

The seven 5Dollar competitions were measured in the prior qualification: Brazil Serie A 124, Brazil Serie B 161, Italy Serie A 110, France Ligue 1 90, England Premier League 100, Spain La Liga 120 and Germany Bundesliga I 81 fixtures in the bounded qualification window. Do not mistake those counts for full-season completeness.

The 5Dollar Community sample returned 77 market blocks across seven finished fixtures, but only 7/77 (9.09%) contained a market timestamp. BTTS tick-history returned HTTP 403. The Community account therefore does not meet the 98% timestamped-odds gate. Its 4-day availability proxy in the Phase 3 import is not a publication timestamp.

## 3. New provider candidates — not approved

| Provider | Potential role | Public documentation evidence | Qualification blockers | Status |
|---|---|---|---|---|
| Sportmonks Football API | Structured team/player stats, lineups, injuries, xG and fixture metadata | Public plans list €29/month for five leagues, €99 for 30 and €249 for 120. Historical data older than three seasons is a one-time add-on from €29 for non-Enterprise plans. xG is an add-on; public FAQ says xG starts from 2024. | Exact seven-competition coverage, historical depth per field, publication timestamps, revision behavior and rights for storage/model training/display are unverified. Post-match xG is not a pre-match feature. Obtain sample/coverage export and written terms before any subscription. | Candidate — docs reviewed; not approved |
| Goalserve | Historical results, team/player stats, lineups/injuries and odds | Public pricing lists Soccer Live Stats from $200/month, Fixtures/Results from $150/month, Pregame Odds from $250/month and Full Stats from $300/month. Provider advertises results back to 2006 and more detailed player/team stats from 2016. | Exact seven-competition completeness, source publication timestamps, xG coverage, historical odds granularity, revision behavior and rights are unverified. Price is material; request written quote and sample export before spend. | Candidate — docs reviewed; not approved |
| football-data.org | Fixture/result and basic match-stat supplement | Public pricing lists €29/month ML Pack Light with ten seasons of history; €29/month Free + Deep Data with lineups/subs; €49 Standard for 30 competitions; odds and statistics add-ons are separately priced. Season-specific match retrieval is documented. | Exact coverage of the seven competitions and data-use rights need confirmation. No xG feed is documented in the reviewed plan matrix. Historical records do not prove as-of publication time. | Conditional candidate for basic data; not approved |

### StrikerAPI — previously evaluated; do not re-probe or spend

Phase 1's detailed review found relevant non-live endpoints: team stats (goals, xG, shots, possession), match/player lines, lineups, shot events/maps and sportsbook odds movement. Coverage is non-uniform by league and season; full shot events begin in 2012-13, shot locations are documented as complete from 2013-14, and odds archives are partial by season/bookmaker. The provider's own xG model is not point-in-time safe because it is fitted across seasons; VELTRIX would need to build its own xG model from eligible raw shot locations.

The account returned HTTP 402 with zero credits. Its current Terms version also needs confirmation against the account's accepted version and upstream source restrictions. The Phase 1 workflow already protects the account: one static free-credit check first, and no feature probe if it returns 402. Do not top up or repeat paid requests.

Decision: technically promising but currently excluded from ingestion. Reconsider only if the account's free balance refreshes and the accepted rights version is confirmed.

## 4. Historical dataset rights and quarantine

- **Wyscout / Pappalardo et al.:** approved historical research dataset under CC BY 4.0 with attribution and change notices. Use raw shot events to train a VELTRIX-owned xG model. Its 1,941-match, seven-competition scope is historical and does not provide current-season features.
- **OpenPlay:** repository reports 26,536 matches, 41.6 million events and 669,404 shots with xG under CC BY 4.0. However, upstream WhoScored/Opta/Stats Perform lineage is not independently established. Keep quarantined from production training and display until upstream rights are confirmed.
- **StatsBomb Open Data:** research-only under its published agreement; no blanket commercial training approval.
- **OpenFootball:** supplemental fixtures/results only; prior comparison had poor exact-score/date agreement. Not accepted as primary results.
- **OpenMatchday** and **Football-Data.co.uk:** excluded from commercial training/publication due their stated use restrictions.
- **OpenFootAPI:** upstream source-specific licence controls; samples labelled FotMob Unlicensed-Beta are not approved.
- **PitchAPI** and **Club-Football-Match-Data:** no ingestion until upstream data lineage and rights are cleared.

## 5. Field-level point-in-time requirements

| Feature family | Minimum evidence |
|---|---|
| Team form / results | Kickoff and final-result publication/availability timestamps; corrections retained; only results settled before cutoff enter rolling form |
| xG / shots / PPDA | Definitions, event timestamps, publication timestamps, historical depth and proof the value existed before cutoff; post-match aggregates excluded from pre-match features |
| Lineups / injuries / player availability | First publication timestamp, update history, confirmed vs predicted status, source provenance and player/team IDs |
| Odds | Bookmaker, market, selection, line, decimal price, exact quote/snapshot timestamp, event ID, pre-cutoff availability and coverage denominator |
| Team / fixture identity | Stable provider IDs, canonical mapping history, competition/season identifiers, kickoff revisions and ambiguity quarantine |

For The Odds API, retain the provider's snapshot/quote timestamp. Do not substitute local retrieval time. Five-minute historical snapshots are not continuous ticks; measure actual event/bookmaker/market coverage before claiming 98%.

## 6. Mandatory evidence pack for new sources

Before approval, archive:
1. Current product documentation and exact endpoint reference.
2. Account plan/entitlement export and dated coverage report for all seven competitions.
3. Representative raw API responses for each selected field family.
4. Historical samples spanning at least three seasons where available, including timestamps and revisions.
5. Written rights covering collection, retention, internal analysis, model training, derived outputs, public display, attribution and redistribution.
6. Rate limits, quotas, request costs, SLA/uptime, support and price quotation.
7. Deterministic identity crosswalk and measured match/team join rates.
8. A point-in-time audit proving no selected feature was published after its intended prediction cutoff.

Missing evidence is **UNKNOWN**, never PASS.

## 7. Initial qualification order

1. Preserve the existing approved 5Dollar fixture/result role and The Odds API prospective odds role; do not requalify them by assumption.
2. Qualify Wyscout historical shot-event ingestion and xG research strictly within its CC BY 4.0 scope and dataset limitations.
3. Request Sportmonks sample coverage, exact seven-competition availability and written rights; no subscription until evidence is reviewed.
4. Request Goalserve sample export, timestamp semantics, coverage and written terms; no spend until evaluated against cost-per-qualified-match.
5. Keep StrikerAPI dormant until free credits refresh and accepted Terms are verified.
6. Keep OpenPlay quarantined pending upstream rights.
7. Use football-data.org only if it materially improves exact competition/season coverage and rights are confirmed.

## 8. Phase 4 entry gate

Model architecture work remains blocked until selected feature families have at least one qualified source, exact competition/season coverage is measured, rights are approved for collection/retention/training, point-in-time availability is demonstrated, identity mapping is deterministic and audited, and the capture schema preserves raw evidence and immutable revisions.

No legacy prediction code, features, priors, calibration or decision rules may be reused. No provider is newly approved by this register. No production deployment, prediction publication, Telegram activation, scheduling or value-bet unlock is authorized.

## 9. Public documentation reviewed

- 5DollarFootballAPI docs: https://5dollarfootballapi.com/docs
- 5Dollar Community plan: https://5dollarfootballapi.com/community
- 5Dollar data quality: https://5dollarfootballapi.com/docs/data-quality
- 5Dollar Terms: https://5dollarfootballapi.com/terms
- The Odds API historical data: https://the-odds-api.com/historical-odds-data/
- The Odds API v4 documentation: https://the-odds-api.com/liveapi/guides/v4/
- Sportmonks plans and pricing: https://www.sportmonks.com/football-api/plans-pricing/
- Sportmonks xG documentation: https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/expected-xg
- Sportmonks FAQ: https://www.sportmonks.com/faq/
- Goalserve football API pricing: https://goalserve.com/en/sport-data-feeds/football-api/prices
- StrikerAPI docs: https://strikerapi.com/docs
- StrikerAPI timing and rights: https://strikerapi.com/docs/timing-and-rights
- football-data.org pricing: https://www.football-data.org/pricing
- football-data.org API reference: https://www.football-data.org/documentation/api
- Wyscout dataset paper: https://www.nature.com/articles/s41597-019-0247-7
- OpenPlay releases: https://github.com/nlbair/openplay/releases

**Evidence limitation:** public documentation is discovery evidence only. Account-specific entitlements, exact field-level coverage, current contracts, publication timestamps and legal rights remain unverified unless explicitly identified above as previously tested in Phase 1.
