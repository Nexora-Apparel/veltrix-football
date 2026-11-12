# VELTRIX FOOTBALL 2.0 — Phase 4 Provider Qualification Register

**Assessment date:** 2026-11-13  
**Branch:** `phase4/provider-qualification-20261113`  
**Purpose:** qualify independent, rights-approved, point-in-time feature sources before any new prediction-engine implementation.

## 1. Non-negotiable qualification policy

A provider is not production-approved by virtue of marketing claims, a successful API response, or broad historical coverage. Approval requires evidence for the exact account, endpoint, competition, field and intended use.

Every acquired observation must retain exact raw response bytes and SHA-256, provider/product/endpoint identity, request parameters with secrets redacted, HTTP status, retrieval timestamp, source event/publication timestamp where supplied, stable entity identifiers, rights evidence, and immutable revision history.

A pre-match feature is eligible for a fixture only when its source availability is provably no later than the frozen prediction cutoff. A post-match statistic (including xG, shots and lineups published after kickoff) is a label/retrospective descriptor only, not a pre-match feature. Current pages and inferred timestamps cannot repair missing historical publication times.

No source is approved for commercial storage, model training, redistribution or public display until the relevant rights are reviewed separately for each use.

## 2. Preliminary provider register

Statuses:
- **Candidate — documentation reviewed:** potentially useful; no account-level qualification yet.
- **Conditional candidate:** useful for a narrow role, with important limitations.
- **Not approved:** required evidence is missing.
- **Approved:** none at this stage.

| Provider | Potential role | Publicly documented facts | Blocking evidence / risks | Preliminary status |
|---|---|---|---|---|
| 5DollarFootballAPI | Fixture/result identity and settled labels; possibly odds history | Current docs describe historical results from 2014 for major competitions, plan-dependent depth, and tick-stored odds. The existing Community account staging import has seven entitled competition IDs and 2,496 traceable settled-result labels. | Existing import has no certified pre-kickoff feature snapshots. The exact account entitlement, historical odds depth, per-competition completeness, source publication timestamps, retention/training/display rights and stable-ID migration behavior must be evidenced from the account and contract. Do not infer that public docs describe this account's plan. | Conditional candidate for fixture/label continuity only; not approved as feature or odds-history source |
| Sportmonks Football API | Team/player stats, match statistics, lineups, injuries, xG, fixtures | Public plans start at €29/month for five leagues, €99 for 30, €249 for 120; historical data older than three seasons is an add-on from €29 one-time for non-Enterprise plans. xG is an add-on; xG is documented from 2024 onward. | Must verify coverage for the exact seven entitled competitions, historical depth by competition/field, timestamp semantics and whether historic lineups/injuries/stats were available before kickoff. xG published after match completion is not a pre-match feature. Rights and commercial training/storage terms require written review. | Candidate — documentation reviewed; not approved |
| The Odds API | Historical bookmaker benchmark and price movement | Historical snapshots available on paid plans; featured markets from 2020-06-06, every 10 minutes initially and every 5 minutes since September 2022. Historical endpoint returns closest snapshot at or before requested time. | Football league/bookmaker/market coverage must be checked event-by-event. Snapshot cadence is not continuous tick history and may miss quotes; establish timestamp meaning, quote coverage, bookmaker identity, market mapping and plan cost. Rights for storage/training/display require review. | Candidate for odds archive; not approved |
| Goalserve | Historical results, detailed stats, lineups/injuries and odds | Public pricing lists Soccer Live Stats from $200/month, Fixtures/Results from $150/month, Pregame Odds from $250/month and Full Stats package from $300/month. Provider advertises results back to 2006 and detailed player/team stats from 2016, with historical lineups and injury lists. | Marketing claims do not prove exact seven-competition completeness, point-in-time publication timestamps, xG coverage, historical odds snapshot granularity or rights. Full stats package price is material; request a sample export and contract before any spend. | Candidate — documentation reviewed; not approved |
| StrikerAPI | Historical team/player performance, xG, odds movement | Public docs list team stats including goals, xG, shots and possession; event/shot-map data; sportsbook odds; line movement; market odds history from May 2023. | Public documentation reviewed does not establish all seven competition coverage, historic feature depth, publication timestamps for each statistic, source licensing or commercial model-training rights. Validate account plan and API semantics before use. | Candidate — documentation reviewed; not approved |
| football-data.org | Fixtures/results, lineups, cards, shots and basic match statistics for supported competitions | Pricing lists €29/month ML Pack Light with ten seasons of history; €29/month Free + Deep Data with lineups/subs; €49 Standard for 30 competitions; odds add-on €15/month and statistics add-on €15/month. API supports season-specific match retrieval. | Coverage is limited to listed competitions; no documented xG feed in the reviewed plan matrix. Historical records are not proof of historical as-of availability. Validate exact competition availability and rights. | Conditional candidate for fixtures/basic stats; not approved |

## 3. Competition qualification matrix

The exact seven competition IDs from the 5DollarFootballAPI account approval are the baseline. Do not substitute competition names or assume coverage from a provider's generic league count.

For every candidate, obtain a machine-readable coverage export and map:
- provider competition ID and canonical name;
- country/region and gender/age category where applicable;
- season start/end and match counts;
- fixture IDs and team IDs;
- available fields per season;
- missingness/completeness by field;
- historical start date per field;
- whether the record has a source publication/availability timestamp;
- whether corrections are versioned or overwrite prior values.

The seven-ID mapping must be reviewed explicitly before any provider is used as a feature source. A provider's coverage of a competition's men's first team does not establish coverage of its women's, reserve, youth or lower-division counterpart.

## 4. Field-level point-in-time requirements

| Feature family | Minimum evidence |
|---|---|
| Team form / results | Match kickoff and final-result publication/availability timestamps; historical corrections retained; only results settled before cutoff enter rolling form |
| xG / shots / PPDA | Match-level and team/player field definitions, event timestamps, publication timestamps, historical depth, and proof the value existed before cutoff; post-match aggregates are excluded from pre-match features |
| Lineups / injuries / player availability | First publication timestamp, subsequent update history, confirmed vs predicted status, source provenance and player/team IDs |
| Odds | Bookmaker, market, selection, line, decimal price, exact snapshot timestamp, event ID, quote availability before cutoff, and coverage denominator |
| Team / fixture identity | Stable provider IDs, canonical mapping history, competition/season identifiers, kickoff revisions and ambiguity quarantine |

## 5. Mandatory provider evidence pack

Before a provider can pass qualification, archive:
1. Current product documentation and exact endpoint reference.
2. Account plan/entitlement export and dated coverage report for the seven competitions.
3. Representative raw API responses for every required field family.
4. Historical samples spanning at least three seasons where available, including timestamps and revisions.
5. Written rights evidence covering collection, retention, internal analysis, model training, derived outputs, public display, attribution and redistribution.
6. Rate limits, quotas, request costs, SLA/uptime, support and price quotation.
7. Deterministic identity crosswalk and measured match/team join rates.
8. A point-in-time audit proving no selected feature was published after its intended prediction cutoff.

Missing evidence is recorded as **UNKNOWN**, never assumed PASS.

## 6. Initial source strategy

- Keep 5DollarFootballAPI as the existing fixture/label archive reference only; do not elevate it to feature-source status based on its historical result import.
- Run a low-cost, no-commitment coverage/sample qualification of Sportmonks first for structured team/player statistics, lineups, injuries and xG. Do not subscribe until the exact seven-competition coverage and rights are confirmed.
- Qualify The Odds API separately for timestamped historical bookmaker snapshots. A five-minute cadence is potentially useful but must be measured against the required 98% odds timestamp coverage.
- Request a sample and written terms from StrikerAPI and Goalserve before comparing cost-per-qualified-match. Goalserve's advertised full-stats monthly price is not justified until timestamp and rights questions are answered.
- Use football-data.org only as a potential low-cost fixture/basic-stat supplement, not as an assumed xG or comprehensive feature source.
- Prefer independent providers for feature families where feasible; preserve provider disagreement rather than silently overwriting one source with another.

## 7. Phase 4 entry gate

Phase 4 model architecture work remains blocked until:
- at least one source is qualified for each feature family actually selected;
- exact competition/season coverage is measured;
- rights are approved for collection, retention and model training;
- point-in-time availability is demonstrated;
- identity mapping is deterministic and audited;
- a capture schema preserves raw evidence and immutable revisions.

The provider register is an evidence ledger, not a declaration that any provider is approved. No legacy prediction code, features, priors, calibration or decision rules may be reused.

## 8. Public documentation reviewed

- 5DollarFootballAPI docs: https://5dollarfootballapi.com/docs
- Sportmonks plans and pricing: https://www.sportmonks.com/football-api/plans-pricing/
- Sportmonks xG documentation: https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/expected-xg
- Sportmonks xG availability FAQ: https://www.sportmonks.com/faq/
- The Odds API historical data: https://the-odds-api.com/historical-odds-data/
- The Odds API v4 documentation: https://the-odds-api.com/liveapi/guides/v4/
- Goalserve football API pricing and coverage: https://goalserve.com/en/sport-data-feeds/football-api/prices
- StrikerAPI documentation: https://strikerapi.com/docs
- football-data.org pricing: https://www.football-data.org/pricing
- football-data.org API reference: https://www.football-data.org/documentation/api

**Evidence limitation:** public web documentation is discovery evidence only. Account-specific entitlements, current contracts, exact competition coverage, data availability timestamps and legal rights remain unverified.
