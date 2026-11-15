# VELTRIX FOOTBALL 2.0 — Stage 2 acquisition exit report

**Report date:** 2026-11-15  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Branch:** `integration/v2-report-bundle-wiring-20261114`  
**PR:** [#120](https://github.com/Nexora-Apparel/veltrix-football/pull/120) — open, draft, unmerged  
**Verified PR head at report time:** `70b1a8ef1742975464f74dfefcf8dac265d46d86`  
**Overall disposition:** **STAGE 2 ACQUISITION REPORT ISSUED — OPEN / NOT RELEASE-READY**

## 1. Executive result

The Stage 2 evidence acquisition and reconciliation work has produced verified source artifacts, a qualified non-PIT fixture/result label set, and the first 25 timestamped 5Dollar Community opening-odds observations. The crosswalk for the current 90-day 5Dollar fixture universe is complete and unambiguous.

Stage 2 is **not release-ready**. The first opening-odds batch covers only 25 of 763 eligible fixtures (3.28%), well below the 98% timestamped odds coverage requirement. The full 5Dollar historical tick endpoint requires an Ultra plan not evidenced for this account. The Odds API has catalogue-only evidence and no event or historical odds quotes. OpenFootball and FootballData archives remain retrospective/non-PIT; Community fixture/result labels are also explicitly non-PIT for pre-match feature use.

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

Overall coverage: **25 / 763 = 3.28%**. This is a bounded first batch, not the full target universe and not the 98% certification threshold.

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
- The 98% timestamped pre-kickoff odds coverage requirement is not met.

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

**NO-GO — STAGE 2 EXIT CRITERIA NOT MET.** Opening-odds coverage remains 26.21%; historical/closing odds entitlement and CLV remain blocked; walk-forward and prospective settlement thresholds are not met; additional temporal and identity restrictions remain. Stage 3 remains on hold.

No production writes, deployment, public predictions, Telegram delivery, schedule activation or value-betting unlock occurred. PR #120 remains draft/open/unmerged.


## 11. Latest acquisition reconciliation — 2026-11-15

Manifests 109–119 have now completed and independently reconciled: 275/275 requests, 275/275 provider responses, 275/275 timestamped opening quote observations, 275 distinct fixtures and 275 PIT-eligible rows. All 275 map to canonical fixtures, preserve valid timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found.

Coverage is 275/763 (36.04%). 488 fixtures remain to full coverage; 473 additional valid observations are required to reach the 98% threshold. Latest completed batch: workflow [#43733924743](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733924743), artifact [#14169571727](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733924743/artifacts/14169571727), SHA-256 `0a186a816796490c3da46492ac06b01ed9997b7609c20d552a61bb47f54bf5bd`.

Manifest 120 / workflow #43734128538 is currently executing and is not included in the 275 verified total. The definitive Stage 2 decision remains **NO-GO — NOT COMPLETE / NOT RELEASE-READY**; see `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`.
