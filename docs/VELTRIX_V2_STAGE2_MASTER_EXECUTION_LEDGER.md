# VELTRIX FOOTBALL 2.0 — Stage 2 Master Execution Ledger

**Status:** OPEN — execution and evidence reconciliation in progress  
**Last updated:** 2026-11-15  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Working branch:** `integration/v2-report-bundle-wiring-20261114`  
**PR:** [#120](https://github.com/Nexora-Apparel/veltrix-football/pull/120) — draft, open, unmerged  
**Last inspected PR head:** `1b50d53edd8388dbf4c9df0b04e792956fee50d0`  
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
| OpenFootball archive collector/parser/verifier | IMPLEMENTED / NOT RUN (current branch artifact verification must be reconciled) | `scripts/veltrix_v2/collect_openfootball_pit_snapshots.py`; `scripts/veltrix_v2/verify_openfootball_pit_snapshot_pack.py`; `tests/veltrix_v2/test_openfootball_pit_snapshot_pack.py`; workflow `.github/workflows/phase2-openfootball-pit-snapshot-pack.yml` | Reuse existing code. Inspect latest workflow artifact and independent verification output. Do not rebuild. |
| FootballData CC0 supplemental collector/parser/verifier | IMPLEMENTED / NOT RUN (current branch artifact verification must be reconciled) | `scripts/veltrix_v2/collect_football_data_cc0_snapshots.py`; `scripts/veltrix_v2/verify_football_data_cc0_snapshots.py`; `tests/veltrix_v2/test_football_data_cc0_snapshots.py` | Reuse existing code. Inspect latest workflow artifact and independent verification output. Do not rebuild. |
| CC0 archive temporal/PIT status | BLOCKED for historical PIT admission | Existing Stage 2 acquisition document section “Independent temporal-semantics audit”; collector/verifier evidence | Git commit metadata is not independently verified public availability. Preserve as retrospective/non-PIT. Do not bypass `recorded_at <= cutoff`; no fabricated timestamps. |
| 5Dollar Community historical qualification | DEFECT / NOT RUN | `scripts/phase2_fivedollar_history_dry_run.py`; `.github/workflows/phase2-historical-data-dry-run.yml`; `tests/test_phase2_data_foundation.py` | User confirms Community key has already been added as `FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY`. Before dispatch: reconcile stale rights approval ID and `commercial_use_allowed=True` against current non-commercial authorization; reconcile tests/fixtures. Then bounded read-only qualification. Do not ask user to add key again. |
| 5Dollar opening-odds capture query | VERIFIED code correction and regression test | `scripts/phase2_capture_fivedollar_opening_odds.py`; `tests/providers/test_fivedollar_opening_odds.py`; fix commits `58a7c79f052416f9a3fd14eb439b7b731bc7254d`, `4a9b41ca69c63932bc17184c6e7cb2be0a416233`, `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a` | No rebuild. Confirm exact current test status. |
| 5Dollar opening-odds actual capture | IMPLEMENTED / NOT RUN | Workflow `.github/workflows/phase2-5dollar-opening-odds-capture.yml`; read-only staging audit found 763 eligible/crosswalked candidates, zero existing opening quote observations and zero endpoint/tick responses | Actual requests and persisted quote provenance remain outstanding. 763 is not quote coverage. Dispatch workflow only after safely resolving default-branch workflow availability without merging PR #120. |
| 5Dollar opening-odds staging audit | VERIFIED read-only query result | Neon staging project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`; 763 candidates, 763 competition-scope matches, 763 resolved fixture crosswalks, 0 quote observations | Do not repeat unless source data changes or capture results need reconciliation. |
| Historical odds entitlement/coverage | BLOCKED / NOT VERIFIED | `docs/VELTRIX_V2_STAGE2_NONCOMMERCIAL_ODDS_ACQUISITION_2026-11-15.md`; `docs/VELTRIX_V2_5DOLLAR_HISTORICAL_ODDS_PIT_SOURCE_REVIEW_2026-11-15.md` | Verify provider entitlement and actual timestamped quote observations. Certification target remains 98%; no assumed coverage. |
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
| GitHub workflow dispatch from default branch | BLOCKED by branch visibility rule | PR #120 is draft/open/unmerged and contains the workflow. Do not merge merely to enable dispatch. Use a safe, separately reviewed default-branch workflow exposure or an authorized workflow dispatch mechanism. |
| 5Dollar provider quota/plan | NOT YET RE-VERIFIED | Workflow must inspect status/quota first and stop if the account profile or remaining quota differs from the approved bounded probe. |
| Historical odds entitlement | NOT VERIFIED | No historical endpoint calls until entitlement and cost caps are evidenced. |

## 5. Execution queue — fixed order

Only perform these existing-work closure tasks; do not add new scope.

1. **Reconcile Community probe rights contract and tests.** Inspect the approval object, rights evidence file/hash, secret reference, request budget, quota guard and test fixtures. Make the smallest correction so commercial use is false and the current approval ID/evidence is used. Run focused offline tests.
2. **Run the existing Community qualification workflow** once safely dispatchable. It is read-only, 365-day qualification only; retain exact run URL, report and quota evidence. Stop on any mismatch or request-budget guard.
3. **Inspect existing OpenFootball and FootballData workflow artifacts.** Run the existing independent verifiers on the exact artifacts; record hashes, counts, failed sources and temporal caveats. Do not recapture unless the artifact is absent, corrupt or incomplete.
4. **Resolve the default-branch dispatch constraint** without merging PR #120. Any workflow exposure must be minimal, reviewed and limited to the already-approved read-only capture.
5. **Run bounded 5Dollar opening-odds capture** (maximum 25 fixture requests per run; no retries) only after the workflow is safely dispatchable. Reconcile actual persisted quote timestamps and provenance.
6. **Reconcile crosswalk and historical-odds gates** using existing artifacts. No speculative mappings or paid calls.
7. **Publish one Stage 2 exit report** listing passed gates, open blockers, evidence links and explicit non-PIT boundaries.

## 6. Evidence log

Append one entry per meaningful operation. Never replace an earlier entry.

| Date (UTC) | Commit / workflow run | Operation | Result | Evidence / artifact | Follow-up |
|---|---|---|---|---|---|
| 2026-11-15 | Workflow [#43723395022](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43723395022) | OpenPlay staging feature pipeline | PASS — 20,178 derived rows; possession metric excluded; staging only | Artifact SHA-256 `5e101a56f8f68b9b6bc6f9982bc3e282aa76e5f2c96a6b4fd91c31d412a2e3cc` | Preserve sidecar; no model admission claim |
| 2026-11-15 | Commit `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a` | 5Dollar opening-odds query predicate/test correction | Focused code-head tests previously reported passing | Script/test commits listed in Section 2 | Actual quote capture remains not run |
| 2026-11-15 | Read-only Neon staging audit | 5Dollar opening-odds target audit | 763 eligible candidates; 0 quote observations | Project/branch/database listed in Section 2 | Capture still outstanding |
| 2026-11-15 | PR #120 head `1b50d53edd8388dbf4c9df0b04e792956fee50d0` | Repository state inspection | PR draft/open/unmerged; Community probe stale rights contract identified | `scripts/phase2_fivedollar_history_dry_run.py`; `tests/test_phase2_data_foundation.py` | Correct before workflow execution |

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
- Test execution status: NOT RUN in this session. The GitHub Actions connector exposes no workflow-dispatch action; `fetch_commit_workflow_runs` returned no runs for the test commit. Do not claim tests passed or dispatch the provider probe yet.
- Safety: no provider requests, database writes, production writes, deployment, schedule or Telegram sends were performed.
- Next action: obtain an authorized way to run the focused offline tests against this exact branch head; only after tests pass, address safe dispatch of the bounded read-only Community probe.
