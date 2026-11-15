# VELTRIX FOOTBALL 2.0 — Stage 2 final exit decision

**Decision date:** 2026-11-15  
**Decision:** **NO-GO — STAGE 2 EXIT CRITERIA NOT MET**  
**Repository:** Nexora-Apparel/veltrix-football  
**Branch:** integration/v2-report-bundle-wiring-20261114  
**PR #120:** Draft, open, unmerged  
**Staging target:** Neon project withered-sky-75161174 / branch br-silent-violet-bc5de88s / database veltrix_football_staging

## 1. Decision

Stage 2 exit is denied at this checkpoint. The acquisition and qualification work is materially advanced, but the evidence is not sufficient for Stage 2 completion, model certification, value betting, or production release. Continue only the remaining Stage 2 work. Stage 3 remains on hold.

This is a definitive no-go decision against the current evidence set, not a declaration that the project is permanently blocked. Reconsider only after the outstanding criteria below are independently evidenced and this decision is superseded by a new signed-off report.

## 2. Opening-odds evidence — reconciled

The fixed 90-day, seven-competition universe contains 763 eligible 5Dollar fixtures. Manifests 109–121 are independently reconciled in the named staging database:

| Manifest | Workflow run | Requests | HTTP responses | Opening observations | Distinct fixtures | PIT eligible |
|---:|---:|---:|---:|---:|---:|---:|
| 109 | 43727509783 | 25 | 25 | 25 | 25 | 25 |
| 110 | 43731726029 | 25 | 25 | 25 | 25 | 25 |
| 111 | 43732404388 | 25 | 25 | 25 | 25 | 25 |
| 112 | 43732592388 | 25 | 25 | 25 | 25 | 25 |
| 113 | 43732760908 | 25 | 25 | 25 | 25 | 25 |
| 114 | 43732926602 | 25 | 25 | 25 | 25 | 25 |
| 115 | 43733133345 | 25 | 25 | 25 | 25 | 25 |
| 116 | 43733321610 | 25 | 25 | 25 | 25 | 25 |
| 117 | 43733520229 | 25 | 25 | 25 | 25 | 25 |
| 118 | 43733721786 | 25 | 25 | 25 | 25 | 25 |
| 119 | 43733924743 | 25 | 25 | 25 | 25 | 25 |
| 120 | 43734128538 | 25 | 25 | 25 | 25 | 25 |
| 121 | 43734327570 | 25 | 25 | 25 | 25 | 25 |
| **Total** | | **325** | **325** | **325** | **325** | **325** |

Independent aggregate read-back confirms 325/325 distinct provider fixture IDs map to canonical fixtures, are PIT eligible, preserve valid opening timestamp ordering, use Bet365 1X2, and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found in these thirteen manifests.

**Coverage:** 325/763 = 42.60%. 438 fixtures remain without a captured opening quote. At least 748 timestamped quotes are required to reach 98% of this denominator, so at least 423 additional valid quotes are still required. The full acquisition target remains 438 additional quotes.

All thirteen batches were capped at 25 fixture requests, used a fresh Community quota preflight, used no automatic retries, retained the provider's opening timestamp and were written only to staging. The latest completed batch is workflow #43734327570, artifact #14170016337, SHA-256 `f752a53019de07e1a3b3c23b139fc5edf5f0d20dbe8e3bc2b06ff4912751a559`.

## 3. Second-batch persistence discrepancy — resolved

The earlier discrepancy arose from querying `odds_quote_observations`, a separate normalized representation, rather than the acquisition write target `source_observations`. Read-only reconciliation through `provider_capture_requests` → `provider_responses` → `source_observations` confirms manifests 109 and 110 each contain 25 persisted opening observations. No provider request was repeated to diagnose the discrepancy. The capture workflow commits each observation and the aggregate read-back agrees with its reported insertion count.

## 4. Historical and closing-odds evidence — blocked

- 5Dollar Community per-fixture odds provides a timestamped opening 1X2 quote through `opened_at`. It does not provide independently timestamped closing/in-play ticks in that response.
- 5Dollar full tick-history endpoint `/fixtures/{id}/odds/history?market=1x2` is documented as Ultra-only. The account's Ultra entitlement is not evidenced; no request was made.
- The Odds API V4 is a technically acceptable alternative for timestamped historical snapshots, but historical odds access is paid-plan-only and the connected account's entitlement, UK bookmaker coverage and event/market availability have not been verified.
- The Odds API has catalogue-only evidence; zero event-odds and zero historical-odds responses are stored. No credit-consuming request was made.
- Five-minute historical snapshots can support a labelled near-close snapshot benchmark, not a claim of the exact final closing tick. No CLV or tick-perfect price movement evidence exists.

Formal source decision: **BLOCKED — ENTITLEMENT NOT VERIFIED**. The detailed evidence and usage guard are in `docs/VELTRIX_V2_HISTORICAL_CLOSING_ODDS_ENTITLEMENT_DECISION_2026-11-15.md`.

## 5. Other evidence and temporal restrictions

- 5Dollar fixture crosswalk: 763/763 eligible fixtures have exactly one active RESOLVED mapping; zero missing or ambiguous.
- Community fixture/result qualification: 2,505/2,505 labels qualified across seven competitions, but they remain non-PIT for pre-match features because exact source publication-time evidence is absent.
- OpenFootball and FootballData archives passed artifact verification, but their observations remain retrospective/non-PIT; no backdating is allowed.
- The historical results archive contains 2,496 records with no source publication/recorded timestamps; PIT-certifiable count is zero.
- OpenPlay's staging-only feature extraction pipeline is implemented and its derived bundle was verified as a sidecar. Its identity crosswalk remains partial: 89/422 teams and 5/22 competitions in the recorded audit; unresolved identities stay quarantined. It is not evidence that all OpenPlay data is available for model evaluation.
- Prospective paper evidence remains insufficient for market certification: the previously audited ledger had 25 shadow fixtures, zero settlements and zero settled dates. Required thresholds include at least 1,000 chronological walk-forward samples per market, 300 prospective settled selections, 90 distinct dates, 98% timestamped odds coverage, positive net ROI with positive lower 95% ROI bound, and 1X2 beating bookmaker Brier score and log loss.

## 6. Exit-gate matrix

| Gate | Decision | Reason |
|---|---|---|
| Provider rights and non-commercial scope | PASS within documented limits | Explicit approvals; attribution required; raw redistribution prohibited; no monetisation |
| 5Dollar fixture/result qualification | PASS as settled labels only | 2,505 labels; explicitly non-PIT |
| OpenFootball / FootballData archive verification | PASS as artifacts only | Verified, but retrospective/non-PIT |
| OpenPlay staging feature bundle | PASS as staging sidecar | Verified derived bundle; identity coverage remains partial |
| 5Dollar fixture crosswalk | PASS | 763/763 exact active RESOLVED mappings |
| 5Dollar opening-odds persistence | PASS | 325/325 independently read back |
| Opening-odds coverage | FAIL / INCOMPLETE | 42.60%; 423 more to reach 98%; 438 to complete universe |
| Historical/closing odds entitlement | BLOCKED | 5Dollar Ultra not evidenced; Odds API paid historical access unverified |
| CLV / closing-line benchmark | NOT MET | Zero timestamped closing or historical snapshots |
| Walk-forward and prospective certification | NOT MET | Sample, settlement, date, odds-coverage and benchmark thresholds unmet |
| Stage 2 exit | **NO-GO** | Multiple mandatory evidence gates remain open |

## 7. Mandatory next actions

1. Continue the fixed 763-fixture opening-odds universe in sequential batches of no more than 25, with fresh quota preflight, 3.1-second pacing, no retries and staging-only persistence. Reconcile every manifest before the next batch is triggered.
2. Verify The Odds API paid historical endpoint entitlement and UK bookmaker/market coverage through account evidence. If available, authorize a separately capped one-request/one-region/one-market staging probe (maximum documented estimate 10 credits), no retries, with exact snapshot timestamp and quota headers. Do not spend credits without explicit authorization.
3. Keep 5Dollar tick history blocked until Ultra entitlement is evidenced. Do not attempt a restricted request.
4. Complete OpenPlay identity resolution only from evidence-backed IDs/aliases and wire only the verified staging feature sidecar into chronological evaluation. Do not promote retrospective data into historical PIT features.
5. Accumulate prospective settled selections and distinct dates, run chronological walk-forward evaluation, and evaluate each market against the required benchmarks.
6. Reissue Stage 2 exit report only after all required evidence is independently reconciled. Until then, do not start Stage 3.

## 8. Release safety

PR #120 remains draft/open/unmerged. No production database writes, production deployment, public prediction publication, Telegram delivery, schedule activation, or value-betting unlock is authorized. Keep all these controls fail-closed.

**Final Stage 2 decision: NO-GO — NOT COMPLETE / NOT RELEASE-READY.**

## 9. Acquisition continuation update — 2026-11-15

Manifests 117–119 have since completed and independently reconciled, bringing the total to 275/763 (36.04%) opening quotes across 275 distinct fixtures. Each new manifest has 25/25 requests, responses, observations and PIT-eligible fixtures. The 98% threshold requires at least 473 more valid quotes; full acquisition requires 488. Manifest 120 is currently in progress and is not included in this verified total. The Stage 2 decision remains NO-GO.


## 10. Acquisition continuation update — 2026-11-15

Manifest 120 has completed and independently reconciled, bringing the total to 300/763 (39.32%) opening quotes across 300 distinct fixtures. Manifests 109–120 each have 25/25 requests, responses, observations and PIT-eligible fixtures. The 98% threshold requires at least 448 more valid quotes; full acquisition requires 463. The next batch trigger is being advanced separately and will not be counted until independently reconciled. The Stage 2 decision remains NO-GO.


## 11. Acquisition continuation update — 2026-11-15

Manifest 121 has completed and independently reconciled, bringing the total to 325/763 (42.60%) opening quotes across 325 distinct fixtures. Manifests 109–121 each have 25/25 requests, responses, observations and PIT-eligible fixtures. The 98% threshold requires at least 423 more valid quotes; full acquisition requires 438. The next batch trigger is being advanced separately and will not be counted until independently reconciled. The Stage 2 decision remains NO-GO.


## 12. Acquisition continuation update — 2026-11-15

Manifest 123 has completed and independently reconciled, bringing the total to 375/763 (49.15%) opening quotes across 375 distinct fixtures. Manifests 109–123 each have 25/25 requests, responses, observations and PIT-eligible fixtures. The 98% threshold requires at least 373 more valid quotes; full acquisition requires 388. The next batch trigger is being advanced separately and will not be counted until independently reconciled. The Stage 2 decision remains NO-GO.


## 13. Acquisition continuation update — 2026-11-15

Manifest 124 has completed and independently reconciled, bringing the total to 400/763 (52.42%) opening quotes across 400 distinct fixtures. Manifests 109–124 each have 25/25 requests, responses, observations and PIT-eligible fixtures. The 98% threshold requires at least 348 more valid quotes; full acquisition requires 363. The latest Community quota read-back is 16 remaining, below the next batch's required preflight headroom of 26. The next run must wait for the provider's quota reset at 17:00 UTC and must obtain a fresh preflight. The Stage 2 decision remains NO-GO.


## Stage 2 final evidence addendum — 2026-11-15 (supersedes earlier interim counts)

### Opening-odds persistence and acquisition reconciliation

The earlier apparent discrepancy was caused by querying the normalized `odds_quote_observations` table instead of the capture workflow's raw provenance table, `source_observations`. The acquisition workflow writes the source observation and links it to `provider_responses`; normalization into the separate quote table is not the capture persistence contract. No provider request was repeated to diagnose this.

Read-only verification on Neon project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`, schema `public`, role `neondb_owner`:
- Manifests 109–124: 16 completed batches.
- 400/400 capture request rows; 400/400 HTTP 200 provider responses; 400/400 linked `source_observations` rows.
- 400 distinct provider fixture IDs; 400 unique payload hashes; 400 PIT flags.
- Independent fixture join: 400/400 match canonical 5Dollar fixture IDs; zero missing identities.
- 400/400 Bet365 1X2 quotes; 400/400 provider `opened_at` timestamps precede canonical kickoff; 400/400 retrieval timestamps follow opening time.
- Observation IDs 431621–432020. No provider calls were repeated for this reconciliation.

The separate normalized `odds_quote_observations` table is not the acquisition write target and its zero count is not evidence of failed capture persistence. Do not use that table's count as the raw capture acceptance criterion.

### Coverage and quota

The predeclared 90-day universe is 763 fixtures across the seven approved competitions. Captured: 400/763 = 52.42%; outstanding: 363. The 98% threshold requires at least 748 valid observations, leaving a further 348 needed. Competition counts: Brazil Serie A 58/115; Brazil Serie B 95/151; England Premier League 50/100; France Ligue 1 45/90; Germany Bundesliga I 36/81; Italy Serie A 50/110; Spain La Liga 66/116.

The last persisted provider response reports 16 requests remaining against the 300-request quota. This is below the required next-batch preflight headroom (25 fixture requests plus status check). Capture is paused until after the documented 17:00 UTC quota reset and a fresh quota preflight confirms sufficient headroom. Continue in batches of at most 25, 3.1-second pacing, no automatic retries, and independently reconcile each manifest before the next batch. No more requests are authorized by this addendum.

### Historical and closing-odds source determination

- 5DollarFootballAPI documents `GET /v1/fixtures/{id}/odds/history` as Ultra-only; Free and Pro receive 403 insufficient_plan. No Ultra entitlement evidence exists for this account. The restriction is therefore an entitlement blocker, not a code defect. See https://5dollarfootballapi.com/docs/odds-history.
- The Odds API documents historical snapshots at 10-minute intervals initially and 5-minute intervals from September 2022; historical endpoints require a paid usage plan. VELTRIX's persisted account evidence remains catalogue-only: three `/v4/sports/` responses, zero odds/event-odds responses and zero historical-odds responses. Sport-key catalogue access does not establish paid historical endpoint, UK bookmaker, league, market or timestamp coverage. See https://the-odds-api.com/liveapi/guides/v4/.
- Independent candidates identified but not accepted: SockOdds advertises recorded price changes/opening/closing history on Pro and states its archive starts 22 Dec 2025 for listed leagues and 8 Oct 2026 elsewhere; coverage and entitlement for all seven VELTRIX competitions are not yet verified. See https://sockodds.com/use-cases/historical-odds-data-api/.
- Odds-API.io advertises historical closing lines since December 2025 and currently lists Premier League, LaLiga, Serie A, Bundesliga, Ligue 1 and Brazil Serie A, but the published list does not establish Brazil Serie B coverage. No account, contract/rights, API response, identity crosswalk, source timestamp, completeness or plan entitlement has been verified for VELTRIX. Treat as a research candidate only, not admissible certification evidence. See https://odds-api.io/historical-odds-api.

**Formal disposition:** no acceptable, account-entitled, seven-competition historical tick/closing source has been established. 5Dollar Ultra and The Odds API paid historical access remain unverified/blocked. The two alternative vendors remain candidates only. Do not ingest or count their marketing coverage claims as evidence. The limitation means no defensible historical price movement or CLV calculation can currently be certified; the 98% timestamped odds gate is also unmet at 52.42%. Opening quotes alone do not supply timestamped closing prices or line movement.

### Stage 2 exit decision

**NO-GO — Stage 2 remains OPEN / NOT COMPLETE / NOT RELEASE-READY.** The persistence discrepancy is resolved as a table-selection/audit-path misunderstanding, and 400 opening quotes are verified. However, only 52.42% of the 763-fixture universe is covered, the 98% threshold is not met, historical/closing odds entitlement is unresolved, CLV evidence is absent, and the market-specific walk-forward/prospective certification thresholds remain unmet. Stage 3, prediction publication, Telegram delivery, schedule activation, production deployment and value betting remain blocked.


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
