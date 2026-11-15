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


## Final acquisition and historical-odds entitlement update — 2026-11-15

The 16 opening-odds capture manifests (109–124) are now reconciled against the actual capture persistence target, `source_observations`, not the downstream normalized `odds_quote_observations` table. On the operational staging branch/database:
- 400/400 request rows, first attempt only; zero retries.
- 400/400 linked HTTP 200 responses and 400/400 raw source observations.
- 400 distinct provider fixture IDs and 400 unique payload hashes.
- 400/400 canonical fixture matches, PIT flags, Bet365 1X2 opening quotes and exact rights approval ID.
- 400/400 provider opening timestamps strictly before kickoff; retrieval after opening.

The persistence discrepancy is resolved as an audit-table mismatch; no provider calls were repeated. The 763-fixture denominator leaves 400/763 (52.42%) covered, 363 outstanding, and 348 additional valid observations needed to reach 98% (748/763).

Historical source disposition is unchanged and formally closed for this review cycle: 5Dollar tick history is Ultra-only and account entitlement is not evidenced. The Odds API historical snapshots are technically suitable if paid-plan access, relevant sport keys, UK bookmaker/market availability and returned timestamp coverage are verified; current VELTRIX evidence is catalogue-only and has zero event/historical odds responses. SockOdds and Odds-API.io are research candidates only; no account entitlement, legal/rights scope, exact seven-competition coverage, identity mapping or response evidence is available. Do not count them toward certification.

Latest quota read-back is 16 requests remaining; stop capture until after 17:00 UTC reset and a fresh preflight. No further provider request is made in this update. Stage 2 remains NO-GO: 52.42% is below 98%, no timestamped closing/near-close evidence or CLV exists, and model certification thresholds remain unmet.


### Opening-odds acquisition continuation — 2026-11-15 17:55 UTC

- Controlled capture manifests 109–135 are reconciled: 27 batches × 25 requests = 675 requests, 675 HTTP 200 responses, 675 persisted raw `source_observations`, 675 distinct provider fixture IDs and 675 distinct payload hashes.
- All 675 are PIT-certifiable opening quotes, have the exact approved non-commercial rights ID, resolve to active canonical fixture crosswalks, and pass Bet365 1X2 opening-price and pre-kickoff timestamp checks. Zero retries.
- The raw capture target is `source_observations`; `odds_quote_observations` is a separate downstream normalized table and is not the raw workflow's persistence target.
- Frozen 90-day universe: 763 fixtures. Coverage is 675/763 = 88.47%. The 98% gate requires at least 748 valid quotes; 73 additional observations are needed. 88 fixtures remain uncaptured.
- Last persisted provider quota evidence after manifest 135: limit 300, remaining 14. No further provider calls are permitted until the next quota reset and a fresh quota preflight confirms sufficient headroom for one full batch.
- Latest completed capture run: 43743516430; manifest 135; artifact 14172798183. Capture job and aggregate artifact upload succeeded.
- CI on the capture head passed: Phase 2 foundation, PostgreSQL 16/18 acceptance, Phase 5 Shadow Regression, Certification Evidence Integrity and Historical Model Audit. Daily Fixture Predictions was skipped as intended.
- Historical/closing odds source remains unqualified: 5Dollar history requires Ultra; The Odds API has only catalogue evidence in this account; SockOdds and Odds-API.io remain unverified candidates. No closing-price or CLV evidence is admitted.
- **Stage 2 remains NO-GO / OPEN / NOT RELEASE-READY.** 88.47% is below 98%; closing odds/CLV and model certification thresholds remain unmet. Stage 3, production deployment, prediction publication, Telegram delivery, schedule activation and value betting remain disabled.


### Competition-level opening-quote reconciliation — manifest 135

| Competition | Frozen universe | Captured | Remaining |
|---|---:|---:|---:|
| Brazil Serie A | 115 | 105 | 10 |
| Brazil Serie B | 151 | 134 | 17 |
| England Premier League | 100 | 88 | 12 |
| France Ligue 1 | 90 | 78 | 12 |
| Germany Bundesliga I | 81 | 71 | 10 |
| Italy Serie A | 110 | 96 | 14 |
| Spain La Liga | 116 | 103 | 13 |
| **Total** | **763** | **675** | **88** |

Counts are grouped by canonical fixture competition through the active crosswalk. No competition is omitted; all 88 remaining fixtures are still in the frozen capture universe.


### Final 90-day opening-odds acquisition — 2026-11-15 18:07 UTC

**Opening-quote coverage: COMPLETE.**

- Final manifest 139 captured the 13 residual fixtures; all 13 requests returned HTTP 200 and persisted 13 source observations. Zero retries.
- Manifests 109–139: 31 controlled batches; 30 × 25 plus the final 13 = **763/763** requests, responses and raw observations.
- Independent final reconciliation: 763 distinct provider fixture IDs; 763 unique payload hashes; 763 PIT-certifiable records; 763 exact rights approvals; 763 active resolved canonical fixture crosswalks; 763 valid Bet365 1X2 opening quotes with opening timestamps before kickoff and available by retrieval.
- Competition totals exactly reconcile to the frozen universe: Brazil Serie A 115/115; Brazil Serie B 151/151; England Premier League 100/100; France Ligue 1 90/90; Germany Bundesliga I 81/81; Italy Serie A 110/110; Spain La Liga 116/116.
- Opening-quote coverage is **100% (763/763)** and exceeds the 98% coverage gate. Latest stored quota evidence after manifest 139: 208/300 remaining.
- Latest completed capture run #43744662625; manifest 139; artifact #14173509833. Capture job and aggregate-only artifact upload succeeded.
- CI on the capture head passed Phase 2 Data Foundation, PostgreSQL 16/18 acceptance, Phase 5 Shadow Regression, Certification Evidence Integrity and Historical Model Audit. Daily Fixture Predictions was skipped as intended.

**Important boundary:** this completes the 90-day timestamped *opening-odds* acquisition only. It does not establish historical closing prices, line movement or CLV. The 5Dollar history endpoint remains Ultra-only; The Odds API account evidence remains catalogue-only; alternative vendors remain unverified. No acceptable historical/closing-odds evidence source has been qualified.

**Final Stage 2 exit decision remains NO-GO — OPEN / NOT COMPLETE / NOT RELEASE-READY.** The opening-odds coverage gate is now PASS. Historical/closing odds and CLV remain BLOCKED/NOT MET, and the market-specific model certification thresholds (walk-forward sample counts, prospective settled selections/dates, positive ROI and confidence bound, and bookmaker benchmark superiority) remain unmet. Stage 3, production deployment, prediction publication, Telegram delivery, schedule activation and value betting remain disabled.


### Historical/closing-odds source re-evaluation — 2026-11-15

#### Best technical candidate: The Odds API (not yet entitled)

The official historical endpoint documentation now confirms coverage dates for all seven required competitions, including both Brazil leagues. The 763-fixture universe spans kickoff dates 2026-08-17 through 2026-11-11, so all seven provider history start dates predate the universe:

| Competition | Sport key | Public historical coverage start |
|---|---|---|
| Brazil Serie A | `soccer_brazil_campeonato` | 2020-07-28 |
| Brazil Serie B | `soccer_brazil_serie_b` | 2022-06-30 |
| England Premier League | `soccer_epl` | 2020-06-06 |
| France Ligue 1 | `soccer_france_ligue_one` | 2020-07-16 |
| Germany Bundesliga I | `soccer_germany_bundesliga` | 2020-06-06 |
| Italy Serie A | `soccer_italy_serie_a` | 2020-06-06 |
| Spain La Liga | `soccer_spain_la_liga` | 2020-06-06 |

Official docs: https://the-odds-api.com/historical-odds-data/ (featured-market 1X2/h2h snapshots; 10-minute snapshots initially and 5-minute snapshots since September 2022; nearest snapshot at or before requested timestamp; 10 credits per region per market). Historical odds are paid-plan-only. Official pricing: https://the-odds-api.com/ (Free: 500 credits/month, no historical odds; lowest paid START 20K: US$30/month, historical odds included).

Account evidence is not sufficient to accept it:
- The three persisted account responses are all quota-free `GET /v4/sports/?all=true` calls. Each shows `x-requests-used=205`, `x-requests-remaining=295`, `x-requests-last=0` (500 total credits). This is consistent with the published 500-credit Free tier, but the account probe intentionally records plan code as undisclosed.
- There are still zero persisted historical-odds responses and zero event-odds responses. The existing no-credit probe only calls `/v4/sports/?all=true`; it does not test paid historical entitlement.
- Existing source approval `approval-the-odds-api-v4-owner-authorized-2026-11-14` is APPROVED for collection, storage, benchmarking, model training and public display, with commercial use allowed and raw redistribution prohibited. Its current competition scope contains only EPL, La Liga, Bundesliga, Serie A and Ligue 1; Brazil Serie A and Serie B are not yet covered by that approval.
- The provider's current terms permit storage, user-facing display, derived values and model training, including commercial use, but prohibit reselling/redistributing the raw feed: https://the-odds-api.com/terms-and-conditions.html (updated 31 Aug 2026).

**Determination:** The Odds API is now the strongest technically compatible full-universe candidate, but it is **not an accepted historical/closing source yet**. Paid historical entitlement, actual h2h response coverage/bookmaker availability, and a rights approval covering both Brazil competitions remain unverified. No paid plan has been purchased or activated.

#### OddsIntel Data — rejected for full-universe certification

Official coverage/pricing: https://data.oddsintel.app/coverage and https://data.oddsintel.app/pricing. It advertises 1X2 consensus closing prices and CLV grading, with Starter history since 10 Oct 2026 (90-day cap), Pro history from the same first match date, and no earlier data. The VELTRIX 763-fixture universe begins 17 Aug 2026: **415 fixtures kick off before 10 Oct; only 348 fall on/after 10 Oct**. It therefore cannot supply closing evidence for the complete frozen universe or meet the 98% threshold.

Additional limitations: it supplies consensus prices only (no bookmaker names or individual bookmaker quotes); takeable grading is marked unchecked; and its terms exclude betting operators and their affiliates and prohibit presenting CLV grading as a verified betting record. Starter is €49/month + VAT for internal business use; Pro is €149/month + VAT for displaying individual derived figures inside a product. Terms: https://data.oddsintel.app/terms.

**Determination:** Not accepted for this Stage 2 full-universe requirement. It may be considered only for a future, separately scoped consensus-close benchmark after legal/use-case eligibility is established; it cannot backfill the 415 pre-10-Oct fixtures.

SockOdds and Odds-API.io remain marketing-only candidates without VELTRIX entitlement, seven-competition response coverage, contract/rights approval or persisted evidence. No provider has yet supplied accepted historical/closing odds for the full 763-fixture universe.
