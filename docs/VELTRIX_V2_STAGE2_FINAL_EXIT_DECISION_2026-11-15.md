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

The fixed 90-day, seven-competition universe contains 763 eligible 5Dollar fixtures. Manifests 109–120 are independently reconciled in the named staging database:

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
| **Total** | | **300** | **300** | **300** | **300** | **300** |

Independent aggregate read-back confirms 300/300 distinct provider fixture IDs map to canonical fixtures, are PIT eligible, preserve valid opening timestamp ordering, use Bet365 1X2, and have active RESOLVED fixture crosswalks. No duplicates or ineligible observations were found in these twelve manifests.

**Coverage:** 300/763 = 39.32%. 463 fixtures remain without a captured opening quote. At least 748 timestamped quotes are required to reach 98% of this denominator, so at least 448 additional valid quotes are still required. The full acquisition target remains 463 additional quotes.

All twelve batches were capped at 25 fixture requests, used a fresh Community quota preflight, used no automatic retries, retained the provider's opening timestamp and were written only to staging. The latest completed batch is workflow #43734128538, artifact #14170085844, SHA-256 `088f5e1adf07a375cc469e23e3d35f7dadfdf4ed2d5e1aaabd51fcfb95428fe8`.

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
| 5Dollar opening-odds persistence | PASS | 300/300 independently read back |
| Opening-odds coverage | FAIL / INCOMPLETE | 39.32%; 448 more to reach 98%; 463 to complete universe |
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
