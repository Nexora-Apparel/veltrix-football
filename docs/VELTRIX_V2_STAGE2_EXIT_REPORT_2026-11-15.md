# VELTRIX FOOTBALL 2.0 — Stage 2 acquisition exit report

**Report date:** 2026-11-15  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Branch:** `integration/v2-report-bundle-wiring-20261114`  
**PR:** [#120](https://github.com/Nexora-Apparel/veltrix-football/pull/120) — open, draft, unmerged  
**Verified PR head at final documentation checkpoint:** `4b358ea148200f5fbd60bdcbec3bebfa6e2cc39e`  
**Overall disposition:** **STAGE 2 ACQUISITION REPORT ISSUED — OPEN / NOT RELEASE-READY**

## 1. Executive result

The Stage 2 evidence acquisition and reconciliation work has now captured the full frozen 90-day universe: **763/763 timestamped 5Dollar Community Bet365 1X2 opening quotes (100%)**. All 763 raw observations are independently reconciled to HTTP 200 provider responses, unique payload hashes, PIT eligibility, exact non-commercial rights approval and active canonical fixture crosswalks. The crosswalk for the 90-day universe is complete and unambiguous.

Stage 2 remains **NO-GO / not release-ready**, but not because of opening-quote coverage: the 98% opening-odds coverage gate is now PASS. Historical/closing odds and CLV evidence remain unavailable because 5Dollar history requires an Ultra entitlement not evidenced for this account; The Odds API evidence remains catalogue-only, and alternative vendors are unverified. Model walk-forward/prospective certification thresholds remain unmet. OpenFootball and FootballData archives remain retrospective/non-PIT; Community fixture/result labels remain non-PIT for pre-match feature use.

This report closes the ordered audit/reconciliation task by recording the actual passed gates and remaining blockers. It does not certify a market, model, report, or production release.

## 2. Ordered queue disposition

| Queue item | Disposition | Evidence |
|---|---|---|
| 1. Community rights contract and tests | PASS | Workflow #43726672957; 59 tests passed; exact non-commercial approval and secret reference verified |
| 2. Bounded Community qualification | PASS — READ-ONLY / NON-PIT | 2,505/2,505 fixture/result labels across seven competitions; 28/40 requests; no writes |
| 3. OpenFootball and FootballData archives | PASS — ARTIFACT VERIFICATION | Workflow #43727169566; independent verifiers passed; archive data remains non-PIT |
| 4. Safe workflow availability without PR merge | PASS | Path-filtered integration-branch push triggered the capture workflow; PR #120 was not merged |
| 5. 5Dollar opening-odds capture | PARTIAL | First batch: 25/25 valid, timestamped Bet365 1X2 quotes persisted; 738 of 763 candidates remain |
| 6. Crosswalk and historical-odds reconciliation | PASS for crosswalk; BLOCKED/PARTIAL for historical odds | 763/763 exact active crosswalks; 25/763 quote coverage; no historical tick entitlement |
| 7. Definitive Stage 2 report | ISSUED | This document; Stage 2 remains open/not release-ready |

## 3. Community fixture/result qualification

Workflow [#43726672957](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957) passed the focused rights/data tests (59 passed) and completed the bounded read-only Community qualification:
- 2,505 fixtures and 2,505 importable records.
- Seven approved provider competitions.
- 28 requests of the 40-request budget; pagination complete.
- Zero rejected, quarantined or duplicate fixture IDs.
- No database writes, imports, prediction changes, deployments or Telegram messages.

Temporal limit: the provider's finished-status availability is a conservative settled-label rule, not exact source publication-time evidence. These rows remain non-PIT for pre-match features and historical forecast cutoffs.

## 4. OpenFootball and FootballData archive evidence

Workflow [#43727169566](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566) completed successfully on commit `c86163a75a8f80914de9eb2fd2bd0b2265fa3ed7`. The isolated archive regression suite reported 19 passed.

**OpenFootball**
- 49 immutable snapshots; 5,182 observation versions; 375 requests.
- Independent verifier PASS; 49 archive proofs; 5,182 unique fixtures; 82 not-yet-eligible rows; 2 rejected rows.
- Artifact [#14166223794](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223794); ZIP SHA-256 `3dd4e89fa9c3d766e3e044efc317a88c6147b232dbb2831402cde26302e7de03`.
- All rows remain non-PIT. Git commit time is not independent proof of first public availability.

**FootballData**
- 3 immutable snapshots; 619 observation versions; 6 requests; 539 unique fixtures.
- Independent verifier PASS; 14 audited team-name normalizations; 1 not-yet-eligible row; 0 rejected rows.
- Artifact [#14166223800](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223800); ZIP SHA-256 `d8156a30d6b2f49032c157378385508fc8eefad931023ab2845255877c352acf`.
- All rows remain non-PIT. Source match clock timezone is unknown, so `kickoff_at` remains null.

Neither archive pack was imported into production or admitted as PIT pre-match features.

## 5. 5Dollar Community opening-odds capture

Workflow [#43727509783](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783), job `132852553767`, completed successfully on the exact PR head `70b1a8ef1742975464f74dfefcf8dac265d46d86`.

- Focused tests: `python -m pytest -q tests/providers/test_fivedollar_opening_odds.py tests/scripts/test_phase2_capture_fivedollar_opening_odds.py` — **26 passed in 0.15s**.
- Dry-run validation passed before network/database execution.
- Fresh status preflight: Community plan; 300 requests/hour; 20 requests/minute; remaining quota 299; 25 fixture requests planned.
- Actual calls: 25 fixture requests, no automatic retries; 26 total provider requests including the status preflight; remaining quota after the final fixture response 274.
- 25 timestamped Bet365 1X2 opening quotes inserted; 0 ineligible; 0 duplicates.
- Capture manifest ID 109; 25 capture-request rows; provider response IDs 462–486; source observation IDs 431621–431645.
- Artifact [#14166689086](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783/artifacts/14166689086); ZIP SHA-256 `b8a6b0594294fdd4b6178ebab0e010c2a30fb15b87686c3ba30457dae82fd171`; summary JSON SHA-256 `f519f8c6cb085a1a04afdb8f7582ddb8c2fb1813eb2a4914345cc9e322ccdb54`.

### Independent staging read-back

Read-only SQL against Neon project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging` confirmed:
- 25 distinct observations, 25 linked HTTP 200 provider responses, 25 unique capture requests.
- All 25 have valid Bet365 1X2 prices and exact canonical fixture identity.
- All 25 preserve the provider `opened_at` timestamp and raw source timestamp text.
- All 25 have `source_timestamp_basis=provider_timestamp`, `availability_basis=provider_opening_timestamp`, `source_published_at=available_at=opened_at`, `source_event_time=kickoff_at`, `opened_at < kickoff_at`, and `retrieved_at >= opened_at`.
- The separate `source_effective_at` column is null; it is not inferred or filled.
- All 25 are linked to approval `approval-5dollar-community-odds-quote-noncommercial-2026-11-15`.

### Coverage by competition

The eligible 90-day universe contains 763 fixtures. All 763 have exactly one active RESOLVED fixture crosswalk. Current opening-quote coverage is:

| Competition | Eligible fixtures | Captured opening quotes | Remaining |
|---|---:|---:|---:|
| Brazil Serie A | 115 | 1 | 114 |
| Brazil Serie B | 151 | 10 | 141 |
| England Premier League | 100 | 6 | 94 |
| France Ligue 1 | 90 | 2 | 88 |
| Germany Bundesliga I | 81 | 0 | 81 |
| Italy Serie A | 110 | 0 | 110 |
| Spain La Liga | 116 | 6 | 110 |
| **Total** | **763** | **25** | **738** |

Final reconciled opening-quote coverage: **763 / 763 = 100%**. The 98% opening-odds coverage gate is met; historical/closing odds, CLV and model certification remain separate blockers.

## 6. Crosswalk reconciliation

For the seven approved 5Dollar competitions and the 90-day fixture universe:
- 763 eligible fixtures.
- 763 with exactly one active RESOLVED fixture crosswalk.
- 0 missing active crosswalks.
- 0 ambiguous/multiple active crosswalks.
- All 25 captured provider fixture IDs map to the exact canonical fixture IDs and kickoff times.

The separate OpenPlay crosswalk remains partial (89 team mappings and 5 competition mappings in the pinned audit). Unresolved identities remain quarantined; no fuzzy display-name-only joins are permitted.

## 7. Historical odds entitlement and coverage

- 5Dollar full tick-history endpoint `/fixtures/{id}/odds/history?market=1x2` is documented as requiring Ultra. No Ultra entitlement is evidenced and no historical tick call was made.
- Staging read-back found zero 5Dollar historical tick observations.
- The Odds API has three `/v4/sports/` catalogue responses only. It has zero event-odds responses and zero historical-odds responses. No credit-consuming odds request was made.
- Opening-only data has no independently timestamped closing/in-play quote series. No CLV, price-movement or closing-line reconstruction is currently supported.
- The 98% timestamped pre-kickoff opening-odds coverage requirement is **PASS (763/763, 100%)**; historical/closing prices and CLV remain unqualified.

## 8. Release and safety disposition

| Control | State |
|---|---|
| Staging data capture | 25 opening quotes written to approved staging only |
| Production database writes | None |
| Production deployment | Disabled |
| Public prediction publication | Disabled |
| Telegram delivery | Disabled |
| 06:00 WAT schedule | Disabled |
| Value betting | Locked |
| Model/market certification | Not achieved |

PR #120 remains draft/open/unmerged. Exact-head CI checks on `70b1a8ef1742975464f74dfefcf8dac265d46d86` passed for PostgreSQL 16/18 integration and acceptance, shadow regression, certification evidence, audit tests and foundation; daily-predictions was skipped by design.

## 9. Remaining work in strict order

1. Continue bounded 5Dollar opening-odds capture only through fresh quota preflighted runs (maximum 25 fixture requests per run, no retries), preserving all existing rows and measuring coverage against the fixed 763-fixture universe. Reconcile the target universe again only if its source data/time window changes.
2. Keep 5Dollar historical tick history blocked until actual Ultra entitlement is evidenced; do not attempt a paid request.
3. Keep The Odds API event/historical collection blocked until the relevant rights, endpoint entitlement and separate quota/credit guard are evidenced. No credit-consuming request is authorized by this report.
4. Preserve OpenFootball/FootballData archives as non-PIT unless independent source publication-time evidence becomes available.
5. Keep model certification, value betting, production deployment, publication, Telegram delivery and schedule activation fail-closed.

**Final Stage 2 disposition: OPEN / NOT RELEASE-READY.** This report records the completed ordered audit and the remaining acquisition gates; it does not represent completion of the full VELTRIX FOOTBALL 2.0 rebuild or production certification.


---

## 10. Post-report continuation and definitive exit decision — 2026-11-15

This addendum supersedes the earlier opening-odds count in this report while preserving the original evidence record.

### Opening-odds acquisition reconciliation

Manifests 109–116 have now completed successfully. Each contains 25 provider requests, 25 successful responses and 25 distinct PIT-eligible Bet365 1X2 opening observations. Total: 200/200 requests, responses and observations, with 200 distinct canonical fixture matches and 200 active RESOLVED crosswalks. Independent read-back confirmed timestamp ordering and correct market/bookmaker for all 200 rows. No duplicates or ineligible observations were found.

The fixed universe is 763 fixtures. Coverage is now 200/763 (26.21%); 563 fixtures remain to complete acquisition, and 548 additional valid observations are needed to reach the 98% threshold. Latest completed batch: [workflow #43733321610](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733321610), [artifact #14169004455](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733321610/artifacts/14169004455), SHA-256 `3f8dd0a575cc50dc52aa75d32fc2901051a3d7351f45e3f38b003bcf3e9c9c24`.

### Persistence discrepancy resolution

The apparent second-batch discrepancy was caused by auditing the separate normalized `odds_quote_observations` table instead of the acquisition write target `source_observations`. Manifests 109 and 110 both independently read back as 25/25 source observations linked through their capture requests and provider responses. No provider calls were repeated.

### Historical/closing odds decision

The separate source decision is recorded at `docs/VELTRIX_V2_HISTORICAL_CLOSING_ODDS_ENTITLEMENT_DECISION_2026-11-15.md`. 5Dollar timestamped tick history remains Ultra-only and account entitlement is not evidenced. The Odds API V4 historical snapshots are a technically acceptable alternative, but the connected account's paid historical endpoint access and UK bookmaker/market coverage are not verified. No credit-consuming odds request or restricted 5Dollar history request was made. There is no timestamped closing/near-close dataset or CLV evidence.

### Definitive Stage 2 disposition

The full decision is recorded in `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`.

**NO-GO — STAGE 2 EXIT CRITERIA NOT MET.** Opening-odds coverage is now 100% and passes its gate. Historical/closing odds entitlement and CLV remain blocked; walk-forward and prospective settlement thresholds are not met; additional temporal and identity restrictions remain. Stage 3 remains on hold.

No production writes, deployment, public predictions, Telegram delivery, schedule activation or value-betting unlock occurred. PR #120 remains draft/open/unmerged.


## 11. Latest acquisition reconciliation — 2026-11-15

Manifests 109–119 have now completed and independently reconciled: 275/275 requests, 275/275 provider responses, 275/275 timestamped opening quote observations, 275 distinct fixtures and 275 PIT-eligible rows. All 275 map to canonical fixtures, preserve valid timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found.

Coverage is 275/763 (36.04%). 488 fixtures remain to full coverage; 473 additional valid observations are required to reach the 98% threshold. Latest completed batch: workflow [#43733924743](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733924743), artifact [#14169571727](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733924743/artifacts/14169571727), SHA-256 `0a186a816796490c3da46492ac06b01ed9997b7609c20d552a61bb47f54bf5bd`.

Manifest 120 / workflow #43734128538 is currently executing and is not included in the 275 verified total. The definitive Stage 2 decision remains **NO-GO — NOT COMPLETE / NOT RELEASE-READY**; see `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`.


## 12. Latest acquisition reconciliation — 2026-11-15

Manifests 109–120 have completed and independently reconciled: 300/300 requests, 300/300 provider responses, 300/300 timestamped opening quote observations, 300 distinct fixtures and 300 PIT-eligible rows. All 300 map to canonical fixtures, preserve valid timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found.

Coverage is 300/763 (39.32%). 463 fixtures remain to full coverage; 448 additional valid observations are required to reach the 98% threshold. Latest completed batch: workflow [#43734128538](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734128538), artifact [#14170085844](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734128538/artifacts/14170085844), SHA-256 `088f5e1adf07a375cc469e23e3d35f7dadfdf4ed2d5e1aaabd51fcfb95428fe8`.

Manifest 121 / workflow #43734327570 is currently executing and is not included in the 300 verified total. The definitive Stage 2 decision remains **NO-GO — NOT COMPLETE / NOT RELEASE-READY**; see `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`.


## 13. Latest acquisition reconciliation — 2026-11-15

Manifests 109–121 have completed and independently reconciled: 325/325 requests, 325/325 provider responses, 325/325 timestamped opening quote observations, 325 distinct fixtures and 325 PIT-eligible rows. All 325 map to canonical fixtures, preserve valid timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found.

Coverage is 325/763 (42.60%). 438 fixtures remain to full coverage; 423 additional valid observations are required to reach the 98% threshold. Latest completed batch: workflow [#43734327570](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734327570), artifact [#14170016337](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734327570/artifacts/14170016337), SHA-256 `f752a53019de07e1a3b3c23b139fc5edf5f0d20dbe8e3bc2b06ff4912751a559`.

The definitive Stage 2 decision remains **NO-GO — NOT COMPLETE / NOT RELEASE-READY**; see `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`.


## 14. Latest acquisition reconciliation — 2026-11-15

Manifests 109–123 have completed and independently reconciled: 375/375 requests, 375/375 provider responses, 375/375 timestamped opening quote observations, 375 distinct fixtures and 375 PIT-eligible rows. All 375 map to canonical fixtures, preserve valid timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found.

Coverage is 375/763 (49.15%). 388 fixtures remain to full coverage; 373 additional valid observations are required to reach the 98% threshold. Latest completed batch: workflow [#43734702902](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734702902), artifact [#14168979796](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734702902/artifacts/14168979796), SHA-256 `295114a6c9ee623ef5fa8fb2dba430e9684913925467074450c5fa60d89877b9`.

The definitive Stage 2 decision remains **NO-GO — NOT COMPLETE / NOT RELEASE-READY**; see `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`.


## 15. Latest acquisition reconciliation — 2026-11-15

Manifests 109–124 have completed and independently reconciled: 400/400 requests, 400/400 provider responses, 400/400 timestamped opening quote observations, 400 distinct fixtures and 400 PIT-eligible rows. All 400 map to canonical fixtures, preserve valid timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found.

Coverage is 400/763 (52.42%). 363 fixtures remain to full coverage; 348 additional valid observations are required to reach the 98% threshold. Latest completed batch: workflow [#43734920511](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734920511), artifact [#14170381591](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734920511/artifacts/14170381591), SHA-256 `e45a5d9b092affa0e6cfd8a70f70c4695c2b81de83b1a5cce837655950490827`.

The latest observed Community quota remaining is 16, below the next batch's required preflight headroom of 26. Further capture must wait until after the 17:00 UTC reset and pass a fresh preflight. The definitive Stage 2 decision remains **NO-GO — NOT COMPLETE / NOT RELEASE-READY**; see `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`.


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


### Final CI reconciliation — 2026-11-15

All required CI checks on final documentation head `4b358ea148200f5fbd60bdcbec3bebfa6e2cc39e` completed successfully:
- Phase 2 Data Foundation Tests — PASS (including PostgreSQL 16/18 reservation persistence and complete foundation suite).
- PostgreSQL 16/18 Historical Data Foundation Acceptance — PASS.
- Phase 5 Shadow Regression — PASS (PostgreSQL 16/18 integration and shadow regression).
- Certification Evidence Integrity — PASS.
- Historical Model Audit Tests — PASS.
- Daily Fixture Predictions — SKIPPED as designed; no publication workflow was run.

PR #120 remains draft/open/unmerged. These CI passes do not override the Stage 2 NO-GO decision: opening-odds coverage is complete, but closing-odds/CLV evidence and market-specific model certification gates remain unmet.


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
