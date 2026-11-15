# VELTRIX FOOTBALL 2.0 — Stage 2 Master Execution Ledger

**Status:** OPEN — execution and evidence reconciliation in progress  
**Last updated:** 2026-11-15  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Working branch:** `integration/v2-report-bundle-wiring-20261114`  
**PR:** [#120](https://github.com/Nexora-Apparel/veltrix-football/pull/120) — draft, open, unmerged  
**Last inspected PR head:** `70b1a8ef1742975464f74dfefcf8dac265d46d86` — exact-head CI checks passed; PR remains draft/open/unmerged.  
**Purpose:** Single operational index preventing completed work from being skipped, duplicated or rebuilt unnecessarily.

> This ledger is the navigation and state register, not a replacement for detailed contracts, code, test reports or immutable workflow artifacts. Detailed documents remain authoritative for their specific technical scope. Every status must be backed by a path, commit, workflow run, artifact, test result or explicit blocker.

## 1. Operating rules

1. Freeze Stage 2 scope. Do not add providers, features or architecture while closing existing Stage 2 gates.
2. Never recreate an existing component before checking its implementation, tests, workflow, evidence artifact and current branch state.
3. Classify each item as:
   - **VERIFIED** — implementation and required independent evidence both exist and pass.
   - **IMPLEMENTED / NOT RUN** — code exists; required execution evidence is absent.
   - **PARTIAL** — some required scope/evidence exists; explicit gaps remain.
   - **BLOCKED** — external dependency or authorization prevents execution.
   - **DEFECT** — concrete reproducible defect; repair only that defect.
   - **NOT STARTED** — no implementation or evidence located after repository inspection.
4. A successful unit test does not prove a provider request, persisted quote coverage, historical PIT eligibility or production readiness.
5. Preserve historical artifacts and hashes. Never overwrite or silently reinterpret evidence.
6. No production writes, PR merge, deployment, schedule activation, prediction publication, Telegram delivery or value-betting unlock under this ledger.
7. Update this ledger after each meaningful execution. Record what changed, exact commit/run, result, artifact, and next gate. Do not create a new document for each small step.
8. A gate marked VERIFIED stays closed unless a regression, new contradictory evidence or changed requirement is recorded.

## 2. Current Stage 2 status

| Workstream | Current classification | Existing implementation/evidence | Remaining action |
|---|---|---|---|
| OpenPlay rights and immutable raw staging | VERIFIED for approved non-commercial scope and staging capture | `docs/legal/openplay-whoscored-opta-authorization-2026-11-15.md`; `docs/VELTRIX_V2_OPENPLAY_STAGING_FEATURE_PIPELINE_2026-11-15.md`; pinned `data-v0.1.0`; approval `approval-openplay-whoscored-opta-noncommercial-2026-11-15` | No rebuild. Preserve rights limits; only reopen for a concrete issue. |
| OpenPlay feature bundle | VERIFIED as staging sidecar, not as a trained model input | Workflow [#43723395022](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43723395022); builder commit `1f56456f893717e26375ab99f999b8e66b533306`; bundle JSONL SHA-256 `9ed328dd7c9ae235c47252e32bde0bb06d2a030ec38d151eeda7de264408bdc1`; artifact SHA-256 `5e101a56f8f68b9b6bc6f9982bc3e282aa76e5f2c96a6b4fd91c31d412a2e3cc` | Keep as sidecar. Do not claim model training or PIT eligibility. |
| OpenPlay invalid possession metric | VERIFIED exclusion | All 20,178 rows carry `SOURCE_VALUES_VIOLATE_DOCUMENTED_PERCENTAGE_RANGE`; no `team.possession_pct` remains | No action unless regression. |
| OpenPlay identity crosswalk | PARTIAL | 89 team mappings and 5 competition mappings; conservative exact identity only | Expand only with independently supported aliases/IDs; unresolved identities remain quarantined. |
| OpenFootball archive collector/parser/verifier | VERIFIED ARTIFACT — NON-PIT | Workflow #43727169566: 49 snapshots, 5,182 observation versions, 375 requests; independent verifier PASS; artifact #14166223794. | Preserve immutable artifact; no PIT admission or historical cutoff training. |
| FootballData CC0 supplemental collector/parser/verifier | VERIFIED ARTIFACT — NON-PIT | Workflow #43727169566: 3 snapshots, 619 observation versions, 6 requests; independent verifier PASS; artifact #14166223800. | Preserve immutable artifact; kickoff_at remains null; no PIT admission. |
| CC0 archive temporal/PIT status | BLOCKED for historical PIT admission | Existing Stage 2 acquisition document section “Independent temporal-semantics audit”; collector/verifier evidence | Git commit metadata is not independently verified public availability. Preserve as retrospective/non-PIT. Do not bypass `recorded_at <= cutoff`; no fabricated timestamps. |
| 5Dollar Community historical qualification | VERIFIED — READ-ONLY / NON-PIT | Workflow #43726672957: 59 tests passed; 2,505/2,505 fixture/result labels qualified across seven competitions; 28/40 requests; no side effects. | Labels only; not PIT pre-match feature evidence. |
| 5Dollar opening-odds capture query | VERIFIED code correction and regression test | `scripts/phase2_capture_fivedollar_opening_odds.py`; `tests/providers/test_fivedollar_opening_odds.py`; fix commits `58a7c79f052416f9a3fd14eb439b7b731bc7254d`, `4a9b41ca69c63932bc17184c6e7cb2be0a416233`, `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a` | No rebuild. Confirm exact current test status. |
| 5Dollar opening-odds actual capture | PARTIAL — FIRST BOUNDED BATCH VERIFIED | Workflow #43727509783: 26 tests passed; 25 fixture requests; 25 timestamped Bet365 1X2 opening quotes inserted in staging; 25/25 PIT/time/identity checks pass. | 25/763 fixtures = 3.28%; 738 remain without an opening quote in this 90-day seven-competition universe. Additional capped runs required for broader coverage. |
| 5Dollar opening-odds staging audit | VERIFIED — READ-ONLY RECONCILIATION | Neon staging `withered-sky-75161174` / `br-silent-violet-bc5de88s` / `veltrix_football_staging`; 763 fixtures; exactly one active resolved crosswalk per fixture; 25 quotes persisted and matched to canonical fixtures. | Crosswalk identity gate passes for this universe; quote coverage remains 3.28%. |
| Historical odds entitlement/coverage | BLOCKED — 98% GATE NOT MET | 25/763 timestamped opening quotes (3.28%); zero 5Dollar historical tick observations; full tick endpoint requires Ultra; The Odds API has catalogue-only responses and no event/historical odds request. | No historical tick/CLV reconstruction; no value-bet certification. Continue only bounded, quota-preflighted opening batches and keep historical endpoints disabled. |
| Evidence-backed cross-provider identity | PARTIAL | OpenPlay exact crosswalk; OpenFootball/FootballData source-scoped IDs | No fuzzy/display-name-only joins. Only add evidence-backed mappings. |
| Feature-aware challenger | PARTIAL / NOT CERTIFIED | Existing independent model/challenger framework and OpenPlay feature sidecar | No training claim until temporal eligibility, chronological evaluation and tests are complete. Baseline remains unchanged. |
| Stage 2 full exit | OPEN | Detailed Stage 2 documents and this ledger | Close each remaining gate once with auditable evidence. |

## 3. Non-commercial rights constraints

The user confirms non-commercial authorization for OpenPlay/WhoScored/Opta and selected project sources, conditioned on no monetisation. Apply the exact scope and restrictions recorded in the legal documents; do not infer blanket rights beyond the recorded source/use scope.

- Monetisation prohibited.
- Raw redistribution prohibited unless a source's explicit licence independently permits it.
- Preserve attribution, provenance and rights approval IDs.
- OpenPlay/WhoScored/Opta data and derived outputs must not be monetised.
- CC0 repositories have their own licence scope; verify licence metadata at collection time.
- A licence/authorization does not prove historical publication time or PIT eligibility.

Authoritative rights documents:
- `docs/legal/veltrix-all-source-noncommercial-authorization-2026-11-15.md`
- `docs/legal/openplay-whoscored-opta-authorization-2026-11-15.md`
- `docs/legal/openfootball-cc0-scope-review-2026-11-15.md`
- `docs/legal/football-data-cc0-supplemental-rights-review-2026-11-15.md`
- `docs/legal/5dollar-terms-review-2026-11-12.md`
- `docs/VELTRIX_V2_STAGE2_NONCOMMERCIAL_ODDS_ACQUISITION_2026-11-15.md`

## 4. Known manual/external dependencies

| Dependency | Status | Handling |
|---|---|---|
| 5Dollar Community API key | USER CONFIRMED ADDED | Treat as configured; never request it again unless the workflow reports missing/invalid secret. Never print or retrieve secret value. |
| GitHub workflow dispatch from default branch | RESOLVED FOR BOUNDED RUN — WITHOUT MERGE | The opening-odds workflow was safely triggered by a path-filtered push on the integration branch; no merge or default-branch exposure was needed. Run #43727509783 passed. | Keep workflow manual/push-triggered only; no schedule. Use explicit bounded manual dispatch for subsequent batches. |
| 5Dollar provider quota/plan | NOT YET RE-VERIFIED | Workflow must inspect status/quota first and stop if the account profile or remaining quota differs from the approved bounded probe. |
| Historical odds entitlement | NOT VERIFIED | No historical endpoint calls until entitlement and cost caps are evidenced. |

## 5. Execution queue — fixed order

Only perform these existing-work closure tasks; do not add new scope.

1. **COMPLETE — Community rights contract and tests.** Exact non-commercial approval ID/evidence, Community-only secret reference, seven-competition scope, 40-request budget and quota guard reconciled. Exact-head workflow run #43726672957 executed the two Phase 2 test files: 59 passed.
2. **COMPLETE — bounded Community qualification.** Read-only 365-day run #43726672957 qualified 2,505/2,505 fixture/result labels across seven competitions with 28/40 requests; report and artifact hashes recorded below. It is explicitly non-PIT and not pre-match feature evidence.
3. **COMPLETE — Inspect existing OpenFootball and FootballData workflow artifacts.** Workflow #43727169566 collected both packs and ran their independent verifiers successfully. Exact artifact IDs, SHA-256 hashes, counts and temporal caveats are recorded in the evidence log below.
4. **COMPLETE — Resolve workflow availability without merging PR #120.** Path-filtered integration-branch push triggered the bounded capture workflow; no default-branch merge/exposure was needed.
5. **PARTIAL — Run bounded 5Dollar opening-odds capture.** First batch complete: 25/25 quotes persisted and verified. The 90-day fixture universe is 763, so 738 fixtures remain; 25/763 = 3.28%. Each further run remains capped at 25 fixture requests, no retries, fresh quota preflight.
6. **COMPLETE — Reconcile crosswalk and historical-odds gates.** All 763 fixtures have exactly one active RESOLVED fixture crosswalk; all 25 captured quotes match canonical identity and pass timestamp checks. Historical tick endpoint entitlement is not available on current plan; The Odds API has catalogue-only evidence; 98% quote coverage is unmet.
7. **COMPLETE — Publish the definitive Stage 2 exit report.** Report records passed acquisition checks and unresolved coverage/entitlement blockers. Stage 2 remains OPEN / NOT RELEASE-READY; no production or publication gates are unlocked.

## 6. Evidence log

Append one entry per meaningful operation. Never replace an earlier entry.

| Date (UTC) | Commit / workflow run | Operation | Result | Evidence / artifact | Follow-up |
|---|---|---|---|---|---|
| 2026-11-15 | Workflow [#43723395022](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43723395022) | OpenPlay staging feature pipeline | PASS — 20,178 derived rows; possession metric excluded; staging only | Artifact SHA-256 `5e101a56f8f68b9b6bc6f9982bc3e282aa76e5f2c96a6b4fd91c31d412a2e3cc` | Preserve sidecar; no model admission claim |
| 2026-11-15 | Commit `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a` | 5Dollar opening-odds query predicate/test correction | Focused code-head tests previously reported passing | Script/test commits listed in Section 2 | Actual quote capture remains not run |
| 2026-11-15 | Read-only Neon staging audit | 5Dollar opening-odds target audit | 763 eligible candidates; 0 quote observations | Project/branch/database listed in Section 2 | Capture still outstanding |
| 2026-11-15 | PR #120 head `1b50d53edd8388dbf4c9df0b04e792956fee50d0` | Repository state inspection | PR draft/open/unmerged; Community probe stale rights contract identified | `scripts/phase2_fivedollar_history_dry_run.py`; `tests/test_phase2_data_foundation.py` | Correct before workflow execution |
| 2026-11-15 | [Workflow #43726672957](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957), job `132850009142`, commit `90d984091fdde520da4126842fb5301e5a8c0990` | Community rights regression + bounded 365-day qualification | PASS — 59 tests; 2,505/2,505 importable; 7/7 competitions; pagination complete; 28/40 requests; read-only; non-PIT | [Artifact #14166776290](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957/artifacts/14166776290); report SHA-256 `3bf4d797df92c293af6f346e296d3d76f7e7d9ec8988320d3992da1b5f6c668a`; ZIP SHA-256 `29e908f311ede85de1a8a8e1f824da54520da32073d0a26cb843ef033384ddea` | Community result labels only; no PIT admission |
| 2026-11-15 | [Workflow #43727169566](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566), commit `c86163a75a8f80914de9eb2fd2bd0b2265fa3ed7` | OpenFootball + FootballData archive capture and independent verification | PASS — OpenFootball 49 snapshots / 5,182 observation versions / 375 requests; FootballData 3 snapshots / 619 observation versions / 6 requests; both verifiers PASS | OpenFootball artifact [#14166223794](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223794), ZIP SHA-256 `3dd4e89fa9c3d766e3e044efc317a88c6147b232dbb2831402cde26302e7de03`; FootballData artifact [#14166223800](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223800), ZIP SHA-256 `d8156a30d6b2f49032c157378385508fc8eefad931023ab2845255877c352acf` | Preserve both packs as retrospective evidence only; all rows non-PIT; no database/production writes |
| 2026-11-15 | [Workflow #43727509783](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783), job `132852553767`, commit `70b1a8ef1742975464f74dfefcf8dac265d46d86` | Bounded 5Dollar Community Bet365 1X2 opening capture | PASS — 26 tests; 25 fixture requests; 25 observations inserted; 25 timestamped PIT quotes; 26 provider requests including status preflight; quota 299→274 | Artifact [#14166689086](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783/artifacts/14166689086); ZIP SHA-256 `b8a6b0594294fdd4b6178ebab0e010c2a30fb15b87686c3ba30457dae82fd171`; summary JSON SHA-256 `f519f8c6cb085a1a04afdb8f7582ddb8c2fb1813eb2a4914345cc9e322ccdb54` | Staging manifest 109, 25/25 request rows and observations; 25/763 coverage (3.28%); 738 outstanding; no production writes/publication |
| 2026-11-15 | Read-only Neon SQL audit, `withered-sky-75161174` / `br-silent-violet-bc5de88s` / `veltrix_football_staging` | Reconcile 5Dollar fixture crosswalk and opening-quote PIT integrity | PASS — 763/763 fixtures exactly one active RESOLVED crosswalk; 25/25 captured quotes match canonical fixture, Bet365 1X2, valid prices, provider opening timestamp < kickoff, retrieved_at >= opening timestamp, HTTP 200 | Manifest `109`; provider response IDs `462–486`; source observation IDs `431621–431645`; 0 historical tick observations | Quote coverage 3.28%; 98% certification gate unmet; no 5Dollar Ultra history or The Odds API event/historical calls; no production writes |

## 7. Per-session update template

For each continuation, update the ledger with:
- Starting PR head and branch state.
- Exact paths inspected (and paths not yet inspected).
- Existing implementation reused.
- Tests actually run and their exact result.
- Workflow run IDs and artifact hashes.
- Any code changes with commit SHA.
- Staging/production write status.
- Newly discovered blockers, distinguishing them from pre-existing blockers.
- One next action from the fixed queue.

**Do not mark an item complete from code presence alone. Do not call an item missing until the repository and evidence artifacts have been searched. Do not restart completed work.**

## 8. Safety state

At the time of this ledger:
- PR #120 remains draft/open/unmerged.
- No production writes are authorized or reported.
- No deployment is authorized or reported.
- No Telegram delivery or schedule activation is authorized or reported.
- No public prediction publication is authorized or reported.
- Value betting remains locked pending certification.
- OpenFootball and FootballData archive data remain retrospective/non-PIT absent independent publication-time evidence.

### Community rights-contract reconciliation — 2026-11-15
- Added source-specific authorization record: `docs/legal/5dollar-community-noncommercial-authorization-2026-11-15.md`. It binds the project-owner non-commercial condition to the 5Dollar October 2026 terms review and the seven exact account-entitled provider competition IDs.
- Updated `scripts/phase2_fivedollar_history_dry_run.py` to use approval ID `approval-5dollar-community-fixture-result-benchmarking-2026-11-14`, set `commercial_use_allowed=False`, and hash/reference the new source-specific authorization record. It still requires the provider terms review file, preserves Community-only secret use, seven-competition scope, and the existing 40-request hard budget/quota preflight.
- Added `test_community_probe_uses_current_noncommercial_approval_evidence` to `tests/test_phase2_data_foundation.py`, asserting the exact approval ID, non-commercial flag, evidence URI/hash, raw redistribution prohibition and competition scope.
- Commits: authorization document `1dcdea9bc202428da9fecbad4b3dd23f3c2917f7`; script correction `8ad3b4629cf42ee5ca27da91cd4068469cfc979c`; focused regression test `db86995533dcba8b61f1c755cc6067f1137f9e73`.
- Read-back verification: script blob `8a6dd22485a176eb22914051bbdd59fd902b0f1d`; test blob `e44c9cbc57f2f860a6c8ee45780412f4487af314`; Community workflow blob `eb309212da4a6f5de1b74334c00620bc89cb3a42` still references `FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY`.
- Test execution: PASS — workflow run [#43726672957](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957), job `132850009142`, exact checkout commit `90d984091fdde520da4126842fb5301e5a8c0990`; `tests/test_phase2_data_foundation.py` and `tests/test_db_migrations.py`: **59 passed in 0.13s**.
- Bounded Community qualification: PASS — same run, `status=QUALIFIED`; 365-day window `2025-11-15T14:52:17Z` through `2026-11-15T14:52:17Z`; 2,505 fixtures and 2,505 importable; all seven allowlisted competitions; pagination complete; 28 requests of 40; 0 rejected, 0 quarantined, 0 duplicate fixture IDs; no failure reason.
- Fresh account/quota evidence: Community plan; 300/hour and 20/minute; initial remaining 299, final remaining 272. Do not treat this as a future quota guarantee.
- Report: `fivedollar-history-dry-run.json`, report SHA-256 `3bf4d797df92c293af6f346e296d3d76f7e7d9ec8988320d3992da1b5f6c668a`; artifact [#14166776290](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957/artifacts/14166776290), ZIP SHA-256 `29e908f311ede85de1a8a8e1f824da54520da32073d0a26cb843ef033384ddea`.
- Temporal boundary: report explicitly sets `point_in_time_certifiable=false`; provider finished-status conservative four-day availability is suitable for settled target labels only, not pre-match feature availability. This run does not qualify PIT history or historical model training.
- Side effects: report records 0 database writes, 0 imports, 0 prediction changes, 0 deployments and 0 Telegram messages. Read-only qualification only.
- Safety: no production writes, deployment, schedule activation or Telegram sends occurred.
- Next action: proceed to the next fixed Stage 2 queue item: inspect existing OpenFootball and FootballData workflow artifacts with their independent verifiers. Do not recapture unless artifacts are absent, corrupt or incomplete.


### Community qualification run evidence — 2026-11-15
- Exact run: [#43726672957](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957); job `132850009142`; branch `integration/v2-report-bundle-wiring-20261114`; checkout commit `90d984091fdde520da4126842fb5301e5a8c0990`; workflow event `workflow_dispatch`; conclusion `success`.
- Test command: `python -m pytest -q tests/test_phase2_data_foundation.py tests/test_db_migrations.py`; result `59 passed in 0.13s`.
- Probe result: `QUALIFIED`; 2,505 fixtures, all 2,505 importable, 7 competitions, 26 fixture pages, 28 total requests / 40 budget; pagination complete; no rejected, quarantined, duplicate or failed rows.
- Account snapshot: Community plan; 300/hour; 20/minute; initial quota remaining 299; final remaining 272. Current observation only; preflight must be repeated for any later capture.
- Report hash: `3bf4d797df92c293af6f346e296d3d76f7e7d9ec8988320d3992da1b5f6c668a`. Artifact ZIP hash: `29e908f311ede85de1a8a8e1f824da54520da32073d0a26cb843ef033384ddea`.
- Report rights: approval `approval-5dollar-community-fixture-result-benchmarking-2026-11-14`; non-commercial; attribution required; raw redistribution prohibited; October 2026 terms.
- Crucial temporal boundary: `availability_policy.point_in_time_certifiable=false`; conservative finished-status availability is for settled target labels only, not certified pre-match feature availability. Do not backdate or admit these rows into PIT feature training/evaluation.
- Side effects asserted by the report: database writes 0; imports 0; prediction changes 0; deployments 0; Telegram messages 0.


### OpenFootball and FootballData archive verification — 2026-11-15
- Workflow [#43727169566](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566) completed `success` on commit `c86163a75a8f80914de9eb2fd2bd0b2265fa3ed7`. The workflow path filter was corrected to include the four archive regression test files; the workflow file itself is a watched path, allowing the integration-branch push trigger without merging PR #120 or exposing it on `main`.
- Isolated test command: `python -m pytest --import-mode=importlib -q tests/veltrix_v2/test_openfootball_pit_snapshot_pack.py tests/providers/test_openfootball_archive.py tests/veltrix_v2/test_football_data_cc0_snapshots.py`; **19 passed in 0.16s**.
- OpenFootball collector: 20 source paths, all succeeded; 49 immutable snapshots; 5,182 observation versions; 375/500 requests. Independent verifier: `PASS`; 49 archive proofs; all commit histories complete; 5,182 unique fixtures; 82 not-yet-eligible rows; 2 rejected results. Observation JSONL SHA-256 `40a3ca23755f67f8c0cdc919bbdb69705f3fad5f9dc4ef21d51f773fec7384f6`. Artifact [#14166223794](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223794), ZIP SHA-256 `3dd4e89fa9c3d766e3e044efc317a88c6147b232dbb2831402cde26302e7de03`.
- OpenFootball coverage includes seven competition scopes. All 5,182 observation rows have `point_in_time_certifiable=false`; `kickoff_at` is null and `available_at` is the actual VELTRIX import time. The commit timestamp is source-version metadata, not independently proven first-public-availability time. Do not use these records for historical PIT features, backtests or certification without a separate proof path.
- FootballData collector: both source paths succeeded; 3 immutable snapshots; 619 observation versions; 6/100 requests. Independent verifier: `PASS`; 539 unique fixtures; 14 audited team-name normalizations; 1 not-yet-eligible row; 0 rejected results. Observation JSONL SHA-256 `1b4e732bf045f106dca6ec9e483b21cfaea0221edbe4eab0a9fe63a209bae321`. Artifact [#14166223800](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223800), ZIP SHA-256 `d8156a30d6b2f49032c157378385508fc8eefad931023ab2845255877c352acf`.
- FootballData includes 2025 revisions and the 2026 partial snapshot dated 2026-07-08. All 619 observation rows have `point_in_time_certifiable=false`; source-reported match clocks have unknown timezone, so `kickoff_at` remains null. The commit timestamp is not a provider publication-time attestation. Do not use for PIT pre-match features or historical cutoff certification.
- Both artifacts record `database_written=false` and `production_written=false`; no production import, schedule activation, public publication or Telegram delivery occurred.


### 5Dollar bounded opening-odds capture and Stage 2 crosswalk/odds reconciliation — 2026-11-15
- Exact current PR #120 head at verification: `70b1a8ef1742975464f74dfefcf8dac265d46d86`; PR remains open, draft and unmerged. Exact-head checks: PostgreSQL 16/18 integration, PostgreSQL 16/18 acceptance, shadow regression, certification evidence, audit tests and foundation all `success`; daily-predictions skipped by design. No PR merge.
- Workflow [#43727509783](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783), job `132852553767`, completed `success` on the exact head. `python -m pytest -q tests/providers/test_fivedollar_opening_odds.py tests/scripts/test_phase2_capture_fivedollar_opening_odds.py`: **26 passed in 0.15s**. Dry-run passed before network/database execution.
- Fresh `/status` preflight at `2026-11-15T15:01:32.898357Z`: Community plan; 300/hour; 20/minute; quota remaining 299; 25 fixture requests planned; preflight response SHA-256 `97b5e2ab31bad9bb612c8a9de53a4c14f9da5204d596ac56d2aa17939dc612a`.
- Actual capture: 25 fixture requests, 3.1-second spacing, no retries; 26 total provider requests including `/status`; quota remaining after final fixture response 274. Workflow output: 25 PIT-eligible, 0 ineligible, 25 inserted, 0 duplicates. No schedule, publication or Telegram action.
- Artifact [#14166689086](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783/artifacts/14166689086), ZIP SHA-256 `b8a6b0594294fdd4b6178ebab0e010c2a30fb15b87686c3ba30457dae82fd171`; `summary.json` SHA-256 `f519f8c6cb085a1a04afdb8f7582ddb8c2fb1813eb2a4914345cc9e322ccdb54`.
- Staging target independently confirmed by the collector allowlist: project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`, role `neondb_owner`; no production target.
- Read-only DB read-back: capture manifest `109`, `requests_planned=25`, 25 request rows, 25 `RESPONSE` outcomes, 25 unique request keys; provider response IDs `462–486`; source observation IDs `431621–431645`. The 25 observations are distinct fixtures, HTTP 200, valid Bet365 1X2 prices, retain raw `opened_at`, source timestamp basis `provider_timestamp`, availability basis `provider_opening_timestamp`, `source_published_at=available_at=opened_at`, `source_event_time=kickoff_at`, `opened_at < kickoff_at`, and `retrieved_at >= opened_at`. All 25 exact-match the eligible canonical fixture universe. The separate `source_effective_at` remains null; do not reinterpret it.
- The 90-day, seven-competition eligible fixture universe is 763. Exactly one active `RESOLVED` fixture crosswalk exists per fixture: 763/763; zero missing or ambiguous. Captured quote distribution: Brazil Serie A 1/115; Brazil Serie B 10/151; England Premier League 6/100; France Ligue 1 2/90; Germany Bundesliga I 0/81; Italy Serie A 0/110; Spain La Liga 6/116. Total 25/763 = 3.28%; 738 fixtures remain without a captured opening quote. This is not 98% market coverage.
- Historical odds gate: zero 5Dollar historical tick observations. The full `/fixtures/{id}/odds/history?market=1x2` tick-history endpoint requires Ultra; no Ultra entitlement or paid call is evidenced. The Odds API has only three `/v4/sports/` catalogue responses and zero event-odds or historical-odds responses; no credit-consuming request was made. No closing-price, movement or CLV path is currently supported by this evidence.
- Rights: staging approval `approval-5dollar-community-odds-quote-noncommercial-2026-11-15` is `APPROVED`, non-commercial, attribution required, raw redistribution prohibited, scope restricted to the same seven provider competition IDs, October 2026 terms; one append-only APPROVED event exists. User's project-wide no-monetisation restriction remains controlling.
- Disposition: bounded batch and crosswalk identity checks PASS; full odds coverage, historical tick entitlement and market certification remain BLOCKED/PARTIAL. No production writes, deployment, publication, Telegram delivery or schedule activation occurred. Stage 2 remains OPEN / NOT RELEASE-READY.


### Stage 2 continuation and exit decision — 2026-11-15 (latest reconciliation)

- Historical/closing odds source decision recorded in `docs/VELTRIX_V2_HISTORICAL_CLOSING_ODDS_ENTITLEMENT_DECISION_2026-11-15.md`. The Odds API V4 historical snapshots are a technically acceptable alternative, but paid historical access and UK bookmaker/market coverage remain unverified. 5Dollar tick history remains Ultra-only with no evidenced entitlement. No credit-consuming Odds API request or restricted 5Dollar tick-history request was made.
- The second-batch persistence discrepancy is resolved: manifests 109 and 110 each have 25 request rows, 25 provider responses and 25 opening-quote source observations. The earlier zero count queried the separate normalized `odds_quote_observations` table rather than the raw acquisition target `source_observations`. No provider requests were repeated.
- Manifests 109–116: 8 completed batches; 200/200 requests, responses and source observations; 200 distinct fixtures; 200 PIT-eligible. Each batch: 25 fixture requests, fresh Community quota preflight, 3.1-second spacing, no retries, zero duplicates and zero ineligible quotes.
- Latest completed capture: workflow [#43733321610](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733321610), job `132870378351`, artifact [#14169004455](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733321610/artifacts/14169004455), artifact SHA-256 `3f8dd0a575cc50dc52aa75d32fc2901051a3d7351f45e3f38b003bcf3e9c9c24`.
- Independent aggregate read-back: 200 distinct provider fixture IDs, 200 canonical fixture matches, 200 PIT-eligible, 200 timestamp-order-valid, 200 Bet365 1X2 and 200 active RESOLVED fixture crosswalks.
- Fixed universe remains 763 eligible fixtures. Current verified opening coverage is 200/763 = 26.21%; 563 remain to full coverage; at least 548 additional quotes are required to reach the 98% threshold (748/763).
- The next bounded capture trigger is being advanced sequentially; a batch is not counted until workflow completion and independent DB reconciliation.
- Formal exit decision: `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md` — **NO-GO / STAGE 2 NOT COMPLETE / NOT RELEASE-READY**. Stage 3 remains on hold. Historical/closing odds, 98% coverage, prospective settlements, walk-forward sample thresholds and other evidence gates remain open.
- Release controls unchanged: PR #120 draft/open/unmerged; no production writes/deployment, publication, Telegram send, schedule activation or value-betting unlock.


### Opening-odds acquisition update — 2026-11-15 (manifests 109–119)

- Eleven manifests (109–119) are independently reconciled: 275/275 request rows, 275/275 provider responses, 275/275 opening quote observations, 275 distinct fixtures and 275 PIT-eligible observations.
- All 275 rows map to canonical fixtures, preserve valid provider opening timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible rows.
- Coverage: 275/763 = 36.04%; 488 remain to full universe; 473 more are required to reach the 98% minimum (748/763).
- Latest completed batch: workflow [#43733924743](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733924743), artifact [#14169571727](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43733924743/artifacts/14169571727), SHA-256 `0a186a816796490c3da46492ac06b01ed9997b7609c20d552a61bb47f54bf5bd`.
- Manifest 120 / workflow #43734128538 is currently in progress and is excluded from the 275 verified total until job success and independent reconciliation.
- Formal decision remains **NO-GO — Stage 2 not complete / not release-ready**. See `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`. Historical/closing odds entitlement and certification thresholds remain blocked. Stage 3 stays on hold.


### Opening-odds continuation update — 2026-11-15 (manifests 109–120)

- Manifests 109–120 are independently reconciled: 300/300 request rows, 300/300 provider responses, 300/300 opening quote observations, 300 distinct fixtures and 300 PIT-eligible observations.
- All 300 rows map to canonical fixtures, preserve valid provider opening timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible rows.
- Coverage: 300/763 = 39.32%; 463 remain to full universe; 448 additional quotes are required to reach the 98% minimum (748/763).
- Latest completed batch: workflow [#43734128538](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734128538), artifact [#14170085844](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734128538/artifacts/14170085844), SHA-256 `088f5e1adf07a375cc469e23e3d35f7dadfdf4ed2d5e1aaabd51fcfb95428fe8`.
- Manifest 121 / workflow #43734327570 is in progress and is excluded from the 300 verified total until job success and independent reconciliation.
- Formal decision remains **NO-GO — Stage 2 not complete / not release-ready**. See `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`. Historical/closing odds entitlement and certification thresholds remain blocked. Stage 3 stays on hold.


### Opening-odds continuation update — 2026-11-15 (manifests 109–121)

- Manifests 109–121 are independently reconciled: 325/325 request rows, 325/325 provider responses, 325/325 opening quote observations, 325 distinct fixtures and 325 PIT-eligible observations.
- All 325 rows map to canonical fixtures, preserve valid provider opening timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible rows.
- Coverage: 325/763 = 42.60%; 438 remain to full universe; 423 additional quotes are required to reach the 98% minimum (748/763).
- Latest completed batch: workflow [#43734327570](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734327570), artifact [#14170016337](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734327570/artifacts/14170016337), SHA-256 `f752a53019de07e1a3b3c23b139fc5edf5f0d20dbe8e3bc2b06ff4912751a559`.
- Formal decision remains **NO-GO — Stage 2 not complete / not release-ready**. See `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`. Historical/closing odds entitlement and certification thresholds remain blocked. Stage 3 stays on hold.


### Opening-odds continuation update — 2026-11-15 (manifests 109–123)

- Manifests 109–123 are independently reconciled: 375/375 request rows, 375/375 provider responses, 375/375 opening quote observations, 375 distinct fixtures and 375 PIT-eligible observations.
- All 375 rows map to canonical fixtures, preserve valid provider opening timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible rows.
- Coverage: 375/763 = 49.15%; 388 remain to full universe; 373 additional quotes are required to reach the 98% minimum (748/763).
- Latest completed batch: workflow [#43734702902](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734702902), artifact [#14168979796](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734702902/artifacts/14168979796), SHA-256 `295114a6c9ee623ef5fa8fb2dba430e9684913925467074450c5fa60d89877b9`.
- Formal decision remains **NO-GO — Stage 2 not complete / not release-ready**. See `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`. Historical/closing odds entitlement and certification thresholds remain blocked. Stage 3 stays on hold.
