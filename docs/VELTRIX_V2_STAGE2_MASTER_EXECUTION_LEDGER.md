# VELTRIX FOOTBALL 2.0 — Stage 2 Master Execution Ledger

**Status:** OPEN — execution and evidence reconciliation in progress  
**Last updated:** 2026-11-15  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Working branch:** `integration/v2-report-bundle-wiring-20261114`  
**PR:** [#120](https://github.com/Nexora-Apparel/veltrix-football/pull/120) — draft, open, unmerged  
**Latest AI Midas staging-import validation:** commit `27ecf03ff3530b52ff91f8e0b3120af0fabc6551` — workflow [#43753939202](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43753939202) passed; 14/14 pinned files, 14 immutable responses, 14 file-level observations and independent post-commit readback PASS. Current documentation head `0a1ceec70491e08c30a1f6aa1d1a41d2a31db585`; its exact-head CI is running, daily predictions skipped; PR #120 remains draft/open/unmerged.  
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
| AI Midas authorization, dataset audit and staging import | PARTIAL — AUTHORIZATION + 14-FILE SNAPSHOT + STAGING FILE-LEVEL RAW EVIDENCE IMPORT VERIFIED; NO NORMALIZED ROW OR MODEL ADMISSION | `docs/legal/aimidas-noncommercial-authorization-2026-11-15.md`; `docs/VELTRIX_V2_AIMIDAS_DATASET_AUDIT_2026-11-15.md`; `docs/VELTRIX_V2_AIMIDAS_STAGING_IMPORT_CONTRACT_2026-11-15.md`; pinned source commit `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`; 19,605 historical match rows; Brazil Série B 2026 advanced file: 738 team rows / 369 matches; staging: 14 raw responses / 14 file-level observations / 11,599,486 bytes; independent readback PASS in workflow #43753939202 | Reconcile historical match archives to canonical fixtures and review Brazil Série B 369/371 candidate crosswalk; keep all rows non-PIT; average odds are not timestamped bookmaker closing quotes. |
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

The user confirms non-commercial authorization for OpenPlay/WhoScored/Opta, AI Midas and selected project sources, conditioned on no monetisation. Apply the exact scope and restrictions recorded in the legal documents; do not infer blanket rights beyond the recorded source/use scope.

- Monetisation prohibited.
- Raw redistribution prohibited unless a source's explicit licence independently permits it.
- Preserve attribution, provenance and rights approval IDs.
- OpenPlay/WhoScored/Opta and AI Midas data and derived outputs must not be monetised.
- CC0 repositories have their own licence scope; verify licence metadata at collection time.
- A licence/authorization does not prove historical publication time or PIT eligibility.

Authoritative rights documents:
- `docs/legal/veltrix-all-source-noncommercial-authorization-2026-11-15.md`
- `docs/legal/openplay-whoscored-opta-authorization-2026-11-15.md`
- `docs/legal/openfootball-cc0-scope-review-2026-11-15.md`
- `docs/legal/football-data-cc0-supplemental-rights-review-2026-11-15.md`
- `docs/legal/5dollar-terms-review-2026-11-12.md`
- `docs/legal/aimidas-noncommercial-authorization-2026-11-15.md`
- `docs/VELTRIX_V2_AIMIDAS_DATASET_AUDIT_2026-11-15.md`
- `docs/VELTRIX_V2_STAGE2_NONCOMMERCIAL_ODDS_ACQUISITION_2026-11-15.md`

### AI Midas — authorization and repository audit (2026-11-15)

- User-confirmed authorization is formalized as `approval-aimidas-football-data-noncommercial-2026-11-15`; see `docs/legal/aimidas-noncommercial-authorization-2026-11-15.md`.
- Inventory and temporal audit: `docs/VELTRIX_V2_AIMIDAS_DATASET_AUDIT_2026-11-15.md`. Pinned repository commit: `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`.
- Six historical datasets cover Brazil Série A plus EPL, Ligue 1, Bundesliga I, Italy Serie A and La Liga: 19,605 rows, 2016–2024/25. The 1X2 average-odds fields are numerically complete in 19,454/19,605 rows (99.23% aggregate), but have no bookmaker identity or quote timestamp.
- Brazil Série B coverage is only the 2026 advanced-statistics CSV: 738 team rows / 369 distinct matches / 20 teams, 2026-03-21 through 2026-11-08. No 2016–2025 Brazil Série B historical match archive or standard match/odds CSV was found.
- The public files can be fetched without an API key. The AI Midas `sync_stats.py` pushes to the source owner's mirror and is not a Veltrix collector; preserve its upstream lineage to `griffisben/Post_Match_App/Stat_Files`.
- Repository metadata for AI Midas and the identified upstream repository reports no declared SPDX licence. Keep the user-confirmed authorization record, attribution and upstream lineage; no raw redistribution.
- Staging import contract is documented at `docs/VELTRIX_V2_AIMIDAS_STAGING_IMPORT_CONTRACT_2026-11-15.md`; it is design-only and has not been executed.
- Final privacy-corrected snapshot workflow #43752435643 passed: 14/14 files captured and independently verified; raw-source artifact from the first run was deleted; only metadata files are retained in artifact #14176976339 (ZIP SHA-256 `54ce4e05d6fd84f410c6723c181030ecde4376a10003ed6523ff9b536591b595`).
- Read-only Brazil Série B crosswalk: 20/20 teams mapped; 369/369 source matches uniquely reconciled to canonical fixtures with 369/369 score matches; canonical universe 371, so coverage is 369/371 (99.46%) and two fixtures are absent from AI Midas. No database writes.
- All source rows remain retrospective/non-PIT unless independently proven otherwise. `pre_match_*` fields have no row-level availability evidence; actual xG/PPDA/possession and other match statistics are post-match. Do not use same-match post-match fields as prediction inputs.
- No AI Midas Neon import, database write, model admission, prediction change or production operation has been performed. Average odds do not qualify as closing odds, CLV or the 98% timestamped-odds gate.

## 4. Known manual/external dependencies

| Dependency | Status | Handling |
|---|---|---|
| 5Dollar Community API key | USER CONFIRMED ADDED | Treat as configured; never request it again unless the workflow reports missing/invalid secret. Never print or retrieve secret value. |
| GitHub workflow dispatch from default branch | RESOLVED FOR BOUNDED RUN — WITHOUT MERGE | The opening-odds workflow was safely triggered by a path-filtered push on the integration branch; no merge or default-branch exposure was needed. Run #43727509783 passed. | Keep workflow manual/push-triggered only; no schedule. Use explicit bounded manual dispatch for subsequent batches. |
| 5Dollar provider quota/plan | NOT YET RE-VERIFIED | Workflow must inspect status/quota first and stop if the account profile or remaining quota differs from the approved bounded probe. |
| AI Midas public dataset access | AVAILABLE — NO API KEY REQUIRED | Read pinned public raw GitHub files from repository commit `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`; do not run the source owner's `.env`-based sync/push script. |
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
| 2026-11-15 | [Workflow #43753939202](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43753939202), commit `27ecf03ff3530b52ff91f8e0b3120af0fabc6551` | AI Midas pinned snapshot + isolated staging raw evidence import | PASS — 13 focused tests; 14/14 source files pinned and independently verified; 14 raw responses / 14 file-level observations / 11,599,486 bytes persisted; independent-process post-commit readback PASS; 0 PIT-certifiable observations | Artifact [#14177201895](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43753939202/artifacts/14177201895), ZIP SHA-256 `8f609bc5c7ae2b8fdcf7f879c3257228188af32d9a7efb34d7b469f60b382d68`; manifest SHA-256 `d8c9bbe1301b62444d86c130b401d4f6cb57740e6ad6177d9b9f6c188d1ae31a` | No normalized rows, fixture crosswalks, odds quotes, model admission or production writes; proceed with read-only identity reconciliation |
| 2026-11-15 | Workflow [#43723395022](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43723395022) | OpenPlay staging feature pipeline | PASS — 20,178 derived rows; possession metric excluded; staging only | Artifact SHA-256 `5e101a56f8f68b9b6bc6f9982bc3e282aa76e5f2c96a6b4fd91c31d412a2e3cc` | Preserve sidecar; no model admission claim |
| 2026-11-15 | Commit `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a` | 5Dollar opening-odds query predicate/test correction | Focused code-head tests previously reported passing | Script/test commits listed in Section 2 | Actual quote capture remains not run |
| 2026-11-15 | Read-only Neon staging audit | 5Dollar opening-odds target audit | 763 eligible candidates; 0 quote observations | Project/branch/database listed in Section 2 | Capture still outstanding |
| 2026-11-15 | PR #120 head `1b50d53edd8388dbf4c9df0b04e792956fee50d0` | Repository state inspection | PR draft/open/unmerged; Community probe stale rights contract identified | `scripts/phase2_fivedollar_history_dry_run.py`; `tests/test_phase2_data_foundation.py` | Correct before workflow execution |
| 2026-11-15 | [Workflow #43726672957](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957), job `132850009142`, commit `90d984091fdde520da4126842fb5301e5a8c0990` | Community rights regression + bounded 365-day qualification | PASS — 59 tests; 2,505/2,505 importable; 7/7 competitions; pagination complete; 28/40 requests; read-only; non-PIT | [Artifact #14166776290](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957/artifacts/14166776290); report SHA-256 `3bf4d797df92c293af6f346e296d3d76f7e7d9ec8988320d3992da1b5f6c668a`; ZIP SHA-256 `29e908f311ede85de1a8a8e1f824da54520da32073d0a26cb843ef033384ddea` | Community result labels only; no PIT admission |
| 2026-11-15 | [Workflow #43727169566](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566), commit `c86163a75a8f80914de9eb2fd2bd0b2265fa3ed7` | OpenFootball + FootballData archive capture and independent verification | PASS — OpenFootball 49 snapshots / 5,182 observation versions / 375 requests; FootballData 3 snapshots / 619 observation versions / 6 requests; both verifiers PASS | OpenFootball artifact [#14166223794](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223794), ZIP SHA-256 `3dd4e89fa9c3d766e3e044efc317a88c6147b232dbb2831402cde26302e7de03`; FootballData artifact [#14166223800](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566/artifacts/14166223800), ZIP SHA-256 `d8156a30d6b2f49032c157378385508fc8eefad931023ab2845255877c352acf` | Preserve both packs as retrospective evidence only; all rows non-PIT; no database/production writes |
| 2026-11-15 | [Workflow #43727509783](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783), job `132852553767`, commit `70b1a8ef1742975464f74dfefcf8dac265d46d86` | Bounded 5Dollar Community Bet365 1X2 opening capture | PASS — 26 tests; 25 fixture requests; 25 observations inserted; 25 timestamped PIT quotes; 26 provider requests including status preflight; quota 299→274 | Artifact [#14166689086](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783/artifacts/14166689086); ZIP SHA-256 `b8a6b0594294fdd4b6178ebab0e010c2a30fb15b87686c3ba30457dae82fd171`; summary JSON SHA-256 `f519f8c6cb085a1a04afdb8f7582ddb8c2fb1813eb2a4914345cc9e322ccdb54` | Staging manifest 109, 25/25 request rows and observations; 25/763 coverage (3.28%); 738 outstanding; no production writes/publication |
| 2026-11-15 | Read-only Neon SQL audit, `withered-sky-75161174` / `br-silent-violet-bc5de88s` / `veltrix_football_staging` | Reconcile 5Dollar fixture crosswalk and opening-quote PIT integrity | PASS — 763/763 fixtures exactly one active RESOLVED crosswalk; 25/25 captured quotes match canonical fixture, Bet365 1X2, valid prices, provider opening timestamp < kickoff, retrieved_at >= opening timestamp, HTTP 200 | Manifest `109`; provider response IDs `462–486`; source observation IDs `431621–431645`; 0 historical tick observations | Quote coverage 3.28%; 98% certification gate unmet; no 5Dollar Ultra history or The Odds API event/historical calls; no production writes |

### AI Midas authorization decision — 2026-11-15

| 2026-11-15 | User-confirmed authorization | AI Midas source authorization recorded | AUTHORIZED for non-commercial VELTRIX project work; technical dataset qualification remains pending | This ledger entry; project-wide non-commercial policy in `docs/legal/veltrix-all-source-noncommercial-authorization-2026-11-15.md` | Audit exact dataset provenance, seven-competition coverage, statistics and odds timestamp semantics before ingestion |

| 2026-11-15 | User-confirmed authorization; pinned AI Midas repository audit | AI Midas authorization, inventory and temporal qualification | PASS — authorization documented; inventory verified; PARTIAL technical qualification; 19,605 historical rows across six competitions; Brazil Série B 2026 advanced stats 369 matches; no PIT or closing-odds certification | `docs/legal/aimidas-noncommercial-authorization-2026-11-15.md`; `docs/VELTRIX_V2_AIMIDAS_DATASET_AUDIT_2026-11-15.md`; source commit `29baca362a34ce5dcd3924b07ec9c7d5139d83fc` | Build a pinned no-key snapshot artifact and exact fixture/team crosswalk; no database/model admission yet |

| 2026-11-15 | Workflow [#43752435643](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752435643), commit `4b666d6666b0aaf32daaa60a6ffb75cc2d76a306` | AI Midas pinned snapshot, privacy correction and independent verification | PASS — 7 tests; 14/14 files; 11,599,486 bytes; verifier PASS; prior raw artifact deleted; metadata-only artifact retained; no DB/production/model/prediction writes | Artifact [#14176976339](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752435643/artifacts/14176976339), SHA-256 `54ce4e05d6fd84f410c6723c181030ecde4376a10003ed6523ff9b536591b595`; audit `docs/VELTRIX_V2_AIMIDAS_DATASET_AUDIT_2026-11-15.md` | Define staging-only feature/observation import contract; preserve odds and PIT gates |
| 2026-11-15 | Read-only Neon query, branch `br-silent-violet-bc5de88s` / `veltrix_football_staging` | AI Midas Brazil Série B identity reconciliation | PASS — 20/20 teams; 369/369 unique fixture matches; 369/369 score matches; 0 unmatched/ambiguous source rows; 369/371 canonical fixture coverage (99.46%); no DB writes | Detailed method and date-offset counts in `docs/VELTRIX_V2_AIMIDAS_DATASET_AUDIT_2026-11-15.md` | Keep two absent fixtures quarantined; no date-to-UTC conversion; no PIT admission |
| 2026-11-15 | GitHub documentation commit `0a389b85bed5feabce1daaa7468c124a5b38522d` | AI Midas staging import contract | PASS — schema-level staging contract documented; design only; no DB writes or production changes | `docs/VELTRIX_V2_AIMIDAS_STAGING_IMPORT_CONTRACT_2026-11-15.md` | Implement staging importer only after crosswalk reviewer evidence and exact-head regression tests |

| 2026-11-15 | Workflow [#43752821538](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752821538), commit `6a932c00618616a33ac3be3642354717a7465954` | AI Midas artifact-cleanup idempotency regression | PASS — old raw artifact already absent; cleanup remained successful; collector + independent verifier passed; metadata-only artifact 2,807 bytes | Artifact [#14176614669](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43752821538/artifacts/14176614669), SHA-256 `02377544a7c9f361b441e641fcad37bc575e3dd16a43092355d3e3dd2123718a` | Keep raw files ephemeral; retain only metadata artifacts |
| 2026-11-15 | GitHub documentation commit `74646069f3edee33f4997f9355ad3e4e0d0db719` | Provider reference register AI Midas addendum | PASS — AI Midas added to consolidated provider reference register with authorization, scope, coverage and temporal limits | `docs/PROVIDER_REFERENCE_REGISTER.md` §5.4 | Keep register aligned with source audit and import contract |

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


### Opening-odds continuation update — 2026-11-15 (manifests 109–124)

- Manifests 109–124 are independently reconciled: 400/400 request rows, 400/400 provider responses, 400/400 opening quote observations, 400 distinct fixtures and 400 PIT-eligible observations.
- All 400 rows map to canonical fixtures, preserve valid provider opening timestamp ordering, use Bet365 1X2 and have active RESOLVED fixture crosswalks. No duplicates or ineligible rows.
- Coverage: 400/763 = 52.42%; 363 remain to full universe; 348 additional quotes are required to reach the 98% minimum (748/763).
- Latest completed batch: workflow [#43734920511](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734920511), artifact [#14170381591](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43734920511/artifacts/14170381591), SHA-256 `e45a5d9b092affa0e6cfd8a70f70c4695c2b81de83b1a5cce837655950490827`.
- Latest Community quota read-back: 16 remaining. This is below the next 25-fixture batch's required preflight headroom (26 including status); do not dispatch another capture until a fresh quota preflight after the 17:00 UTC reset.
- Formal decision remains **NO-GO — Stage 2 not complete / not release-ready**. See `docs/VELTRIX_V2_STAGE2_FINAL_EXIT_DECISION_2026-11-15.md`. Historical/closing odds entitlement and certification thresholds remain blocked. Stage 3 stays on hold.


### AI Midas historical identity reconciliation — 2026-11-15

- Read-only workflow [#43755219763](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43755219763) passed on code head `a951513f2518842a03b6305245b66b3591f5ced0`; 19 focused tests passed and all six pinned historical archives (19,605 rows) were audited.
- Canonical registry examined: 2,496 fixtures. It begins in November 2025, while the six historical archives end by 25 May 2025; no canonical fixture candidates were found.
- 6,495 source rows have both exact-normalized teams represented in the current registry but no fixture candidate; 13,110 rows have at least one team absent from the current registry.
- Exact duplicate groups: 0. Conflicting duplicate groups: 0.
- Raw source season/date values, source file pins, original line numbers and row fingerprints are preserved in the ephemeral detailed report. Sanitized aggregate artifact [#14178350008](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43755219763/artifacts/14178350008) contains no raw CSV or row-level detail.
- Database transaction was explicitly read-only. No normalized fixtures, results, entity crosswalks, model features or predictions were written. No mapping was marked `RESOLVED`.
- Full report: `docs/VELTRIX_V2_AIMIDAS_HISTORICAL_IDENTITY_RECONCILIATION_2026-11-15.md`.
- This identity audit does not supply historical PIT timestamps, closing odds, CLV or certification evidence. AI Midas rows remain non-PIT and model admission remains false.


### AI Midas Brazil Série B 2026 fixture identity reconciliation — 2026-11-15

- Dedicated audit target: canonical 5DollarFootballAPI Brazil Série B, provider competition ID 522514093, staging fixture universe 371 finished fixtures for calendar 2026.
- AI Midas file provenance rechecked: aimidas1/aimidas1@29baca362a34ce5dcd3924b07ec9c7d5139d83fc, advanced stats/Brazil Serie B 2026.csv, Git blob SHA-1 b6bdb94c053d2149e6232fb100e1f158e46e4533, 192,284 bytes; raw provider response ID 1238 / source observation ID 432397; response SHA-256 55b0c00629abd2d4ff3c31659ada950b67ffc2752609284b32c15c99f71152ab.
- Independent read-only SQL reconciliation: 738/738 source team rows, 369/369 match labels, 20/20 unique team identities; 369/369 unique canonical fixture IDs and 369/369 exact score agreements. All 738 team-level Goals / Goals Conceded fields agree with the source match-label score orientation.
- Date deltas: 333 same UTC calendar date, 36 canonical kickoff dates one day after the source date. Source date remains date-only; no inferred kickoff time.
- Two exact canonical fixture omissions: Náutico 1–0 Botafogo SP on 2026-09-03 (fixture 1927 / provider ID 3538579905), an unexplained omission inside the source file's date range; and Londrina 2–1 Náutico on 2026-11-11 (fixture 1807 / provider ID 1878457839), beyond the source file's 2026-11-08 maximum date. No replacements or synthetic mappings.
- Implementation adds stable per-row source IDs, canonical-row SHA-256 fingerprints, match-key hashes and a read-only audit workflow. Sanitized artifact excludes raw CSV content.
- Reviewer status: all 369 candidate identities are evidence-verified but remain REVIEW_REQUIRED; no reviewer acceptance event has been recorded and no crosswalk is marked RESOLVED. No crosswalk, normalized fixture/result or model-feature rows were written.
- Full report: docs/VELTRIX_V2_AIMIDAS_BRAZIL_SERIE_B_2026_IDENTITY_RECONCILIATION_2026-11-15.md.
- PIT, historical closing odds and CLV remain unqualified. AI Midas average odds do not satisfy bookmaker-specific closing-price or CLV requirements. Value betting remains LOCKED.


### AI Midas Série B team-stat row quarantine correction — 2026-11-15

- Independent recheck found 2/738 team-stat rows inconsistent with the match-label score: source CSV line 8 (CRB) reports 2–0 team goals/conceded while the Match label and canonical result are Náutico 0–3 CRB; line 9 (Náutico) reports 0–2 instead of 0–3.
- Match-level identity and canonical score remain verified for that fixture. The two team-stat rows are quarantined from advanced-stat feature admission; no values are rewritten or inferred.
- Correct team-row integrity count: 736/738 consistent, 2 quarantined. Match-level score agreements remain 369/369.
- The dedicated audit implementation now preserves both discrepancy row IDs and SHA-256 fingerprints in the sanitized artifact and labels the affected match QUARANTINED_ROW_SCORE_MISMATCH.
- This supersedes the prior 738/738 team-row consistency statement in the immediately preceding AI Midas Série B ledger entry. Full detail: docs/VELTRIX_V2_AIMIDAS_BRAZIL_SERIE_B_2026_IDENTITY_RECONCILIATION_2026-11-15.md.


### Historical odds source research continuation — 2026-11-15

- New highest-priority historical coverage candidate: The Odds API. Its official coverage page lists Brazil Série B historical data from 2022-06-30; featured-market snapshots are 5-minute intervals from September 2022. Historical prices are paid, while coverage-discovery endpoints cost 1 credit/request. Historical odds calls cost 10 credits per region per market. The snapshot timestamp and bookmaker/market last_update must both be preserved; quote-level freshness must be checked because a bookmaker's last_update can be materially older than the snapshot. This is a sampled pre-kickoff close proxy, not automatically an exact final sportsbook close.
- Odds-API.io: timestamped bookmaker-specific historical closing lines since December 2025; bulk endpoint supports 10 leagues, 366 days, 30 bookmakers and 100 events/page; paid bulk access starts at £49/month. Brazil Série B league support remains unverified; do not purchase before confirming league slug and market coverage.
- SockOdds: Pro-only per-change history with observed_at; Brazil Série B not in its earlier-history league list, and unlisted leagues begin 2026-10-08. Supplementary only, not a deep Brazil Série B archive.
- Odds.School: public Brazil Série B pages show 49 sportsbooks (18 in selected analysis) and per-bookmaker update times, but archive completeness and bulk/API rights are unverified. No scraping until written permission.
- SharpPick: public page reports 130 Brazil Série B matches / 20,710 snapshots at 5-minute intervals; terms prohibit bulk crawling/scraping or redistribution without permission, and bookmaker-specific quote identity is not established. No automated ingestion.
- Betfair Historical Data: timestamped exchange data since 2015, but exchange back/lay prices are not bookmaker prices. Separate benchmark only.
- OddsIntel Data: consensus closing price and close_ts since 2026-10-10, but no bookmaker names; not eligible for bookmaker-specific closing-price certification.
- The existing 5Dollar opening-odds continuation remains 400/763 (52.42%); 348 additional quotes required to reach 748/763 (98%). No API requests or paid odds captures were made during this research.
- Next acquisition step: fresh The Odds API quota preflight, followed by low-cost coverage-only discovery and a fixture × bookmaker × market × timestamp coverage matrix. Do not request paid price snapshots until coverage and quota headroom are known.
- Full research report: docs/VELTRIX_V2_HISTORICAL_ODDS_SOURCE_RESEARCH_2026-11-15.md.
- Historical closing odds remain NOT QUALIFIED; CLV remains NOT CERTIFIED; PIT walk-forward remains NOT MET; value betting remains LOCKED.


### Brazil Série B audit execution proof — 2026-11-15

- Workflow run 43758559130: dedicated aimidas-brazil-serie-b-identity job SUCCESS; 21 focused tests passed.
- Sanitized artifact 14178319188; ZIP SHA-256 4b8c0ed7489cf82dd48c34ca1ba55f884ae5fe652fb2190c919139721a764500.
- Row-level evidence: 738 unique source row IDs and SHA-256 fingerprints, 369 unique match-key hashes, 369 unique canonical fixture IDs. Raw CSV content was not uploaded.
- Final disposition: 369 match-level identity/score candidates verified; 2 missing canonical fixtures unresolved; 2 team-stat rows quarantined; reviewer acceptance pending; 0 crosswalk writes; value betting LOCKED.


### The Odds API competition-scope gate — 2026-11-15

- Live staging approval check confirms approval-the-odds-api-v4-owner-authorized-2026-11-14 is APPROVED for collection, storage, benchmarking and model training, but its competition scope is limited to five keys: soccer_epl, soccer_spain_la_liga, soccer_germany_bundesliga, soccer_italy_serie_a and soccer_france_ligue_one. Raw redistribution is prohibited.
- Brazil Série B is outside this approval. Public technical API coverage does not authorize Veltrix ingestion. No Brazil Série B prices were requested or stored; the two Brazil events/markets discovery exercises were metadata-only, not persisted, and are excluded from admitted data. Do not make further Brazil requests to The Odds API unless the approval scope is formally expanded.
- Brazil metadata discovery trail: Londrina–Náutico was absent from the 2026-11-11 21:50:36 snapshot (1 credit); Ponte Preta–Operário PR was found in the 2026-11-12 21:50:36 snapshot with 16 providers, 1X2 three-way listed for 16, totals for 13, BTTS for 3; the 16 includes two exchanges. Total discovery credits used including a parser retry: 5. Latest account quota evidence: 210 used / 290 remaining. No price endpoint calls or database writes.
- Continue historical price pilot only within the five approved European competitions. Candidate fixture: Atletico Madrid vs Barcelona, 2026-11-08 20:00 UTC, canonical fixture ID 1426, Spain La Liga. Require exact event identity and pre-kickoff quote timestamps. Store raw response only in staging; never upload raw price data to public artifacts.
- Value betting remains LOCKED; historical closing odds and CLV remain NOT CERTIFIED.


### The Odds API historical price entitlement result — 2026-11-15

- Current approved source scope remains five European competitions only: EPL, La Liga, Bundesliga, Serie A and Ligue 1. Brazil Série B is not authorized under the current approval.
- The approved La Liga sample reached historical event and market discovery, but the historical event-odds endpoint returned HTTP 401 with the provider message that historical odds are only available on paid usage plans. The official error catalogue maps this to the paid-plan restriction. No odds prices were returned or stored.
- Final no-credit quota probe at 2026-11-15 20:50:40 UTC: 226 used / 274 remaining; approved La Liga sport key present.
- Credit reconciliation from the 295-remaining checkpoint: 5 Brazil metadata-discovery credits (outside source scope, not admitted), 6 La Liga event/market discovery credits, 10 credits consumed by the rejected paid historical-price request; total 21 credits used, 274 remaining.
- Read-only staging verification: 0 pilot provider_responses, 0 pilot source_observations, 0 normalized odds_quote_observations. No production writes, predictions, or Telegram messages.
- The capture script is now fail-closed until paid historical-price entitlement is confirmed. Do not retry the price endpoint or spend more credits under the current account.
- Historical closing odds: NOT QUALIFIED. CLV: NOT CERTIFIED. PIT walk-forward: NOT MET. Value betting: LOCKED.

### AI Midas Brazil Série B 2026 identity reconciliation — 2026-11-15

- **Verified:** 20/20 source team identities map uniquely to 20 canonical team registry IDs; 738/738 source rows fingerprinted; 369/369 match groups map uniquely with exact home/away orientation; 369/369 Match-label scores agree with canonical fixture results.
- Source-to-canonical date deltas: 333 same UTC calendar date, 36 one-day offset (source date is date-only; no timezone inference).
- **Quarantine:** two team-stat rows in one match conflict with the Match-label/canonical score. For Náutico 0-3 CRB (source 2026-11-07; canonical fixture 1811 / provider fixture 4070869087), the team rows state 2-0. Source line 8 row SHA-256 78d9492295da1b8dfa9ef735b786f63412089a37640b1f01aa3d57395707abc6; line 9 SHA-256 ce5bf78a5090a5bef9997ae65c3b5a8e864e117218ed0404e59384b57a62bfb4. Match label agrees with canonical 0-3, but both advanced-stat rows are quarantined.
- Two canonical fixtures have no source row: Náutico 1-0 Botafogo SP, 2026-09-03 23:00 UTC (fixture 1927 / provider 3538579905), absent despite being inside source date range; Londrina 2-1 Náutico, 2026-11-11 22:00 UTC (fixture 1807 / provider 1878457839), after source file's last date 2026-11-08. Exact reasons are recorded in the report; neither has a replacement mapping.
- Reviewer acceptance remains pending. No crosswalk rows resolved/written, no normalized fixtures/results or model rows written, and no database mutation.
- Workflow [#43761387345](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43761387345) passed at code head a55dc20a385a82e6886946850f1aec3b4971ebe5. Full report artifact [#14180247939](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43761387345/artifacts/14180247939), ZIP SHA-256 33f0b1f78f3dd0cf4993b9957e99f562386f8d4c6f56123ad6490dc1dd29cd47. The artifact contains all 369 match candidates, 738 row fingerprints, 20 team mappings and both unmatched fixtures, without raw advanced-stat values.
- AI Midas remains non-PIT and model-ineligible. Its average odds are not timestamped bookmaker closing odds or CLV evidence. **Value betting remains LOCKED.**


### Historical odds provider continuation — 2026-11-15

- The Odds API no-credit preflight [#43760295591](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43760295591) passed: approved Spain La Liga key available; Brazil Série B key technically discoverable but not in the five-league rights approval. Quota was 226 used / 274 remaining, with zero credits spent by preflight.
- The approved La Liga historical price pilot reached the provider but received HTTP 401 because historical odds are paid-plan-only. No price response was captured, no source observation or normalized quote was written. The capture code remains fail-closed until paid historical entitlement is confirmed. Do not retry the paid-only route on the existing plan.
- No Brazil Série B The Odds API price request is authorized; technical sport-key availability does not expand the source approval.
- Provider screening completed: Odds-API.io is the strongest technical candidate for the five approved European leagues (timestamped bookmaker-specific closing ML/1X2, archive since Dec 2025, 366-day bulk window), but starts at £49/month, has no new free keys, has no published Brazil Série B confirmation, and is not yet an approved Veltrix source. ParlayAPI has separate historical odds/closing endpoints but its terms require a signed agreement for public/customer-facing derived products and cap line-level retention at 90 days absent written consent; Brazil Série B coverage unverified. SockOdds does not list Brazil Série B in its published league catalogue and history is Pro-only. OddsRelay history starts 17 Oct 2026, is UK & Ireland-focused and requires Enterprise for business use. OddsIntel does not provide bookmaker identities and excludes betting operators/affiliates. Public Odds.School/SharpPick pages are leads only; no scraping or ingestion.
- No new provider was authorized, no subscription/payment was made, and no alternative prices were ingested. Historical closing odds and CLV remain NOT CERTIFIED. **Value betting remains LOCKED.**
- Detailed comparison and source links: docs/VELTRIX_V2_HISTORICAL_ODDS_SOURCE_RESEARCH_2026-11-15.md, section 8.


### AI Midas Brazil Série B crosswalk acceptance — 2026-11-15 21:13:49 UTC

- Workflow [#43762497871](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43762497871) passed at code head cb30b76ba8446170eb8639fe58789dca7176d8c2. Acceptance artifact [#14180892673](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43762497871/artifacts/14180892673), ZIP SHA-256 1870fc9066afed1ee0cc0db11911270808408cc77dee34013b3d63e5ce20ac81.
- Independent automated reviewer ID: automated-independent-reconciliation-v1.
- Staging crosswalk registry now contains 389 RESOLVED mappings: 20 TEAM (10 exact names, 10 explicit aliases) and 369 FIXTURE (exact team orientation/date/score evidence). All 389 rows link evidence observation 432397; staging read-back confirmed all reviewer IDs and unique canonical/source IDs. valid_from is 2026-11-15T21:13:49.803Z; no backdating.
- The two unmatched canonical fixtures (1927 Náutico–Botafogo SP and 1807 Londrina–Náutico) remain unresolved with no replacement mappings.
- Canonical fixture 1811 identity is resolved from the Match label and canonical score, but its two inconsistent team-stat rows (source lines 8–9) remain quarantined.
- Only entity_crosswalk_versions was written in staging. No normalized fixture/results, advanced-stat features, odds, predictions or production rows were written. No deployment, publication, Telegram or schedule changes.
- The reviewer ID is automated, not a human signature. If a named human sign-off is later required by governance, it must be recorded separately.
- All AI Midas observations remain non-PIT and model-ineligible; closing odds/CLV remain uncertified. **Value betting remains LOCKED.**


### Odds-API.io historical closing-line coverage refinement — 2026-11-15

- Official docs now provide stronger technical evidence than the initial screening: bulk /v3/historical/closing-lines is a paid endpoint with up to 10 leagues, 366 days, 30 bookmakers and 100 settled events per page; per-event /v3/historical/odds is available on every plan but requires an API key. New free keys are paused.
- The historical guide's example includes a bookmaker-specific ML 1X2 price with an updatedAt timestamp before kickoff and final score. Public settled coverage lists 331 EPL, 349 LaLiga, 349 Serie A, 272 Bundesliga and 263 Ligue 1 matches, with median 98–105 bookmakers per match; Brazil Série A has 339 matches since 28 Jan 2026. These five European leagues alone show 1,564 settled events, but exact fixture overlap with Veltrix's 763-fixture universe still requires a canonical coverage audit.
- Brazil Série B is not listed in the published historical coverage table. The 2,159 football league count does not prove Série B coverage; treat it as UNVERIFIED until a provider catalogue/API response confirms its league slug and actual settled prices.
- Solo plan starts at £49/month for two bookmakers; new free keys are paused. Bulk closing lines is paid. A candidate plan would need Bet365 plus a second benchmark book, but bookmaker availability per league must be confirmed first.
- Terms permit statistical analysis, data modelling and application development; raw odds resale/redistribution needs written consent. The homepage advertises website/app display, including paid products, but obtain written confirmation for the exact Veltrix public display/derived-output use before onboarding.
- Odds-API.io is now the strongest technical candidate for historical bookmaker-specific closes across the five approved European leagues, but it is NOT yet a Veltrix-authorized source. No key, subscription, payment or data ingestion occurred. A provider-specific rights approval and budget decision are still required.
- The Odds API remains blocked for historical endpoints on the current key (HTTP 401 paid-plan-only) and its existing rights scope remains five European competitions. No successful historical price response or CLV observation exists. Value betting remains LOCKED.


### Independent staging read-back and report synchronization — 2026-11-15 21:27 UTC

- Independently queried Neon project `withered-sky-75161174`, branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging` after acceptance workflow #43762497871.
- Confirmed 389 RESOLVED AI Midas crosswalk rows: 20 TEAM and 369 FIXTURE; all rows have reviewer `automated-independent-reconciliation-v1` and evidence observation `432397`; zero missing references and zero evidence orphans.
- Source and canonical identifiers are one-to-one in both directions: no duplicate source-to-canonical or canonical-to-source mappings.
- Confirmed the two canonical fixtures absent from the AI Midas source remain unresolved with no replacement mappings. The two conflicting team-stat rows remain quarantined.
- Normalized-data isolation: Brazil Série B 2026 remains 371 fixtures / 371 result rows; zero fixture rows were created and zero result rows were observed during the acceptance interval. Acceptance wrote only `entity_crosswalk_versions` in staging.
- Synchronized the dedicated identity-reconciliation report to the accepted state and clarified that its zero-write side-effect section applies only to the earlier read-only audit: `docs/VELTRIX_V2_AIMIDAS_BRAZIL_SERIE_B_2026_IDENTITY_RECONCILIATION_2026-11-15.md`. Report commits: `3efb836fdab8c6529bfe4924c17172a3c7c97ef9`, `726edd84ae199b98e7b83dc648d14a477f413a96`.
- No model admission, normalized fixture/result writes, odds writes, production writes, deployment, publication, Telegram delivery or schedule activation. Value betting remains LOCKED.
- Next: continue closing-odds and CLV source research separately; preserve opening-odds evidence as opening-only. PR #120 remains draft/open/unmerged and no merge/release authorization is implied.


### Prospective odds, settlement and OddsPapi qualification audit — 2026-11-15

- Re-read the current PR #120 branch and Neon staging state. PR #120 remains open/draft/unmerged. The previously accepted AI Midas mappings remain present: 20 TEAM + 369 FIXTURE RESOLVED rows, with zero missing reviewer/evidence references. The two source-absent fixtures still have zero AI Midas fixture-crosswalk rows. No crosswalk writes were made in this audit.
- Reconfirmed 5Dollar opening quote evidence: 763/763 distinct fixtures, 763/763 PIT-eligible **opening** quotes, all using provider timestamp basis and provider opening timestamp basis. This supersedes older 400/763 and 750/763 checkpoints. It does not establish timestamped closing odds or CLV.
- Read-only result audit: 2,496 `fixture_results` rows, all linked to source observations and rights approvals, with availability basis `provider_finished_status_conservative_4d`. This can support conservative post-match settlement-label availability after exact fixture/result checks; it is not pre-match feature availability and must not be backdated.
- Read-only paper-ledger audit: 25 `SHADOW_PREDICTION` events; all are from `veltrix-results-poisson-v1`, all carry `point_in_time_certifiable=false`, none has an odds snapshot reference or settlement reference. Kickoffs span 18–21 November 2026. These V2 Poisson v1 first-observed non-PIT records do not count toward the 300 settled prospective selection or 90-date market gates and must not be upgraded in place. No new model forecasts were generated in this audit.
- Existing `ingestion_quarantine` table currently has zero rows; the two AI Midas contradictory team-stat rows remain excluded/quarantined in the source reconciliation/import evidence and were not promoted to normalized feature rows. Do not confuse the audit-level two-row quarantine with records in the generic ingestion quarantine table.
- New provider research: OddsPapi v4 historical odds returns per-bookmaker timestamped snapshots (`createdAt`, price, limit, active), up to three bookmakers per fixture call; 5-second endpoint cooldown; ETag support for settled fixtures. Vendor material states 250 free requests/month and up to 100 days of history per fixture, with depth varying. Brazil Série A tournament ID 325 and Brazil Série B ID 390 are identified in its public guide. Separate scores and settlements endpoints provide period scores with `updatedAt` and per-outcome grades. This is the strongest new technical candidate, but not approved: published terms do not explicitly grant VELTRIX's intended raw-response retention/model-training/backtesting/derived-display rights; 100-day depth and exact 7-competition event coverage remain unverified. No API calls, source observations, approval row, subscription or payment were made.
- Created qualification report: `docs/VELTRIX_V2_ODDSPAPI_HISTORICAL_ODDS_QUALIFICATION_2026-11-15.md` (commit `9aee593fd17838c5b259da65bd2b6c88f1b1b5fe`) and added provider screening detail to `docs/VELTRIX_V2_HISTORICAL_ODDS_SOURCE_RESEARCH_2026-11-15.md` (commit `083ac077d219d8c9ec5178f3990ec837a59932ff`).
- 5Dollar source position: opening coverage is complete at 763/763. Its fixture odds response only provides an explicit timestamp on the opening object; closing values lack a quote-level timestamp. Its timestamped tick-history endpoint is Ultra-only. The account's Ultra entitlement is not evidenced. No plan upgrade/payment was initiated.
- Report-verifier/publication infrastructure remains fail-closed. The existing raw certification verifier requires seven hash-bound artifacts, validates source pointers and timestamps, recomputes metrics, and cannot authorize release without trusted rights verification and attestation. Existing exact-head CI on `e0720a2020bf2ce28ed6e959c06de14a44cfaa25` had 12 successes, 3 expected skips and zero failures; documentation changes now trigger a fresh exact-head CI run. Do not treat this earlier CI as validation of the new documentation commit until the new checks complete.
- Certification targets unchanged: per market ≥1,000 walk-forward fixtures; ≥300 timestamped prospective settled selections across ≥90 distinct Africa/Lagos dates; ≥98% timestamped odds coverage; net ROI >0 with date-clustered 95% lower bound >0; 1X2 Brier and log loss better than de-vigged bookmaker benchmark on identical fixtures/cutoffs.
- No production/normalized fixture/result writes, odds ingestion, model admission, PR merge, deployment, publication, Telegram delivery or schedule activation. Value betting remains LOCKED.

**Next:** secure written OddsPapi rights clarification before any provider request; independently determine 5Dollar Ultra entitlement without changing plan; keep the new V2 model's prospective predictions separate from the 25 V2 Poisson v1 first-observed non-PIT shadow records; collect and settle only with exact source/quote/fixture provenance; continue report-verifier CI and record each run here.


### Persistent AI Midas quarantine and non-commercial certification-gate correction — 2026-11-15

- The staging read-back found the two contradictory AI Midas rows existed in the reconciliation evidence but the generic `ingestion_quarantine` table was empty. To make the requested quarantine durable and queryable, inserted exactly two open staging quarantine records (IDs 1 and 2) for CSV lines 8 and 9, linked to pinned dataset observation 432397. Both preserve provider row IDs, exact SHA-256 row fingerprints, source commit/path, canonical fixture 1811, provider fixture 4070869087, observed values, expected-from-match-label values, reason `SOURCE_TEAM_STAT_SCORE_CONFLICT`, and disposition `QUARANTINED_NO_FEATURE_ADMISSION / UNRESOLVED_DO_NOT_REWRITE`.
- Independent post-write read-back: 2/2 quarantine rows remain open, 2/2 link to source observation 432397, and both fingerprints are distinct. Feature admission remains empty: 0 `feature_snapshots`, 0 `feature_snapshot_links`, 0 `feature_snapshot_eligibility_events`. No normalized team-stat or model feature writes occurred.
- Crosswalk invariants rechecked after quarantine persistence: 389 resolved mappings remain (20 TEAM + 369 FIXTURE); no mapping exists for canonical fixtures 1927 and 1807. No crosswalk rows were changed.
- Found a certification-infrastructure policy contradiction: `app/certification_metrics.py` required `commercial_use_eligible=true`, while the owner-confirmed VELTRIX project policy is NON-COMMERCIAL ONLY and source approvals explicitly prohibit monetisation. Corrected the raw certification rights gate to require `project_use_mode=NON_COMMERCIAL_ONLY`, `noncommercial_use_eligible=true`, `commercial_use_eligible=false` and `raw_redistribution_allowed=false`, while retaining the independent provider-rights verifier requirement and exact approved source IDs. Added parametrized fail-closed tests for commercial eligibility, disabled non-commercial eligibility, wrong use mode and raw redistribution. Updated both raw evidence contract and certification bundle specification.
- Certification-gate correction commits: `42e76a85f377f45c6211590085ce60af14ae2782`, `ad62fd6ca6bb74e4cfe83447f9b4d2c210806f25`, `479a8a99967ad64ba47884ec1f1057329f1d3abd`, `f4227a3dfe50ba7f04baabd4c4622112dfff079d`.
- Updated the AI Midas reconciliation report with the persistent quarantine IDs and read-back evidence (commit `28e014fe04bc397c6bd937bbe7862d004b0d66d9`).
- This is a source-rights/policy correction to the V2 evidence verifier, not a change to the legacy prediction or calibration models. The 25 V2 Poisson v1 first-observed non-PIT shadow forecasts remain excluded from certification. No OddsPapi API requests or imports were made; rights remain unapproved. No production writes, deployment, prediction publication, Telegram delivery, schedule activation or PR merge.
- Exact-head CI is expected to rerun after these commits; do not claim success until checks for the final PR HEAD complete.

**Next:** retrieve the final exact-head CI results, especially certification evidence integrity, PostgreSQL 16/18 acceptance, Phase 5 shadow regression and AI Midas identity audit. Continue provider rights qualification and prospective odds/settlement capture only through an approved source; value betting stays LOCKED.


### Certification CI failure analysis and correction — 2026-11-15

- The first CI run after the non-commercial rights-gate change failed in the certification-evidence job: run [#43766606827](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43766606827). Result: 107 passed, 2 failed. Both failures were test-contract drift, not verifier logic: (1) the unapproved-rights test expected the phrase `approved rights`, while the new error text inserted `non-commercial` between those words; (2) the certificate-builder test fixture still declared `commercial_use_eligible=true` and omitted the new non-commercial fields.
- Corrected the failure message to preserve the stable `approved rights` phrase and updated the builder test fixture to the required non-commercial schema. Commits: `2a63dd57792e7fa74094bdb7b71114a369c00f42`, `e30df7d9013838c1323011038aedea442f35d8c3`.
- The new exact-head CI run for `e30df7d9013838c1323011038aedea442f35d8c3` is now running (certification evidence run [#43766778468](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43766778468); Phase 2, shadow regression, historical model audit and AI Midas checks also triggered). Do not treat it as passed until all required jobs complete.


### Prospective 5Dollar opening-quote capture workflow — 2026-11-15

- Extended the existing non-commercial, staging-only 5Dollar capture path to support a separate `prospective` mode over the next 1–7 days, bounded to at most 25 fixtures per run. The historical mode remains available with its existing 1–90 day lookback.
- The prospective path reuses the already approved 5Dollar `odds_quote` source approval and the existing exact fixture/team/competition crosswalk checks, status/quota preflight, 3.1-second request spacing, no-retry policy and staging DSN guard.
- It captures only Bet365 1X2 **opening** quotes with provider `opened_at`, separate retrieval time, raw provider response hash, and immutable response/source-observation provenance. It explicitly reports `closing_odds_qualified=false` and `clv_certified=false`; opening prices are not represented as current, closing or executable prices.
- Updated the manual workflow's push-trigger default to one prospective 7-day batch (maximum 25). No daily schedule, production write, model prediction, selection, Telegram delivery or publication is enabled. The quota preflight fails closed if the account cannot cover the planned fixture requests.
- Added tests for historical/prospective window boundaries, timezone awareness, invalid mode/range rejection, and opening-only/non-CLV dry-run semantics.
- This single commit is expected to trigger one bounded prospective capture workflow using existing GitHub Actions secrets; the actual API/DB result must be retrieved and independently verified before claiming any quote rows were acquired.


### Prospective opening-quote capture attempt 1 — 2026-11-15

- The new bounded 7-day prospective capture workflow was triggered by the single branch push: [run #43766983519](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43766983519).
- It stopped at the parser/safety-test step before the dry run or API execution because the script's updated module docstring was missing its closing triple quote, producing an `IndentationError`.
- Confirmed execution boundary: no 5Dollar status preflight, no fixture API calls, no database connection or writes occurred in this failed attempt. No provider quota was consumed by the capture job.
- Fixed the docstring terminator. The next push will rerun the same bounded prospective 7-day batch (maximum 25 fixtures), subject to parser tests and the existing live quota preflight. This remains opening-only evidence; it is not a closing price or CLV observation.


### Prospective opening-quote capture attempt 2 — 2026-11-15

- After fixing the module docstring, the second workflow attempt [#43767046125](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43767046125) reached the test suite and failed one existing test that called the refactored private `_load_targets` helper without the new `mode` and `future_days` arguments. The other 32 tests passed.
- The workflow stopped before dry-run, quota preflight, provider API calls or database connection. No API quota was consumed and no staging writes occurred.
- Updated the existing competition-scope test for historical mode and added a prospective-window test verifying the SQL bounds are exactly `now` through `now + 7 days`, with the approved Brazil Série B competition scope. A fresh bounded run will execute on the next branch push.


### 5Dollar scheduled-fixture discovery blocker and safe path — 2026-11-15

- The bounded 7-day opening-quote capture workflow completed successfully as run [#43767115313](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43767115313), but its aggregate summary was a no-op: 0 eligible future canonical fixtures, 0 provider requests, 0 opening quotes and 0 database writes. A read-only staging query confirmed there are currently no future 5Dollar fixture rows/crosswalks in the canonical fixture registry within 7, 14, 30 or 90 days.
- This is a fixture-discovery gap, not an odds-provider outage. The 5Dollar scheduled-fixture API path already exists in `scripts/phase5_collect_5dollar_shadow.py`, but the existing workflow couples it to the V2 Poisson v1 first-observed shadow model and paper-ledger admission. That coupling must not be used as a shortcut for odds capture.
- Added an explicit `--fixtures-only` path that persists only bounded raw provider fixture snapshot evidence in staging. It returns before importing or executing `veltrix_v2.models.engine.predict_batch`, and guarantees zero normalized fixture/result, feature, odds-quote, prediction or paper-ledger writes. It uses the existing 5Dollar fixture-result approval, 7-league scope, team/competition crosswalk checks, 14-request cap, 1–14 day upcoming window and 25-target cap.
- Updated the Phase 5 workflow to a one-time push-triggered fixture-evidence-only run with 90-day finished snapshot lookback, 14-day scheduled window and 25-target cap. No scheduled trigger was added. It will not generate predictions or activate any publication path.
- Corrected source documentation to describe the 25 existing ledger events accurately as V2 Poisson v1 first-observed non-PIT shadow records, not assumed legacy-model records. They remain ineligible for the market certification selection thresholds because they lack timestamped odds-snapshot and settlement links and are not PIT-certified.
- The 5Dollar opening-quote capture run [#43767115313](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43767115313) did not call the provider because no future canonical fixture targets existed. The new fixture-only discovery run will be independently inspected before any further odds-capture changes.


### Fixture-only discovery workflow attempt 1 — 2026-11-15

- The first fixture-only workflow run [#43767399295](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43767399295) stopped during dependency installation before tests, dry-run, API calls or database access.
- Failure: workflow used `pip install -e .`, but this repository has no `setup.py` or `pyproject.toml`. No provider quota was consumed and no staging writes occurred.
- Corrected the workflow to install the pinned project dependencies from `requirements.txt` plus psycopg, matching the existing Phase 2 capture workflow. The next push will retry the same 14-request maximum / 14-day fixture-only discovery with no model import or paper-ledger writes.


### Fixtures-only Phase 5 regression test correction — 2026-11-15

- The full Phase 2 foundation test run for commit `136aa8c27d72706c45e009e26be557e37609dab5` exposed two failures in `tests/veltrix_v2/test_phase5_5dollar_shadow_capture.py`. Those tests monkeypatched a module-level `capture.predict_batch`; the safe fixtures-only refactor intentionally removed the top-level model import and now imports `predict_batch` lazily only in the prediction branch.
- Corrected the tests to patch `veltrix_v2.models.engine.predict_batch` at its actual lazy-import source. This preserves the production guarantee that fixture-only capture does not import or execute the model while keeping the non-fixtures-only orchestration tests deterministic.
- This test-only correction does not touch the fixture-only workflow paths, so it will not trigger a duplicate provider capture run. The active fixture-only run [#43767443333](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43767443333) continues independently.


### 5Dollar prospective fixture-only capture — independent staging verification — 2026-11-15

- Run [#43767443333](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43767443333) executed the fixture-only path. The command's final JSON-print step exited with `KeyError: duplicate_predictions_skipped`, but the capture and staging transaction had already completed. Aggregate-only artifact [#14183036801](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43767443333/artifacts/14183036801) reports `FIXTURE_SNAPSHOT_CAPTURE_COMPLETE`.
- Independent Neon read-back confirms 14/14 provider responses HTTP 200 and 14/14 capture manifests persisted. The seven scheduled pages contain 103 raw upcoming fixture rows across the approved competitions. The 25 existing prospective shadow target fixture IDs are all present in those scheduled snapshots (25/25); team, away-team and competition crosswalks resolve 25/25; exact provider fixture ID, home/away provider team IDs, provider competition ID and kickoff timestamp match 25/25.
- The seven finished pages yielded 671 source-observation rows (660 accepted first-observed rows + 11 rejected), all explicitly non-PIT. No normalized fixture rows, normalized result rows, feature snapshots, feature links, feature eligibility events, odds quote rows or paper-ledger events were written by this fixture-only run. The AI Midas quarantine remains 2 open rows.
- Fixed the fixture-only summary helper to include `duplicate_predictions_skipped: 0` and documented the run's successful data persistence despite its final CLI summary-print failure.
- The 25 prospective targets are source-scoped shadow fixture IDs, not new canonical fixture rows. They are mapped through existing 5Dollar team and competition crosswalks; no fixture crosswalks were invented. The opening-odds collector now reads these target IDs from the existing paper ledger and requires an exact match against a fresh scheduled provider page plus valid team/competition crosswalk versions. It stores opening quote observations with `canonical_fixture_id=null`, the pseudo ledger fixture ID, source prediction event hash, original and current fixture-snapshot hashes, and team/competition crosswalk evidence. These are source-level observations only.
- The existing V2 Poisson v1 forecasts have `PROSPECTIVE_OBSERVED_ONLY` evidence and `point_in_time_certifiable=false`. Because the new opening quote capture occurs after their original prediction cutoff, every associated quote carries `market_selection_eligible=false` and `clv_eligible=false`; it must not be counted as a selection-time price for those forecasts. The opening quote itself retains its own provider `opened_at` timestamp and retrieval timestamp for future evidence use.
- No prediction or settlement event was appended. The 25 existing fixtures have kickoffs 18–21 November 2026; the separate manual settlement workflow remains pending until fixtures finish and the documented conservative 4-day result-availability delay is satisfied.


### Prospective opening-quote collector test correction — 2026-11-15

- The first prospective target-loader CI attempt [#43768125737](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43768125737) failed one test before dry-run or provider access: the new mocked-target test used `timedelta` without importing it. The other 34 tests passed.
- Added the missing local import. The workflow stopped before quota preflight, provider requests or database connection; no API quota or staging writes were consumed by this attempt.


### Fixture-only capture output and trigger safety hardening — 2026-11-15

- Fixed the final summary printer's missing `duplicate_predictions_skipped` field by explicitly setting it to zero in fixtures-only mode and added a regression assertion.
- Changed the fixture-only workflow job to run only on explicit `workflow_dispatch`. Its one-time push-triggered discovery has already run; future source-code or documentation pushes will not silently repeat provider requests. No schedule trigger exists.
- The initial fixture-only data capture remains independently verified in Neon and in aggregate artifact #14183036801. The workflow's failure was after persistence, at the final summary print; this patch makes the no-model path return a complete, stable summary on future manual runs.


### Prospective opening-odds target query correction — 2026-11-15

- The prospective opening-quote workflow run [#43768185582](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43768185582) passed all 35 parser/safety tests and the dry-run, then stopped during the read-only staging target query. Psycopg interpreted the literal SQL `LIKE '%'` as a placeholder and raised `ProgrammingError: only '%s', '%b', '%t' are allowed as placeholders, got '%'`.
- This occurred before quota preflight or any provider fixture request. No API quota was consumed and no odds rows were written.
- Replaced the literal-percent `LIKE` expression with PostgreSQL `POSITION(... IN request_id)` matching, and strengthened the prospective target-loader test to assert the placeholder-safe query. The next bounded attempt will re-run the 25-target exact identity check before making any provider requests.


### Prospective opening-odds SQL alias correction — 2026-11-15

- The next opening-quote workflow attempt [#43768280700](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43768280700) passed all parser/safety tests and dry-run, then stopped in the read-only prospective target query with PostgreSQL `AmbiguousColumn: provider_competition_id`. The candidates CTE and verified competition join exposed the same column name.
- Failure occurred before quota preflight and before any fixture endpoint calls. No provider quota or odds rows were consumed.
- Aliased the verified competition mapping as `mapped_provider_competition_id` and explicitly selected it as the final provider competition field; added a regression assertion. The next run will retry the same bounded 25-target query.


### Prospective opening-odds duplicate target correction — 2026-11-15

- The prospective opening-quote workflow attempt [#43768345812](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43768345812) passed all parser/safety tests and dry-run, then stopped in the read-only target loader with `PROSPECTIVE_SHADOW_TARGET_DUPLICATE`.
- Investigation: multiple fresh scheduled-page responses within the 24-hour evidence window can contain the same provider fixture ID. The query correctly found the 25 unique paper-ledger target IDs but returned repeated rows from those multiple page snapshots.
- Added a deterministic `DISTINCT ON (provider_fixture_id)` selection ordered by the latest current snapshot fetch timestamp, while preserving the independent exact team/competition/kickoff identity predicate and the 25 unique-target assertion. Added a regression assertion.
- The duplicate check failed before quota preflight, provider fixture requests or any database writes. No API quota was consumed.


### Prospective 5Dollar odds capture and latest pre-match snapshot backfill — 2026-11-15

- Opening quote capture workflow [#43768424133](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43768424133) completed successfully on the prospective paper-ledger targets: 25 fixture-detail requests, all HTTP 200; 25 unique Bet365 1X2 opening observations persisted. Quota remaining after the batch: 260. All 25 opening quotes have provider `opened_at` timestamps; their opening times are approximately 16–21 days before kickoff, so they are not near-kickoff selection prices.
- The same 25 fixture responses contained complete Bet365 1X2 `closing` stage values (25/25), but no provider update timestamp (0/25). Official 5Dollar documentation says that for scheduled fixtures this `closing` stage is the latest pre-match price so far, and it freezes at kickoff; it is not a final close until kickoff. The response was collector-observed between 22:17:30 and 22:18:50 UTC, 3 days 12 hours to 5 days 16 hours before kickoff.
- Persisted the 25 values separately as `odds_latest_prematch_snapshot` using version-controlled SQL `db/ops/2026-11-15_fivedollar_latest_prematch_snapshot.sql`. Inserted source-observation IDs 433108–433132. Independent Neon read-back confirms 25 unique fixtures, 25 unique provider responses, 25 linked opening observations, correct rights approval on all rows, no provider update timestamp, `source_timestamp_basis=unknown`, `availability_basis=collector_first_observed_v1`, and `point_in_time_certifiable=false` on all 25.
- Every snapshot retains the pseudo paper-ledger fixture ID, prediction event hash, source response hash, current fixture-snapshot hash, team/competition crosswalk version IDs, opening quote observation reference and collector observation timestamp. `canonical_fixture_id` remains null; no fixture crosswalk or normalized fixture was invented.
- All 25 snapshots explicitly carry `market_selection_eligible=false`, `clv_eligible=false`, `final_close_observed=false`, and `captured_after_associated_prediction_cutoff=true`. The 25 associated V2 Poisson v1 forecasts remain `PROSPECTIVE_OBSERVED_ONLY` and non-PIT. These observations cannot count toward the 300 prospective settled market selections, 98% timestamped closing-odds coverage or CLV gate.
- Isolation read-back: zero normalized fixture writes, zero normalized result writes, zero feature snapshots/links/eligibility events and zero paper-ledger events from the odds capture/backfill. No production writes or publications.
- 5Dollar `/v1/fixtures/{id}/odds/history` provides tick-level `recorded_at` timestamps but is Ultra-only. No upgrade or payment is authorized. Historical closing odds remain NOT QUALIFIED; CLV remains NOT CERTIFIED; value betting remains LOCKED.
- The 25 associated fixtures kick off 18–21 November. Settlement remains pending until each fixture is finished and the existing conservative 4-day result-availability delay is satisfied. Settlement workflow remains manual-only; no schedule was activated.
- Disabled push-triggered reruns for the opening-odds workflow; future captures require explicit `workflow_dispatch`. No schedule trigger exists.
- Independent preservation check after these writes: AI Midas remains 20 TEAM + 369 FIXTURE resolved crosswalks (389 total), zero reviewer/evidence gaps, zero mappings for the two source-absent canonical fixtures, and exactly two open quarantined team-stat rows.


### Comparative provider qualification and refreshed staging integrity audit — 2026-11-15 23:26 WAT

- Independently re-read the Neon staging database after the earlier OddsPapi report. AI Midas crosswalk invariants still hold: 20 TEAM + 369 FIXTURE resolved; 20/20 and 369/369 source IDs and canonical IDs unique; zero duplicates; zero reviewer/evidence gaps; zero mappings for the two source-absent canonical fixtures.
- The two contradictory AI Midas team-stat rows are physically retained as exactly two open `ingestion_quarantine` rows with reason `SOURCE_TEAM_STAT_SCORE_CONFLICT`, provider fixture ID `4070869087`, canonical fixture ID 1811, source commit `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`, source path `advanced stats/Brazil Serie B 2026.csv`, lines 8–9, and original row SHA-256 values. Both remain unresolved; no source row was rewritten and no feature admitted.
- Read-only odds audit: 788 unique fixtures have timestamped 5Dollar opening observations (provider timestamp + provider opening timestamp + PIT true). This includes the frozen historical universe 763/763 plus a separate 25 prospective shadow-target opening captures. The separate 25 latest-pre-match `closing` field observations are a distinct set: source timestamp unknown, collector-first-observed only, PIT false, market-selection false, CLV false, final-close false, captured after prediction cutoff true. Do not count them as close or CLV evidence.
- Prospective ledger: exactly 25 SHADOW_PREDICTION events, all non-PIT; zero quote-snapshot links, zero settlements. Kickoffs span 18 Nov 2026 22:30 UTC to 21 Nov 2026 15:00 UTC (four WAT dates). No target is settlement-eligible yet. Existing 2,496 fixture result rows remain source/rights linked but are not these prospective settlements.
- No feature snapshots, feature links or eligibility events exist from this review. No odds rows, normalized fixture/result rows, paper-ledger events or production data were written.
- Provider comparison: 5Dollar Ultra is the most economical direct bookmaker-level tick history route if entitlement is already available ($25/month published); not entitled on current evidence. Odds-API.io is a technically strong bulk closing-lines alternative but its public coverage table lists Brazil Série A, not Série B; exact Série B and seven-competition coverage plus rights remain unverified. SockOdds has strong timestamped change and settlement semantics but no Brazil Série B in its current league catalogue; no prices delivered for Brazilian Série A. OddsIntel is consensus-only (no bookmaker names/raw lines), free Sample testing/evaluation-only, paid from €49/month; terms exclude betting operators/affiliates so written eligibility clarification is required. OddsRelay's archive starts 17 Oct 2026 and business requires Enterprise; TheRundown backtesting needs prior written permission. Full details: `docs/VELTRIX_V2_CLOSING_ODDS_PROVIDER_COMPARATIVE_QUALIFICATION_2026-11-15.md` (commit `0aaf7db4b97c70a0d5775c492424eae49a4d5aa0`).
- No API keys were requested, no provider requests/credits were consumed, no provider account was created, no plan changed, no payment made, and no new source-approval row or observation inserted.
- Certification gates unchanged: per market ≥1,000 chronological walk-forward fixtures; ≥300 timestamped prospective settled selections across ≥90 distinct Africa/Lagos kickoff dates; ≥98% timestamped odds coverage; net ROI >0 and date-clustered 95% lower bound >0; 1X2 Brier and log loss beat de-vigged bookmaker benchmark on identical fixtures/cutoffs. The 25 old non-PIT forecasts cannot count.
- Current PR #120 HEAD at the start of this audit: `f5f8b8068e5bd82e981a7782129a4b311280d891`, open/draft/unmerged. Exact-head CI: 12 successful checks, 4 expected skips, zero failures. Report surface bundle, publication verifier and certification-evidence tests are in the passing certification/foundation/acceptance suites; no publication/attestation workflow was dispatched because it is main-only and release remains disabled.
- No merge, deployment, publication, Telegram send, schedule activation, value-bet unlock or production write. Value betting remains LOCKED.

**Next:** independently confirm 5Dollar Ultra entitlement without upgrading; request written Odds-API.io Brazil Série B coverage and rights details before any paid trial; leave The Odds API historical endpoint untouched after its HTTP 401; keep all 25 prospective forecasts non-PIT until new V2 forecasts and eligible quote evidence exist; run the settlement collector only after target kickoffs and provider FINISHED status, using the existing staging-only append-only path.


### 5Dollar account entitlement evidence — 2026-11-15 23:31 WAT

- Read-only Neon query of `provider_entitlement_observations` returned one 5Dollar record: plan `community`, status `ACTIVE`, seven approved competition IDs, checked at `2026-11-12T22:51:54.745Z`, quota remaining 299. No Ultra entitlement observation exists. This supersedes the weaker wording "entitlement not evidenced": the last verified account plan is Community, not Ultra. Because the observation is dated 12 November, it is not a live plan check for 15 November; do not infer today's plan state or call the Ultra-only tick-history endpoint. No plan change, payment, API request or database write was made. Full decision is documented in `docs/VELTRIX_V2_CLOSING_ODDS_PROVIDER_COMPARATIVE_QUALIFICATION_2026-11-15.md` (latest update commit `21d444670038d156b7d2eaa219bea014de1df361`).
