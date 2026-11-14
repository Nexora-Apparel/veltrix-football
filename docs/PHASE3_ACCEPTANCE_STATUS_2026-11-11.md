# VELTRIX FOOTBALL — Phase 3 Acceptance Record

Date: 2026-11-11
Repository: Nexora-Apparel/veltrix-football
Qualification PR: #42 — Add bounded read-only StrikerAPI qualification
PR head at latest recorded changes: ac9579dd8663e0731e2d151c8ca34e5244bc245e

## 1. Provider terms and provenance

Operational terms review is recorded in PROVIDER_TERMS_AND_DATA_PROVENANCE_2026-11-11.md and STRIKERAPI_DATA_GOVERNANCE.md.

Limited sources:
- 5Dollar Free: EPL fixture/results only, last-three-month window, 60 requests/hour and 20/minute burst ceiling. Required public attribution: Football data by 5DollarFootballAPI, linked to https://5dollarfootballapi.com.
- StrikerAPI Free: fixture/results for EPL, Argentina and Brazil within observed endpoint/account coverage. Free allowance 500 credits/month; list_games costs 2 credits.
- NWSL remains provisional pending provider explanation of the public page's 224 count versus 240 league-stage API rows (16 fewer than the official regular-season fixture count; 20 fewer than the API's 244 total finals including four knockout fixtures).
- No odds, xG, shot maps, box scores or lineups are approved as production prediction features by this fixture/results qualification.
- Raw provider feed redistribution is prohibited.

This is an operational interpretation of current published provider terms, not legal advice or a signed league data licence.

## 2. NWSL discrepancy

Evidence:
- StrikerAPI API: 240 league-stage finals + 4 completed knockout finals = 244 final rows.
- StrikerAPI public NWSL page: 224 matches for 2026.
- Official 2026 NWSL rules: 16 teams × 30 regular-season games each = 240 regular-season fixtures.
- Official 2026 schedule footprint: 248 matches inclusive of playoffs and Challenge Cup.

Interpretation:
- The API's 240 league-stage count agrees with the official regular-season format.
- The four additional API rows are knockout-stage games.
- The public page count is 16 below the official regular-season format; arithmetic identifies the gap but does not establish why the public page undercounts.
- No written StrikerAPI support response has been obtained. NWSL is provisional, not fully approved.

References:
- https://strikerapi.com/nwsl
- https://strikerapi.com/docs/list-games
- https://www.nwslsoccer.com/news/nwsl-announces-2026-schedule-footprint
- https://images.nwslsoccer.com/image/private/t_q-good/prd/tstudhfledlk7z8ygtzd.pdf

## 3. Neon production database acceptance — read-only recheck

Target:
- Neon project VELTRIXFOOTBALL (withered-sky-75161174)
- Default branch main (br-soft-field-bc6zxixp)
- Database veltrix-football (not the separate neondb auth database)
- PostgreSQL 18.6

Live read-only SQL checks executed 2026-11-11:
- 11 public tables
- 11 primary keys
- 7 foreign keys
- 5 unique constraints
- 20 check constraints
- 22 indexes
- 1 applied migration (0001_persistent_foundation)
- 1 prior reconciliation audit with status PASS
- 0 fixtures, teams, competitions, results, source observations, import runs or import checkpoints
- Aggregate acceptance predicate: PASS

Existing audit ID 1 records manifest checksum match=true, expected/applied migrations=1/1, expected indexes present=true, rollback probe=passed, imported records=0; checked 2026-11-08T17:19:59.558Z.

No INSERT, UPDATE, DELETE, DDL, import or migration was executed during the 2026-11-11 recheck. Existing database records were preserved.

### Python acceptance script status

Added scripts/neon_acceptance.py and .github/workflows/neon-readonly-acceptance.yml. The runner checks the six recorded catalog counts inside a read-only transaction and emits a sanitized JSON result. It has not been executed: the available GitHub integration does not expose workflow_dispatch, and the DATABASE_URL secret cannot be read from this context. The direct SQL recheck is not a substitute for the Python execution result.

## 4. Historical import qualification

Completed evidence:
- 90-day StrikerAPI ↔ 5Dollar EPL read-only reconciliation: 100/100 unique matches.
- Zero unmatched, ambiguous, quarantined, duplicate or conflicting rows.
- All kickoff deltas zero seconds; all statuses and scores agreed.
- Provider source accounting balanced 100 rows on each side.
- Zero production database writes, imports, checkpoints or canonical merges.
- StrikerAPI bounded four-competition probe used 29 calls / 58 credits under the 48-call / 96-credit ceiling.

Not yet qualified:
- A database-targeted provider dry-run script and manual workflow have been added. No execution artifact exists yet.
- No full historical export beyond bounded windows/page caps has been validated.
- 5Dollar Free supplies only the last three months of results and the five top European competitions.
- StrikerAPI's full advertised historical coverage has not been exhaustively fetched/reconciled by competition, season and endpoint.
- Source payload provenance must be persisted as observations without overwriting earlier versions.
- Import pipeline must be run in dry-run mode against a disposable Neon branch or isolated test target, with production writes disabled.

Exact import scope currently safe to test:
- EPL, previous 90 days, StrikerAPI plus 5Dollar.
- Argentina and Brazil, previous 90 days, StrikerAPI only.
- NWSL excluded from supported launch/import scope; provider count clarification remains open in issue #49.
- Do not expand the import window or competition set until page counts, source accounting, identity matching, duplicate handling, result/score validation and rate budgets pass.

## 5. PR and CI state

- PR #42 remains open and draft; do not merge on the basis of this record.
- Exact-head unit workflow run #42781003277 succeeded on head 58f4779f4f4a30c51ac40410ee9cb0c1e4e5ab60.
- Job unit-tests passed all configured reconciliation/provider verifier tests.
- Latest EPL live reconciliation evidence: workflow run #42680798028, artifact #13701808156.
- NWSL catalogue verification and crosswalk evidence remain scoped; no wider 17-competition pass is claimed.

## 6. Phase 3 decision

LIMITED SOURCE QUALIFICATION PASSED; FULL PHASE 3 SIGN-OFF NOT GRANTED.

Allowed for the next import dry-run only:
- StrikerAPI EPL fixture/results
- 5Dollar EPL fixture/results
- StrikerAPI Argentina fixture/results
- StrikerAPI Brazil fixture/results

NWSL is excluded from the supported launch scope. Its page/API discrepancy remains unresolved and must not be used as a production source. Other StrikerAPI competitions and all non-fixture datasets remain unsupported pending separate qualification.

Full Phase 3 remains blocked by:
1. Execute the newly added read-only Python Neon acceptance runner against the target database and retain its workflow artifact. The script and manual workflow now exist; execution is still pending.
2. Execute the newly added provider-backed dry-run against the isolated Neon branch; the workflow and validator now exist, but no provider run artifact has been produced.
3. NWSL remains formally excluded from the supported launch scope unless a written provider explanation and fresh qualification are obtained; this is no longer a blocker for the limited launch if exclusion is maintained.

Independent v2 contract/foundation implementation may proceed on its isolated architecture branch. Model fitting, calibration, evaluation claims, publication and prediction activation remain gated until full Phase 3 sign-off. No legacy prediction model, feature pipeline, calibration or fallback logic may be reused.


## 7. New execution artifacts — 2026-11-11 follow-up

- Added `scripts/neon_acceptance.py` and `.github/workflows/neon-readonly-acceptance.yml`. Python runner remains unexecuted pending manual workflow dispatch and the repository DATABASE_URL secret.
- Added `scripts/provider_import_dry_run.py` and `.github/workflows/provider-import-dry-run.yml`. It fetches StrikerAPI fixture/results for EPL, Argentina and Brazil over 90 days and 5Dollar EPL for the same period. It validates unique provider IDs, home/away team IDs and names, timezone-aware kickoffs, final scores, pagination, payload SHA-256 and rights approval IDs; performs full EPL cross-provider identity/status/score reconciliation; checks existing isolated database records for provider-ID, competition identity, kickoff, team identity, status, missing-result and score conflicts; and asserts before/after row counts are unchanged. It contains no INSERT/UPDATE/DELETE or DDL.
- Created isolated Neon branch `veltrix-phase3-import-dry-run` (`br-silent-violet-bc5de88s`) from production main and provisioned a 0.25 CU read-write compute endpoint on that child branch only. Production main was not modified.
- Workflow dispatch and secrets remain external execution blockers. No provider API calls or dry-run writes have been made in this follow-up.
- NWSL issue #49 still has no vendor response. No written explanation has been received, so NWSL remains excluded.


## 8. Unit-test and production-write verification — 2026-11-11

- Provider dry-run validation tests: 5 passed, 0 failed on latest validation commit `5980b58e1b9f0d4d53b3dbcaa056599ee91b1582`, run [42978553967](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42978553967).
- StrikerAPI reconciliation unit suite: passed on the same head.
- The live provider-backed dry-run did not begin because `DRY_RUN_DATABASE_URL` is absent. The live Python Neon acceptance did not begin because `DATABASE_URL` is absent. These are failed secret-preflight runs, not failed Python assertions.
- Production `main` read-only snapshot: 0 fixtures, teams, competitions, results, source observations, import runs and import checkpoints. Neon branch metadata reports `written_data_bytes=0`.
- Isolated child branch read-only snapshot: same seven domain counts all zero; branch metadata reports `written_data_bytes=0`. The 0.25 CU compute endpoint exists only on this child branch.
- No INSERT, UPDATE, DELETE, DDL, import or migration was executed on production or the child branch.
- Manual-only workflow dispatch was restored after the initial push-triggered preflight runs. The two verification workflows will not run automatically on future branch commits.

### Exact secret requirements

- `DATABASE_URL`: read-only credential for the production database, used only by `scripts/neon_acceptance.py`.
- `DRY_RUN_DATABASE_URL`: credential for Neon child branch `br-silent-violet-bc5de88s` only, used by the provider-backed dry-run.
- `STRIKERAPI_API_KEY` and `FIVEDOLLARFOOTBALL_API_KEY` are wired into the provider workflow; StrikerAPI secret was present in the preflight run. Do not paste any secret into chat or source code.

Full Phase 3 sign-off remains withheld until both Python workflows execute and pass, the dry-run artifact demonstrates balanced cross-provider EPL source accounting and no conflicts, and NWSL is either formally excluded from the release scope or clarified by the provider. No prediction-model fitting or publication is authorized yet.


## 9. Follow-up execution — 2026-11-11 (continued)

- Live catalog recheck on both production `main` and isolated child branch returned 11 public tables, 11 primary keys, 7 foreign keys, 5 unique constraints, 83 check constraints and 22 indexes. The Python runner's expected CHECK count was corrected from 20 to 83 on the qualification branch.
- Both databases still have zero fixtures, teams, competitions, fixture results, source observations, import runs and import checkpoints.
- The isolated Neon endpoint was provisioned at 0.25 CU, then suspended after the read-only checks. No import execution occurred; branch metadata continued to report zero written data bytes and zero compute seconds.
- The provider dry-run now rejects every database hostname except the exact dedicated isolated Neon endpoint (and its pooler hostname). This prevents a misconfigured DRY_RUN_DATABASE_URL from silently targeting production. A corresponding unit test was added.
- The actual Python GitHub Actions acceptance workflow has **not** executed. The available GitHub integration cannot dispatch workflow_dispatch runs or create repository secrets. Earlier preflight evidence recorded DATABASE_URL and DRY_RUN_DATABASE_URL as missing. The SQL catalog recheck is not represented as a Python workflow pass.
- The actual provider-backed import dry-run has **not** executed. Its workflow requires STRIKERAPI_API_KEY, FIVEDOLLARFOOTBALL_API_KEY and DRY_RUN_DATABASE_URL; the latter must point to the dedicated isolated endpoint. No provider API calls or import writes were made during this continuation.
- NWSL is formally excluded from the supported launch/import scope. The 224-versus-240 discrepancy is still unexplained by StrikerAPI; official league format explains why 240 regular-season fixtures are expected, but not why the provider's public page lists 224. Issue #49 remains open for a written explanation. No NWSL source data is approved.
- Exact approved fixture/results coverage for the limited launch/dry-run remains: StrikerAPI EPL, Argentina and Brazil within the bounded qualification windows; 5Dollar EPL within the Free-plan three-month results window. All odds, xG, shot data, lineups, events and player statistics remain unapproved by Phase 3 fixture/results qualification.
- Phase 3 sign-off remains withheld until both manual Python workflows execute successfully and the provider dry-run artifact demonstrates complete source accounting, zero conflicts and unchanged isolated/production database counts.


## 10. Provider dry-run guard CI — 2026-11-11

- The latest pull-request CI run for the provider import dry-run tests completed successfully: run [#42979471873](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42979471873), commit `55a3fa356c01165b52322fb952b6556fa03c4dce`.
- GitHub Actions log confirms **7 passed, 0 failed** in `tests/test_provider_import_dry_run.py`, including the isolated Neon hostname allowlist and production/unknown-host rejection.
- This is the offline validation suite only. It does not mean the provider-backed import workflow or Neon Python acceptance workflow executed.


## 11. Production acceptance runner hardening — 2026-11-11

- The Neon Python runner now allows only the verified production endpoint hostname (including its pooler) and rejects any other target before connecting.
- It checks the 11-table schema baseline, 11 primary keys, 7 foreign keys, 5 unique constraints, 83 CHECK constraints, 22 indexes, one applied migration and one PASS reconciliation audit.
- Every query runs inside an explicit PostgreSQL READ ONLY transaction; credentials and exception text are not printed.
- This hardening does not change the actual execution status: the workflow has not yet reached the Python runner because the DATABASE_URL repository secret was missing in the previous preflight. No Python acceptance pass is claimed.



## 12. Secret-backed workflow execution — 2026-11-11 (continued)

- The repository secrets are now present and are consumed by GitHub Actions. This is confirmed by masked non-empty environment values in both workflow logs.
- Neon Python acceptance run [#42983237444](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42983237444) reached the Python runner in a PostgreSQL read-only transaction but failed the target validation: the configured connection resolves to a database other than `veltrix-football`. No writes occurred.
- Provider-backed dry-run [#42983219130](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42983219130) passed secret preflight and the isolated-host allowlist, then rejected the database name before any provider API calls. No import writes occurred.
- The provider dry-run's direct-execution import-path defect was corrected by adding the repository root to `sys.path`. The latest provider dry-run unit suite passed on commit `67cf638cc819679d72e02eff551ab13648509913`: run [#42983244812](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42983244812).
- The Neon runner now explicitly rejects a connection whose current database is not `veltrix-football`; it does not silently query another database.
- Both GitHub Actions workflows now support manual dispatch and narrowly scoped pushes to the qualification branch for their relevant validator/workflow changes.
- Required manual correction: update both GitHub secret values so their Neon connection strings select database `veltrix-football` (not `neondb`). `DATABASE_URL` must target production branch `main`; `DRY_RUN_DATABASE_URL` must target isolated branch `veltrix-phase3-import-dry-run`. Keep the verified hostnames unchanged.
- Phase 3 remains unsigned. No provider import, production write, migration or model activation occurred.


## 13. Corrected-secret rerun — 2026-11-11

- Neon read-only acceptance rerun attempt 2: **PASS** — [workflow run #42983237444](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42983237444).
  - Connected to the verified production Neon endpoint and database `veltrix-football`.
  - Python runner completed successfully in a PostgreSQL READ ONLY transaction; `transaction_read_only=true`.
  - All eight acceptance checks passed: 11 public tables, 11 PKs, 7 FKs, 5 unique constraints, 83 CHECK constraints, 22 indexes, one applied migration and one PASS reconciliation audit.
  - No production writes occurred.
- Provider-backed import dry-run rerun attempt 2: **FAIL — provider HTTP 402** — [workflow run #42983219130](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42983219130).
  - Correct isolated Neon endpoint/database validation passed.
  - Both provider API credentials and isolated database secret were present (masked by GitHub).
  - The script reached its first StrikerAPI fixture request and received HTTP 402. No successful provider fixture response was received; the dry-run report was not produced.
  - The workflow failed before database import/write logic. No provider-backed import or database write occurred.
  - Treat HTTP 402 as a provider account/credit/billing entitlement blocker until StrikerAPI confirms the exact cause. Do not repeatedly retry or spend further credits until account balance/plan status is checked.
- Phase 3 is still not fully signed off. Neon schema acceptance is now complete; provider-backed source accounting and isolated dry-run validation remain outstanding.
