# VELTRIX FOOTBALL 2.0 — 5DollarFootballAPI historical odds PIT source review

Review date: 2026-11-15.

## Rights basis

Provider Terms (October 2026): https://5dollarfootballapi.com/terms

The Terms permit data use in models and internal tools, caching/storing responses, and display in user-facing products, while prohibiting redistribution of raw data as a competing feed. Free/Community/Education public-facing products require attribution. The planned use is private model research and internal storage; no raw-feed redistribution.

## Timestamped historical data

Official endpoint: GET /v1/fixtures/{id}/odds/history?market=1x2

The provider documents full pre-match and in-play price ticks, oldest first, each with a UTC recorded_at timestamp, score state, line and prices. Ticks can therefore be reconstructed strictly as-of a historical forecast cutoff. Pre-match features must exclude any in-play tick and any tick at or after kickoff. Null/suspended ticks are preserved as evidence but never converted into prices.

The endpoint requires Ultra. Free and Pro plans receive HTTP 403 insufficient_plan. The provider documents history windows of three months on Free, twelve months on Pro and complete supported history back to 2014 on Ultra. Actual season/market coverage varies by competition.

## Approval state — 2026-11-15

A separate non-commercial staging approval is now recorded:
- Approval ID: `approval-5dollar-community-odds-quote-noncommercial-2026-11-15`
- Data type: `odds_quote`; permitted uses include COLLECTION, STORAGE, MODEL_TRAINING and BENCHMARKING.
- Competition scope: the seven already-approved canonical competition IDs.
- `commercial_use_allowed=false`; raw redistribution prohibited.
- Terms version: October 2026; evidence hash is the existing legal terms review hash.
- An append-only `APPROVED` status event was recorded.

The project owner has separately imposed a project-wide non-commercial rule. VELTRIX will not monetise any source data, regardless of broader permissions in upstream provider terms.

## Current account status and decision

The account's Community opening 1X2 route has now completed its first bounded staging capture. Workflow #43727509783 made 25 fixture requests (26 total including status preflight), inserted 25 Bet365 1X2 opening observations, and passed the independent staging read-back. The workflow is capped at 25 fixture requests per run, 90-day lookback, no retries, 3.1-second pacing and no schedule.

The 90-day seven-competition fixture universe contains 763 eligible fixtures. The first batch covers 25/763 (3.28%); 738 remain without a captured opening quote. All 25 inserted observations retain the provider's explicit UTC `opened_at`, retrieval time, kickoff, raw response hash and rights approval; independent read-back confirmed 25/25 timestamp-order and canonical identity checks. The workflow reports 25 PIT-eligible quotes, but this is only a bounded source subset, not 98% market coverage or model certification.

The full tick-history endpoint `/fixtures/{id}/odds/history?market=1x2` remains documented as Ultra-only. No Ultra entitlement, historical tick request or subscription change has been made. No closing/in-play timestamps are exposed in this fixture response, so no closing-line or price-movement/CLV reconstruction is supported.

**Disposition:** first opening 1X2 batch VERIFIED in staging; universe coverage PARTIAL at 3.28%; full tick history BLOCKED by current plan entitlement. Existing fixture-result rows remain non-PIT for pre-match feature reconstruction; do not fabricate their publication times.


## 2X. Community Access opening 1X2 quote — timestamped subset

The provider's per-fixture odds endpoint is available on Free and Community Access. Its 1X2 opening object carries home/draw/away prices and an explicit UTC opened_at timestamp. That timestamp is a valid point-in-time quote time when it is timezone-aware, no later than retrieval, and strictly before kickoff.

The Community Access 12-month dataset can therefore supply one timestamped Bet365 1X2 opening quote per fixture without Ultra. This is not full odds tick history:
- closing and in-play snapshots in the fixture response do not expose their own quote timestamps and must not be treated as timestamped observations;
- no CLV or price-movement path can be reconstructed from opening-only data;
- the 1X2 benchmark cutoff must be the quote's opened_at time, not an assumed later 06:00 report time;
- quote coverage must be measured per fixture and must reach the certification target; do not infer 98% from the provider's general coverage claims.

The parser is connected to the staging capture and persistence path. Focused tests passed (26 passed in 0.15s) in workflow #43727509783. The independent read-back confirms all 25 stored rows have `source_timestamp_basis=provider_timestamp`, `availability_basis=provider_opening_timestamp`, `source_published_at=available_at=opened_at`, `opened_at < kickoff_at`, and `retrieved_at >= opened_at`; all 25 match their exact canonical fixture identity. It does not solve historical team-form result availability or full CLV/tick-history coverage.


## First Community opening-odds capture — 2026-11-15
- Workflow: [#43727509783](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783), commit `70b1a8ef1742975464f74dfefcf8dac265d46d86`, conclusion `success`.
- Focused tests: 26 passed in 0.15s. Fresh Community quota preflight: 300/hour, 20/minute, remaining 299; 25 fixture requests; remaining 274 after capture; no retries.
- Staging artifact: [#14166689086](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783/artifacts/14166689086); ZIP SHA-256 `b8a6b0594294fdd4b6178ebab0e010c2a30fb15b87686c3ba30457dae82fd171`; summary JSON SHA-256 `f519f8c6cb085a1a04afdb8f7582ddb8c2fb1813eb2a4914345cc9e322ccdb54`.
- Staging DB read-back: manifest 109; 25 request records, 25 provider responses and 25 source observations. Observation IDs 431621–431645; response IDs 462–486.
- All 25 are timestamped Bet365 1X2 opening quotes with valid prices, exact canonical fixture crosswalk, provider opening timestamp strictly before kickoff, and retrieval after the opening timestamp. The separate source_effective_at field is null.
- 90-day universe: 763 fixtures across seven approved competitions; 25 captured (3.28%), 738 remain. Per competition: Brazil Serie A 1/115; Brazil Serie B 10/151; England Premier League 6/100; France Ligue 1 2/90; Germany Bundesliga I 0/81; Italy Serie A 0/110; Spain La Liga 6/116.
- Crosswalk gate: 763/763 fixtures have exactly one active RESOLVED mapping; zero missing or ambiguous. All 25 captured quote identities match.
- Historical odds gate: zero 5Dollar historical tick observations; full endpoint remains Ultra-only and unentitled. The Odds API has 3 sports-catalogue responses and zero event/historical odds responses. 98% quote-coverage gate is not met; no CLV or price-movement evidence.
- No production writes, deployment, publication, Telegram send or schedule activation.
