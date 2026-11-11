# VELTRIX FOOTBALL — Phase 3 Acceptance Record

Date: 2026-11-11
Repository: Nexora-Apparel/veltrix-football
Qualification PR: #42 — Add bounded read-only StrikerAPI qualification
PR head reviewed: 58f4779f4f4a30c51ac40410ee9cb0c1e4e5ab60

## 1. Provider terms and provenance

Operational terms review is recorded in PROVIDER_TERMS_AND_DATA_PROVENANCE_2026-11-11.md and STRIKERAPI_DATA_GOVERNANCE.md.

Limited sources:
- 5Dollar Free: EPL fixture/results only, last-three-month window, 60 requests/hour and 20/minute burst ceiling. Required public attribution: Football data by 5DollarFootballAPI, linked to https://5dollarfootballapi.com.
- StrikerAPI Free: fixture/results for EPL, Argentina and Brazil within observed endpoint/account coverage. Free allowance 500 credits/month; list_games costs 2 credits.
- NWSL remains provisional pending provider explanation of the public page's 224 count versus 240 league-stage API rows.
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

The repository tree and prior project history contain no exact Python acceptance script filename, path or execution command. Prior acceptance was performed through direct production SQL equivalent to repository assertions; the Python script itself was never run. This recheck repeats the SQL acceptance predicate and passes, but it must not be misreported as execution of a Python script. A reproducible Python runner using a securely supplied Neon connection string still needs to be added and executed.

## 4. Historical import qualification

Completed evidence:
- 90-day StrikerAPI ↔ 5Dollar EPL read-only reconciliation: 100/100 unique matches.
- Zero unmatched, ambiguous, quarantined, duplicate or conflicting rows.
- All kickoff deltas zero seconds; all statuses and scores agreed.
- Provider source accounting balanced 100 rows on each side.
- Zero production database writes, imports, checkpoints or canonical merges.
- StrikerAPI bounded four-competition probe used 29 calls / 58 credits under the 48-call / 96-credit ceiling.

Not yet qualified:
- No database-targeted import dry-run artifact exists.
- No full historical export beyond bounded windows/page caps has been validated.
- 5Dollar Free supplies only the last three months of results and the five top European competitions.
- StrikerAPI's full advertised historical coverage has not been exhaustively fetched/reconciled by competition, season and endpoint.
- Source payload provenance must be persisted as observations without overwriting earlier versions.
- Import pipeline must be run in dry-run mode against a disposable Neon branch or isolated test target, with production writes disabled.

Exact import scope currently safe to test:
- EPL, previous 90 days, StrikerAPI plus 5Dollar.
- Argentina and Brazil, previous 90 days, StrikerAPI only.
- NWSL, previous 90 days, StrikerAPI only and provisional pending vendor clarification.
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

NWSL remains provisional. Other StrikerAPI competitions and all non-fixture datasets remain unsupported pending separate qualification.

Full Phase 3 remains blocked by:
1. A reproducible Python Neon acceptance runner and execution against the target database.
2. An import-pipeline dry-run with a provider-backed manifest and balanced source accounting, without production writes.
3. Written StrikerAPI clarification of the NWSL 2026 224-versus-240 league count.

Prediction architecture implementation and prediction activation remain gated until full Phase 3 sign-off. No legacy prediction model, feature pipeline, calibration or fallback logic may be reused.
