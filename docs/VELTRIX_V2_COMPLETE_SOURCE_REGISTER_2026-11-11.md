# VELTRIX FOOTBALL 2.0 — Complete source register and competition qualification
Date: 2026-11-11
Status: corrected inventory of sources discovered in project research; this is not blanket approval to ingest or train.
Branch: veltrix-2.0-architecture-blueprint

## Decision rule

A source is classified separately by (1) discovery, (2) account/endpoint access, (3) observed competition and field coverage, (4) rights to access/store/train/display, and (5) point-in-time integrity. "Found" does not mean "qualified"; an HTTP 200 does not establish coverage or rights. No source may silently inherit approval from another provider or data type.

VELTRIX is currently intended for the owner's private, non-commercial analysis. This does not override API terms, upstream rights, rate limits, attribution or retention rules. No source below is approved for every use case.

## Source register

| Source | What it can contribute | Competition reach found/documented | Evidence and limitations | Current decision |
|---|---|---|---|---|
| 5DollarFootballAPI | Fixtures, results, tables, team statistics, Bet365 odds snapshots/markets | Account-confirmed Free: England Premier League, France Ligue 1, Germany Bundesliga I, Italy Serie A, Spain La Liga. Community Access is documented as top five plus one country pack and 12 months history, but is NOT account-confirmed. | Live smoke verification 2026-11-11: auth passed; five accessible leagues; one bounded sample of five EPL fixtures returned 1X2 5/5, O/U 2.5 5/5, BTTS 3/5. A second bounded run reproduced the same coverage. The 60 req/hour counter showed 46 remaining after the second run. Existing account: Free, three months history, 20/min burst. Official Terms of Service (October 2026) explicitly permit use in the customer's own models, commercial products, caching and end-user display. Public-facing Free products must visibly attribute “Football data by 5DollarFootballAPI” with a link; raw-feed resale/redistribution is prohibited. | Primary bounded fixtures/results source for those five leagues; model training rights approved under published terms. Historical availability remains conservative four-day lag and is not point-in-time certifiable; odds primary candidate with measured BTTS gaps. Do not assume Community entitlement. |
| GOAL API | Fixtures/results; possible stats, lineups, events and odds require endpoint-by-endpoint qualification | Argentina Liga Profesional and Brazil Serie A probes returned samples; docs advertise further coverage. | Bearer auth + browser-like User-Agent passed read-only probe; 982/1,000 daily calls remained after 18 calls. Official Terms of Service last updated November 2026 grant a limited right to incorporate returned data into apps/sites/products, but explicitly grant no underlying sports-data IP licence and place third-party rights clearance on the customer; no explicit model-training grant was found. | Technical fixtures/results candidate for Argentina/Brazil only. No model training or public display until upstream rights and model-use scope are clarified in writing. |
| StrikerAPI | Fixtures/results, standings, lineups, box scores, match events, shot locations, odds; provider-computed xG/per-90/Elo | Docs show broad competition endpoints; project historical qualification previously covered EPL, Argentina and Brazil. | Account currently returned HTTP 402 because 500 monthly free credits were exhausted. Credits refresh monthly; endpoints consume credits. Docs state own-product/model use allowed, raw-feed resale prohibited. No live call now. | Strong historical/enrichment candidate when credits refresh; conserve credits for bounded tests. |
| OpenPlay data-v0.1.0 | Historical match/player/team stats, lineups, shots, shot-level xG, event data | Big-five European leagues, UEFA club competitions and selected international tournaments; static through 2025/26. | Pinned release downloaded and hash-verified (10 Parquet tables); 26,536 matches with event data, 775,994 player-match rows, 1,068,162 lineup rows, 669,404 shots, 53,094 team-match rows. Release declares CC BY 4.0, but maintainer identifies WhoScored/Opta/Stats Perform upstream; rights chain and historical pre-match availability are not independently established. | Technically qualified dataset/adapter; high-value historical research candidate. Quarantine from training until upstream rights and point-in-time availability are resolved. Preserve its native xG model identity. |
| StatsBomb Open Data | Event, lineup and selected 360 data; native shot xG and event attributes | Selective competition-season coverage only; not universal or current-live coverage. | Official repository states research/analytics purpose, attribution and logo requirements; custom user agreement/registration applies. Adapter and event aggregation implemented, but rights/availability metadata must be checked per match. | Personal research after agreement/registration and attribution; not a general production feed. |
| OpenFootball football.json/world | Historical/current fixtures and results; repository claims CC0/public-domain data | European leagues and cups; world repository explicitly lists Nigeria Premier Football League, Egypt, Morocco, Algeria, Brazil, MLS, Japan, Australia and others. | No key or quota. Snapshot can lag; prior 90-day EPL reconciliation found 45/100 exact scores, six date conflicts and 49 missing scores. Date-only/local unzoned timestamps must not be converted to invented UTC. NPFL 2025/26 file cites RSSSF as its source; RSSSF states its archive data are subject to copyright, so the repository-level CC0 statement does not by itself resolve upstream rights for that file. | Supplemental discovery/cross-check only. Do not ingest/train on NPFL RSSSF-derived rows until upstream rights are clarified.
| Open Matchday | Current-season fixtures/results, HT/FT, goal minutes, basic match stats (shots, fouls, cards, corners) | 75 competitions listed, including top five, UEFA cups, Championship, Brazil, Argentina and other regions. | Repository says informational non-commercial use. It merges OpenLigaDB, fixturedownload, ESPN, football-data.co.uk, FotMob and Soccerway; provider rights remain in force. Its own README reports stats only on about 19% of rows, goal minutes about 8%, no xG/lineups/injuries/odds/play-by-play, and fixed CET-1 kickoff convention (can be one hour wrong in summer). | Useful coverage discovery and manual research comparison only. Do not bulk-ingest or train on the compilation until upstream rights are separately cleared for each contributing dataset. |
| PitchAPI | Fixtures/results, events, shots/xG, player/team stats, lineups, advanced analytics and heatmaps including PPDA, xG timeline and confirmed/predicted lineup flags | Official docs claim 77 leagues, history back to 2021, every endpoint on a free plan with no request allowance; timestamps are RFC 3339 UTC and IDs are opaque. | Documentation was inspected 2026-11-11. It explicitly warns that pre-kickoff lineups may be predictions and advanced analytics are unavailable for some matches. No terms/privacy or upstream-data licensing policy was found in the published docs; account access, per-league completeness, source lineage, retention and model-training permission remain unverified. Provider xG is its own model and cannot be mixed with others. | Highest-priority technical probe candidate, but do not store, train, display or use in production until the provider supplies written rights, upstream lineage and privacy/retention terms. |
| FootyStats API | Results, team/player statistics, xG, shots, odds, player metrics and historical match data | Official pricing page lists Free as Premier League only, 180 requests/hour and limited endpoints; Hobby is 50 leagues/1,800 requests per hour at £29.99/month. However, the official tutorial says API access starts at £29.99/month, while the FAQ says example-key calls are free. Therefore public example-key access is verified, but actual account Free-plan entitlement is contradictory and not verified. | Official API FAQ/Terms allow API data to be stored, retained after cancellation, used in AI/ML/prediction models and displayed in websites/apps; raw-data resale/redistribution is prohibited and no attribution is required. Live example-key probe passed against the official 2024/25 EPL sample: 10 match rows returned required fixture/result fields and xG columns (team_a_xg, team_b_xg, total_xg plus prematch variants). The API documents max_time for as-of statistics, but historical cutoff semantics have not yet been independently validated. Actual account Free-tier fields, pagination depth, timestamps and per-match xG completeness remain unverified. | Strong EPL historical-enrichment candidate with explicit model-use rights. Public example-key probe is technically verified, but do not classify it as an account-backed free production source until FootyStats resolves the Free-plan contradiction and a real account key confirms endpoint entitlement. Do not assume 2007 coverage or complete xG/odds on every match. |
| Football API (footballapi.org) | Fixtures, results, standings, match records, club form, head-to-head, goals/cards and selected match statistics | Official complimentary key: current-season Premier League only; 50 calls/day, 10/minute. Membership: $29/month or $299/year for 68 competitions and seasons back to 2015/16. | Official Terms (21 Oct 2026) allow use in own work, apps and sites and display to own users; prohibit raw-data resale/redistribution, bulk extraction to rebuild its collection, and competing-product replication. No explicit model-training grant found. API docs claim stable IDs and UTC timestamps; docs show some match records contain club xG fields, but field coverage and historical completeness are not independently tested. No VELTRIX account/key probe yet. | High-priority bounded Premier League fixtures/results candidate, but not approved for training or production persistence until model-training rights are clarified in writing and a read-only account probe verifies timestamps, field coverage, daily quota and completeness. No odds or lineups; not a standalone full VELTRIX source. |
| Football Soccer API (footballsoccerapi.com) | Fixtures/results, match detail, lineups, team/player statistics, xG, travel/context, exchange kickoff/half-time prices | Published Free key: 50 requests/day, 60/minute; current pricing/docs say yesterday's results only across all leagues. Archive: $49/month for historical settled matches/prices/stats; Live: $99/month for current/upcoming fixtures and live feeds. No VELTRIX account/key or live probe. | Terms (27 Oct 2026) and Acceptable Use (5 Sep 2026) explicitly allow building models, research, commercial applications and user-facing display; storage after cancellation is allowed; raw bulk archive redistribution/rebuilding a competing database is prohibited. Provider says its data may be inaccurate/incomplete and is not authoritative for settlement. Official Free-plan pages conflict: current pricing/docs say yesterday-only; a separate older Free-key page describes ten-season archive access. Treat current pricing/docs as authoritative until provider confirms. | High-priority candidate for a daily, independent results cross-check and long-run prospective result collection; not an immediate historical training source or pre-match fixture/odds source on Free. Model-use rights are documented, but no live key test, exact field coverage or source lineage audit. Do not use as sole settlement authority. |
| OpenFootAPI | Fixtures/results, standings, search, team metadata, match context; paid plan adds lineups, events, shot-level xG and odds | Official Free Starter: 120 competitions, 5,000 requests/month, 60/min; fixtures, scores, schedules, standings and search. Developer costs $14/month and unlocks lineups/events/xG/odds; excluded from the no-budget plan. | Terms last updated 2026-09-07 explicitly permit internal statistical research, model training, evaluation, validation and indefinite retention. Every competition carries its own source/license metadata and published outputs must carry source attribution; no raw feed redistribution. Public-demo probe passed: 120 competitions; public match sample 5/5 with UTC kickoff, updatedAt and sourceRefs; EPL 2010/11 historical query returned 5 preview rows. Live source-license distribution: FotMob 80 competitions (Unlicensed-Beta), Football-Data.co.uk 31 (Free-Open-Data), Livesport 6 (Public-Factual-Data), OpenLigaDB 3 (ODbL-1.0), OpenFootball CC0 0. Top-five historical entries all report FotMob Unlicensed-Beta. No SLA; beta; source-level rights remain binding. | Broad fixtures/results discovery candidate only. The three ODbL competitions (DFB Pokal, 2. Bundesliga, 3. Liga) have only two seasons each and require attribution; not enough historical depth for certification. Do not train or publicly display FotMob, Football-Data.co.uk or Livesport sourced records until each source grants explicit rights. |
| OpenLigaDB direct API | German and selected European fixtures, results, standings and match metadata | 2026 live catalogue: 85 leagues; verified current-season match sets include 1. Bundesliga 306, 2. Bundesliga 306, 3. Liga 380, DFB Pokal 56, Champions League 144 and LaLiga 380. Premier League shortcut returned 0 rows in this probe. | Official API is free/no-key, 60 requests/minute per IP; use getlastchangedate for cheap polling and fetch full data only when changed. Official page states records are user-entered/community-maintained and published under ODbL 1.0; commercial use/copy/adaptation allowed with attribution and share-alike for redistributed modified databases. Historical probe: Bundesliga seasons 2010, 2015, 2020 and 2025 each returned 306/306 results; LaLiga returned 0 rows for those years. Every sampled current/historical match had matchDateTimeUTC and lastUpdateDateTime, but lastUpdateDateTime and getlastchangedate responses are timezone-naive; do not treat them as UTC or use them for PIT certification without provider confirmation. Team logo/icon rights are not granted by the data licence. | Strong free ODbL candidate for Bundesliga history/current fixtures, cups and selected leagues; LaLiga current-season sample also present. Cross-check community-entered scores. Historical labels may support exploratory training with conservative availability assumptions, but not point-in-time certification until update timestamp timezone/semantics are confirmed. Source attribution required; do not use logos without separate permission. |
| football-data.org | Fixtures, results, tables and limited match/team data | Free plan documents 12 competitions including major Europe and selected others. | Free 10 requests/min; existing project token previously returned invalid-token. Public terms/retention and post-cancellation rights need written clarification; no confirmed xG or odds history. | Secondary fixtures/results candidate after corrected credential and written rights clarification. |
| TheSportsDB | Fixtures/events, results, event lineups/timelines/stats, player lookups, metadata/images | Broad catalogue; coverage is uneven and must be checked by league. | Official free v1 key 123, 30 req/min, strict endpoint-specific result caps: e.g. event lineups/timeline/stats 5 results, player stats 10, event lookup 1. Terms last updated 2026-09-17 say free API content may be copied/modified via official endpoints for development projects, but free usage cannot publish apps to an app store without paid subscription; rights for public website/Telegram distribution are not explicit. No verified xG coverage or point-in-time publication timestamps. | Internal metadata/spot-check candidate only. No public display or production dependency until distribution rights are clarified; not a bulk player-stat/xG backbone. |
| The Odds API | Timestamped bookmaker odds and market snapshots | Live probe previously listed 46 soccer competitions; event-specific coverage varies. | Existing key authenticated; 1X2, totals and BTTS markets observed. Terms permit storing, retaining, displaying and using data to train statistical/ML models; raw-feed resale prohibited. Must preserve captured timestamps, bookmaker and market/line identity. | Preferred secondary odds/benchmark source; odds only, not results/history. |
| OddsPapi | Supplemental odds enrichment | Not recently requalified by competition or market. | Existing adapter/secret reference found; no fresh live coverage/quote timestamp audit. | Dormant odds candidate pending fresh independent verification. |
| InferSports | Keyless events; schema for 1X2/totals odds | Same-day events returned in prior probe; actual quote-bearing competition coverage not established. | Three bounded odds probes previously returned no current quotes; schema did not establish BTTS support. | Disabled research candidate; not a results-history replacement. |
| OpenLigaDB / fixturedownload / ESPN / FotMob / Soccerway | Upstream feeds used in Open Matchday's aggregation | Varies by competition and stat type. | Not independently qualified for VELTRIX ingestion or rights; Open Matchday itself warns upstream rights remain in force. | Do not treat as independently approved sources just because they appear in an aggregator. |
| Football-Data.co.uk archive | Historical results, odds and some statistics | 38 division codes in recovered artifact; 70,444 rows. | File-quality audit passed (no malformed rows or duplicate match keys), but site terms restrict free data to private/academic use and disallow automated AI/model-training projects. Missing exact kickoff and per-record publication timestamps. | Audit/reconciliation only; no automated ingestion or model training. |
| FPL public API | EPL player/gameweek statistics | EPL/FPL only. | Terms prohibit automated extraction/access absent permission; undocumented API. | Explicitly excluded. |
| Understat / FBref scraping | Potential xG and advanced statistics | Selected leagues. | Scraping/storage/training rights not cleared; FBref's Opta advanced data access changed. | Do not scrape. |
| API-Football/API-Sports | Broad fixtures/statistics | Broad advertised coverage. | User-reported credential suspension twice. | Excluded from active dependencies. |
| Highlightly | Fixtures and selected stats | Previously limited and rate-limited. | Prior 429 and incomplete coverage. | Legacy only; do not silently fall back. |
| Sportmonks | Broad fixtures/stats/xG/odds depending paid bundles | Free tier limited to Denmark and Scotland; wider paid plans. | No-budget constraint; advanced data add-ons. | Technically credible paid alternative, not in current no-spend plan. |

## Competition coverage interpretation

### Current fixtures/results candidates
- **England, France, Germany, Italy, Spain (top flights):** 5Dollar is account-confirmed. OpenFootball and Open Matchday can provide independent supplemental records, but their freshness/rights/timestamp constraints apply.
- **Argentina and Brazil:** GOAL API passed a bounded fixtures/results technical probe. Open Matchday and OpenFootball world repositories list these competitions, but the exact dataset snapshots need freshness and identity audits. StrikerAPI has historical qualification evidence but current credits are exhausted.
- **Nigeria (NPFL):** OpenFootball world explicitly lists the Nigeria Premier Football League. This is a discovered CC0 fixture/results source, not yet live-audited for current-season completeness, score freshness or stable team identity. Open Matchday's competition index should also be checked; its upstream rights remain unresolved.
- **UEFA Champions/Europa/Conference League:** OpenPlay and StatsBomb have selective historical event/lineup data; Open Matchday lists current-season fixtures/results. StrikerAPI/5Dollar/PitchAPI coverage must be checked against the exact account and league catalogue.
- **Championship and other domestic second tiers:** OpenFootball/Open Matchday list several; StrikerAPI and PitchAPI are candidates. No broad account-level production approval yet.

### Separate odds coverage
- The Odds API and 5Dollar can support 1X2, BTTS and totals depending on event/bookmaker availability. The first 5Dollar sample had only 3/5 BTTS quotes; The Odds API is the fallback candidate. OddsPapi remains unverified.
- Historical match results cannot be treated as historical odds. A current quote retrieval timestamp cannot be backdated to kickoff or historical dates.
- A 98% odds coverage gate must be measured on the exact eligible prospective fixture universe and per market, not inferred from a provider's advertised catalogue.

## Immediate qualification work

1. **PitchAPI:** obtain a key; probe one overlapping EPL date plus one Argentina, Brazil, Nigeria, UEFA and Championship fixture where available. Capture endpoints for fixtures/results, lineups with confirmed flags, player/team stats, shots/xG, events and publication timestamps. Request written lineage, retention, personal model-training and attribution terms before storage/training.
2. **FootyStats:** use the official free test endpoints/account to establish the actual free EPL data fields, historical depth, rate limits and xG/shot availability. Terms explicitly allow model use; don't assume that applies beyond API data retrieved under an eligible account.
3. **TheSportsDB:** bounded free v1 sample for event IDs, lineups, event stats and player stats across one EPL and one Nigerian fixture; document sparse limits and timestamps. Metadata/spot-check only unless coverage proves otherwise.
4. **OpenFootball Nigeria:** pin the world repository commit and NPFL dataset, hash it, inspect season completeness and score status, and compare a bounded sample against a second independent source.
5. **Open Matchday:** use the per-league index to map competitions and stats coverage, but do not import merged data until every upstream provider's relevant terms are resolved. Fixed CET-1 time conversion is not a valid universal UTC timestamp.
6. **StrikerAPI:** wait for monthly credits to refresh; use a bounded call budget after prioritizing missing historical match data, lineups and events.
7. **Odds:** keep The Odds API as secondary market source, record each capture time, and measure quote coverage by 1X2/BTTS/O-U independently.

## Non-negotiable gate

No source is approved for model training solely because it has a public endpoint, free tier, CC licence claim, API key, or successful HTTP response. Require source/competition/season-specific coverage, upstream rights, data retention permission, point-in-time availability, stable identity mapping, measured missingness, duplicate/conflict reconciliation, and exact payload provenance. Until then, keep records quarantined and let the prediction system abstain.


## Live provider smoke evidence — 2026-11-11

- Repository workflow Verify Multi-Source Football Providers completed successfully on branch veltrix-2.0-architecture-blueprint, run #43070489675.
- 5DollarFootballAPI authenticated and exposed exactly five leagues. The bounded EPL odds sample was 1X2 5/5, O/U 2.5 5/5, BTTS 3/5. After the bounded run, the provider reported 46 requests remaining on its hourly counter.
- The Odds API accepted its key and listed 46 active soccer competitions; the /sports catalogue request reported 298 requests remaining. No odds-market quota was used in this authentication check.
- The earlier PR-triggered workflow named Multi-Source Provider Verification only ran unit tests; its provider-auth and live-market steps were skipped because the event was a pull request. Do not cite that workflow as live provider evidence.
- No provider smoke result establishes source rights, training permission, historical depth, event completeness or 98% prospective odds coverage.


### FootyStats free example-key technical probe — 2026-11-11

- Opt-in workflow [#43073399418](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43073399418) passed using the provider's public `example` key; no account key or user quota was used.
- Official 2024/25 EPL sample (`season_id=12325`) returned 10 rows with fixture ID, Unix kickoff, status, team IDs and final goal counts.
- The sample included `team_a_xg`, `team_b_xg`, `total_xg`, and corresponding pre-match fields.
- The API accepted two `max_time` requests (2025-01-01 and 2025-03-01 UTC) and returned 10 rows for each. This verifies parameter acceptance only; it does not yet prove the as-of fields are leakage-safe or source publication timestamps are known.
- Next qualification step is a free account key and a bounded EPL season sample to verify the actual Free-plan endpoint entitlement, pagination, historical depth, xG coverage and timestamp/availability semantics.


### OpenFootAPI public-preview qualification — 2026-11-11

- Workflow [#43074794958](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43074794958) passed using the provider's public demo key; no private API key or user quota was used.
- The competition catalogue returned 120 competitions. The top-five historical entries each advertised 17 available seasons, but all five listed FotMob with the source licence string “Unlicensed-Beta (owner-approved factual data)”.
- A public date query returned five matches and source metadata, including UTC kickoff, `updatedAt`, stable match ID and `sourceRefs`. An EPL 2010/11 query returned five historical preview rows, sourced to FotMob.
- Another sample match carried both FotMob “Unlicensed-Beta” and Football-Data.co.uk “Free-Open-Data” source records. These source labels are not interchangeable with a blanket OpenFootAPI training licence.
- OpenFootAPI's own Terms permit internal model training and retention, but also require compliance with each upstream source licence and carrying source attribution into published outputs. Therefore the provider is technically qualified for a bounded metadata/fixtures preview, not approved for production training or public display until source-owner rights are confirmed.
- Free Starter covers fixtures/results/standings/search only. xG, lineups, live events and odds require the $14/month Developer tier; do not assume those fields are free.


### OpenFootAPI source-license distribution — 2026-11-11

- Public demo catalogue returned 120 competitions and the following source-license distribution: FotMob 80 / Unlicensed-Beta; Football-Data.co.uk 31 / Free-Open-Data; Livesport 6 / Public-Factual-Data; OpenLigaDB 3 / ODbL-1.0; OpenFootball CC0 0.
- The three ODbL competitions were DFB Pokal, 2. Bundesliga and 3. Liga, each with only two available seasons in this catalogue.
- The five top-tier leagues (Premier League, La Liga, Serie A, Bundesliga and Ligue 1) each showed 17 seasons but all were sourced from FotMob under “Unlicensed-Beta (owner-approved factual data)”. That is not an explicit public licence and is not approved for VELTRIX training or display without written source-owner permission.
- Football-Data.co.uk's own policy restricts its free data to personal/academic research and excludes commercial AI/model-training projects. The OpenFootAPI wrapper terms do not override that upstream restriction.
- Livesport's “Public-Factual-Data” label has not been supported by a source-owner licence grant; keep it quarantined pending written confirmation.


### OpenLigaDB detailed coverage and timestamp qualification — 2026-11-11

- Public API probe [#43075704724](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43075704724) completed successfully. The 2026 catalogue contained 85 leagues.
- 2026/27 returned: 1. Bundesliga 306 fixtures / 81 results; 2. Bundesliga 306 / 99; 3. Liga 380 / 130; DFB Pokal 56 / 48; Champions League 144 / 72; LaLiga 380 / 100; Premier League 0.
- Bundesliga historical seasons 2010, 2015, 2020 and 2025 each returned 306 fixtures with 306 results. LaLiga returned no rows for the same four seasons.
- All returned match records contained `matchDateTimeUTC`, `lastUpdateDateTime`, and match-result structures. However, `lastUpdateDateTime` and `getlastchangedate` values were timezone-naive (e.g. `2026-09-02T15:36:25.313`); do not infer UTC or local timezone. This prevents using them as certified point-in-time availability timestamps until OpenLigaDB confirms timezone and semantics.
- The official API documentation states 60 requests/minute per IP, recommends polling `getlastchangedate` before fetching full matchday data, and says completed seasons do not change. The provider's official page says the records are community-entered and published under ODbL 1.0.
- OpenLigaDB's data licence does not grant rights to linked team logos/icons. The website's desired team-logo cards require a separate asset-rights solution.


### Football API (footballapi.org) — official terms and free-tier qualification — 2026-11-11

- Official documentation advertises a complimentary key limited to the current Premier League season, 50 calls/day and 10/minute. Membership is $29/month or $299/year for 68 competitions, historical seasons from 2015/16 and live scores. No VELTRIX key/account was created or probed; these are published entitlements only.
- The free key includes fixtures, results, match records, tables, club form and head-to-head. Documentation examples expose match facts and some club xG fields, but lineups and bookmaker odds are not included. Do not infer complete xG coverage from a sample example.
- Stable provider match/club IDs and UTC kickoff timestamps are documented. Point-in-time availability of historical feature fields and source publication timestamps still require verification.
- Terms last updated 21 October 2026 allow use in the customer's own work, apps and sites and display of results to its users. They prohibit raw-data redistribution/resale, bulk extraction to rebuild the provider's collection and competing-product replication. No explicit permission for training the customer's own ML prediction model was found. Therefore it is not approved as a training/persistence source until the provider confirms that use in writing.
- Recommendation: request written model-training and retention clarification first; then, if approved, run a bounded read-only Premier League sample within the 50-call daily budget. Do not consume quota for exploratory repeated probes.
- Official references: https://footballapi.org/documentation ; https://footballapi.org/terms ; https://footballapi.org/key

### FootyStats free-plan entitlement clarification — 2026-11-11

- The public example key has already passed the bounded technical sample recorded above. This does not establish an account entitlement.
- Official FootyStats pricing page lists a Free / Premier League-only / 180 requests per hour plan with limited endpoints. Its official tutorial instead states API packages start at £29.99/month, while its FAQ says several endpoints can be tested for free using the example key.
- The provider explicitly permits retrieved API data to be stored, retained after subscription cancellation, used for AI/ML/prediction systems and displayed in websites/apps; raw data resale/redistribution is prohibited.
- Status: model-use rights are documented for data retrieved through an eligible API account, but whether an actual zero-cost production account has usable access remains unresolved. Do not schedule production ingestion against the public example key.


### V2 historical runner and model-evaluation status — 2026-11-11

- The 5Dollar Free account's three-month history entitlement is now reflected in the default V2 historical runner: 90-day acquisition window, 60-day minimum usable history, shorter chronological diagnostic folds and a 200-row minimum for attempting the diagnostic. These are execution thresholds only. The 1,000 held-out matches per market certification gate is unchanged.
- The runner reports 1X2, BTTS and O/U 2.5 calibration diagnostics separately. All are marked diagnostics-only and do not imply a fitted calibrator or passed prediction-publication certification.
- The full repository unit-test suite passed **852 tests, 1 warning** on commit `781e75917908eb625ed5ec539af3a4226744d7cb` (workflow run [#43079910512](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43079910512)). Live provider probes remain opt-in; skipped probes are not treated as qualification.
- Core safeguards added during the audit: source rights must cover retrieval and forecast cutoff; player statistics cannot be available before kickoff; nonconverged Poisson models cannot emit expected goals; feature values require provenance; exact event/quote timestamps are required for The Odds API; binary odds pairs must normalize to one; and ROI method labels reflect whether a date-block interval was actually produced.
- No new provider is approved for training solely from published marketing claims. Football API (footballapi.org) remains pending written model-training permission and a live bounded key probe. FootyStats model-use rights are documented, but free-account endpoint entitlement remains contradictory pending account verification.


### Football Soccer API (footballsoccerapi.com) — terms and Free-plan qualification — 2026-11-11

- Official Terms last updated 27 October 2026 and Acceptable Use last updated 5 September 2026 explicitly permit building models, research, commercial applications and displaying results to the customer's users. Data may be stored and retained after cancellation. Raw bulk-feed redistribution, bulk archive extraction to rebuild a competing database and competing products are prohibited.
- Current pricing and documentation pages describe the Free key as 50 requests/day and 60/minute, with yesterday's settled results across all leagues only. No today's fixtures, upcoming fixtures, odds, statistics or older archive on Free. Archive is published at $49/month; Live at $99/month. No account/key was created or tested.
- A separate older Free-key landing page still describes ten seasons and historical results access. This conflicts with current pricing/docs and the 20 October changelog that says historical data moved to Archive. Do not rely on the older page for entitlement; require account-key verification.
- The API publishes match IDs, UTC kickoff timestamps and per-competition field coverage. It documents measured xG from 2022 and estimated xG from shot data, but those fields are not part of the current Free entitlement. It also publishes exchange prices at kickoff and half-time on paid plans.
- The provider expressly states that data may be incomplete or inaccurate and is not authoritative for settlement. Recommendation: if a Free key is manually created, use a bounded once-daily results-only cross-check against 5Dollar/GOAL, preserve disagreements and source hashes, and never use it as the sole settlement authority. Accumulated daily records could later support a rights-approved prospective dataset, but not a 1,000-match historical backtest now.
- Official references: https://footballsoccerapi.com/terms ; https://footballsoccerapi.com/acceptable-use ; https://footballsoccerapi.com/pricing ; https://footballsoccerapi.com/documentation ; https://footballsoccerapi.com/documentation/changelog ; https://footballsoccerapi.com/free-key


### Provider documentation refresh — 2026-11-11 (official-source recheck)

#### 5DollarFootballAPI — Community Access is a no-cost expansion, not yet activated

- The current official documentation confirms Community Access is $0, requires no card, and adds one selected country's whitelisted leagues to the existing top-five European leagues.
- Community Access advertises 12 months of results and odds, 300 requests/hour and the same 20-requests/minute burst ceiling. It can be activated from the provider's Community page for a 12-month term. It does not include the Pro batch-odds expansion (`include=odds`) on fixture lists, so VELTRIX must budget one odds request per fixture when needed.
- The existing VELTRIX account remains confirmed as Free; do not assume the Community entitlement until the account status endpoint or dashboard confirms `community`.
- This could extend the historical window and add either Argentina or Brazil without a paid subscription, but it only adds one country pack. The country selection remains a manual account decision; no account setting was changed.
- Free and Community public-facing output must show “Football data by 5DollarFootballAPI” with a link. Own-model use, caching and display in the user's own product are permitted; raw-feed resale/redistribution is prohibited.
- Official references: https://5dollarfootballapi.com/terms ; https://5dollarfootballapi.com/docs ; https://5dollarfootballapi.com/docs/changelog ; https://5dollarfootballapi.com/community

#### StrikerAPI — revised timestamp, xG and retention restrictions

- Current official docs describe 17 competitions, including Brazil Serie A and Argentina Liga Profesional; shot-location/xG data is documented from 2014 for Brazil and Argentina, with coverage varying by league and season.
- The provider permits storage while the account is open, internal research/backtesting, training the user's own models, and commercial use of derived predictions. It prohibits redistributing raw datasets/feeds and raw or bulk odds exports. No attribution is required. After cancellation, retained data is limited to the user's internal research/backtesting and cannot continue powering a user-facing product.
- Free accounts receive 500 credits/month. Calls cost 1–25 credits; rate protection is 60 requests/minute above 100 credits and 10/minute below 100. The VELTRIX account previously returned HTTP 402 due to exhausted credits; wait for refresh before further probes.
- Events and box scores are refreshed once daily at 10:00 UTC and records may be overwritten during the post-match refresh window. The provider does not retain per-record revision history or revision IDs.
- Crucially, provider xG is not point-in-time: its league model is fitted using all seasons, including later seasons, and historical shots are revalued after manual refits. Do not use its published xG as a historical pre-match feature or certified historical benchmark. If rights and provenance are accepted, use shot locations to fit VELTRIX's own xG model chronologically.
- The provider says it combines public sources and its own models but does not publish a source list per dataset, and it does not grant league rights. These limits must remain in the provenance record.
- Official references: https://strikerapi.com/docs/timing-and-rights ; https://strikerapi.com/docs ; https://strikerapi.com/data

#### FootyStats — point-in-time query capability confirmed in documentation

- The League Matches endpoint documents `max_time` as a Unix timestamp that returns league and team statistics up to the specified time. This is a useful point-in-time query mechanism and matches the previous public example-key test, which accepted two cutoff values.
- The FAQ states match statistics are usually available within about 20 minutes after full-time, but this is a freshness claim, not a per-record publication timestamp.
- The API is not a live/in-play score feed. Its FAQ documents results, xG, shots, possession, odds, lineups and player statistics, with field availability varying by league and season.
- The published FAQ and Terms permit data retrieved through the API to be stored, retained after cancellation, used for AI/ML/prediction models and displayed in websites/apps; raw data resale/redistribution is prohibited and no attribution is required.
- The Free tier remains ambiguous: the pricing page advertises EPL-only access at 180 requests/hour with limited endpoints, while the setup/tutorial says subscription is needed and the public example key is explicitly for testing. No production account entitlement is assumed.
- Qualification decision remains: strong EPL historical-enrichment candidate, but require a real account key and validate `max_time` semantics, historical pagination, per-match xG completeness and cutoff-safe feature values before persistence/training.
- Official references: https://footystats.org/api ; https://footystats.org/api/documentations/faq ; https://footystats.org/api/documentations/match-schedule-and-stats ; https://footystats.org/api/documentations/terms-of-use-and-legal

#### PitchAPI — technical feature claims confirmed; rights gate remains closed

- Current docs claim one free plan covering 77 leagues, unlimited requests, all endpoints and history back to 2021. Documented endpoints include fixtures/results, shots, lineups, events, player stats, team stats, xG timelines and advanced metrics including PPDA.
- The API documents UTC RFC 3339 timestamps and explicitly marks lineups as predicted until confirmed. Some matches may return `ANALYTICS_UNAVAILABLE`; coverage is not universal.
- The published documentation page contains no terms of service, privacy/retention policy, attribution requirements or upstream source-lineage statement. A technical claim of free access is not a data licence.
- Decision remains quarantine: no persistence, training, public display or production dependency until written provider confirmation covers upstream rights, model training, retention, public display, attribution and privacy.
- Official reference: https://pitchapi.dev/

#### GOAL API — technical access does not confer underlying sports-data rights

- November 2026 Terms state GOAL API licenses data from third-party providers for redistribution through its service, but explicitly grant no IP licence to the underlying sports data and place competition/territorial rights clearance on the customer.
- The Terms warn that betting platforms and mass-media distribution may require additional rights-holder licences. No explicit ML model-training or indefinite-retention grant was found.
- The prior Argentina/Brazil technical probes remain valid evidence of endpoint access only. Keep GOAL records out of training and public display pending written clarification of model-training, retention and upstream rights.
- Official reference: https://goal-api.com/terms


#### FootyStats public example-key response inspection — 2026-11-11

- The official documented sample match endpoint returned a 2019/20 EPL match record with stable match/team IDs, Unix kickoff, final score, shot counts, possession, actual match xG, pre-match xG fields, lineups/bench, event timings, H2H and a multi-book odds comparison.
- The response confirms that the example key exposes rich historical match fields for test data. It does not prove a real account's Free-plan access or production entitlement.
- The response contains both current aggregates (`home_ppg`, `away_ppg`) and explicitly pre-match fields (`pre_match_home_ppg`, `pre_match_away_ppg`). Current aggregates must never be used as historical pre-match features. The pre-match fields still require a bounded `max_time` cutoff test before they are accepted as point-in-time features.
- Actual `team_a_xg` / `team_b_xg` are post-match values and are not valid pre-match features. The `*_xg_prematch` fields are candidate pre-match fields only; their generation timestamp, model version and cutoff behaviour remain unverified.
- The sample's odds comparison contains bookmaker prices but no per-quote capture timestamps. It cannot satisfy VELTRIX's timestamped-odds/CLV certification gate. Do not treat the presence of historical odds as proof of captured_at provenance.
- The sample response includes a provider Terms URL in its message; usage remains bound to the official Terms of Use and raw-data redistribution remains prohibited.


### Nigeria Premier Football League (NPFL) source and historical-data audit — 2026-11-11

#### OpenFootball world / RSSSF-derived historical NPFL data

- The public OpenFootball world repository contains Nigeria top-flight seasons from 2009/10 through 2025/26, plus some second-tier seasons. The current directory does not contain a 2026/27 NPFL file.
- The 2025/26 top-flight file declares 20 teams and 380 matches, contains 380 match rows, and identifies RSSSF's Nigeria 2025/26 page as its source. Its header says the source was retrieved on 2026-08-21.
- The 2025/26 file contains date-only match entries and no kickoff times. Do not invent kickoff times or UTC timestamps from those dates.
- Rights conflict: OpenFootball describes its repository data as CC0, but the NPFL file specifically cites RSSSF. RSSSF's Charter says archive data are subject to copyright, and the Nigeria 2025/26 page carries an RSSSF copyright notice. The upstream rights chain is therefore unresolved; do not train on, persist as a production dataset, or redistribute this RSSSF-derived file based only on the repository-level CC0 claim.
- Official references: https://github.com/openfootball/world/tree/master/africa/nigeria ; https://www.rsssf.org/charter.html ; https://www.rsssf.org/tablesn/nig2026.html

#### Official NPFL website — current-season discovery and manual verification candidate

- The official NPFL Fixtures & Results page publishes the 2026/27 season, including completed matches and upcoming fixtures from August through November 2026. It displays match date/time, teams, score/result, stadium and matchday. The current page includes fixtures/results through the November 29 schedule.
- Displayed timestamps include seconds (for example, `2026-11-15 16:00:10`) and the page also displays local-style times such as 4:00 pm. No explicit timezone definition or API publication timestamp was found. Do not assume these timestamps are UTC or WAT until the league confirms their semantics.
- The public page exposes no API documentation, terms of service, data licence, retention grant, or model-training permission. No automated extraction, persistence, training or public republication is approved.
- Decision: official NPFL site is the best current-season reference for manual fixture/result verification and team-name/stadium reconciliation. It is not yet a production ingestion source. Seek written permission for automated use and timezone clarification before building an adapter.
- Official reference: https://npfl.com.ng/fixtures-results/

#### NPFL operational consequence

- Nigeria can be added to VELTRIX's candidate competition map, but it must not be used to fill the 25-fixture daily quota.
- Current-season fixture discovery is possible, but model publication requires approved historical results, stable team identities, reliable kickoff timezone and sufficient point-in-time feature history.
- The RSSSF/OpenFootball file cannot satisfy those conditions by itself. The official NPFL website currently provides stronger current-season schedule/result visibility, but rights and timestamp semantics remain unresolved.


#### 5DollarFootballAPI Nigeria Premier Football League — newly confirmed coverage

- The official Pro coverage table lists Nigeria Premier Football League as league ID `3427505320`.
- The official data-quality table reports 207 finished matches in its rolling 12-month window; corners 95.2%, half-time corners 95.2%, corner line 50%, odds 95.2%, event timeline 95.2% and live statistics 95.2%. Its recorded history starts in 2015 across 13 seasons.
- These are provider-published completeness measurements, not an independent VELTRIX reconciliation. The data-quality snapshot was generated 2026-11-07 05:05 UTC and uses a 365-day window.
- Nigeria is therefore a real 5Dollar competition, unlike the RSSSF-derived OpenFootball file whose upstream rights are unresolved. Pro access is paid, but Community Access offers the top-five plus one selected country's whitelisted leagues at $0. Nigeria's eligibility in the Community country-pack selector has not been confirmed from the public page; verify the available country choices and then verify `/v1/status` reports `plan: community` before assuming access.
- The 207-match rolling-12-month sample is below VELTRIX's 1,000 held-out-match certification threshold per market. Community Access only supplies the last 12 months, so it cannot by itself provide a certifiable NPFL walk-forward sample. The 13-season archive is advertised in the Pro coverage data-quality page, but is not an entitlement of Community. Do not certify NPFL markets using only Community history.
- The Free account cannot access Nigeria merely because the Pro coverage table lists it. Do not add the NPFL to the current Free workflow or treat a Pro league ID as an entitlement.
- Official references: https://5dollarfootballapi.com/docs/league-coverage ; https://5dollarfootballapi.com/docs/data-quality ; https://5dollarfootballapi.com/community
