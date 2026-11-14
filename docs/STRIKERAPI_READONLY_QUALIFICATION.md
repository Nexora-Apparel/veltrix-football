# StrikerAPI Read-Only Qualification

Status: bounded 90-day history / 180-day schedule probe passed on 2026-11-09; NWSL public-page/API count discrepancy remains unresolved pending written vendor clarification; the bounded EPL reconciliation and contractual terms review are recorded.

## Why this provider

StrikerAPI publishes scheduled fixtures, settled results and historical match data for competitions relevant to VELTRIX FOOTBALL. Its REST API is suitable for this project without requiring a live in-match feed.

Official references:
- https://strikerapi.com/docs
- https://strikerapi.com/docs/list-games
- https://strikerapi.com/docs/atlas
- https://strikerapi.com/docs/timing-and-rights
- https://strikerapi.com/pricing

## Explicit competition mapping

The official `list_games` documentation identifies these keys:
- `soccer`: English Premier League (the Premier League default/key)
- `nwsl`: National Women's Soccer League
- `brazil`: Brazil Serie A
- `argentina`: Argentina Liga Profesional

The verifier labels `soccer` as English Premier League; it is not an unidentified generic sample. League keys must remain explicit in provider provenance.

## Bounded read-only probe

The verifier checks:
- final results over the preceding 90 days;
- scheduled fixtures over the next 180 days;
- Argentina, Brazil, NWSL and the English Premier League;
- response schema, stable game IDs, dates/timestamps, status, team IDs/names and final scores;
- pagination via `next_offset`, with no more than six pages per competition/status check;
- timezone-aware kickoff timestamps;
- duplicate IDs within each competition across returned pages.

### Run #4 — expanded qualification evidence (attempt 3)

- Workflow: [Verify StrikerAPI Read-Only Coverage #4](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42639816228)
- Run ID: `42639816228`; attempt: `3`; job ID: `129247142796`
- Workflow commit on `main`: `5f882a356df9c213195f50333a8a58f2faffa6a7`
- Qualification code checked out from `phase-3/strikerapi-readonly-qualification`, head `eccbabf21e8405f75fa4c562b3aa7569c71d00ef`
- Result: success; **17/17 unit tests passed**.
- Rolling query windows: final results `2026-08-11..2026-11-09`; scheduled fixtures `2026-11-09..2027-05-08`.
- Rolling-window rows: 802 total, all valid, zero duplicate IDs, zero truncated checks.
- Argentina Liga Profesional: 182 final, 8 scheduled.
- Brazil Serie A: 124 final, 41 scheduled.
- NWSL: 97 final, 0 scheduled in the rolling window.
- English Premier League: 100 final, 250 scheduled.
- Explicit NWSL season/stage diagnostics:
  - 2026 league-stage finals: 240 valid rows, 5 pages.
  - 2026 knockout-stage finals: 4 valid rows, 1 page.
  - 2027 league-stage scheduled: 0 rows.
  - 2027 knockout-stage scheduled: 0 rows.
  - All four scoped checks completed without invalid rows or pagination truncation.
- NWSL API therefore returned 244 final fixtures for 2026 and no 2027 scheduled fixtures at probe time. The provider's public NWSL page lists 224 matches for 2026: 16 fewer than the official 240 regular-season fixture count and 20 fewer than the API's 244 total final rows including four knockout fixtures. Do not silently treat the public-page count as authoritative until clarified.
- API use: 29 calls / 58 documented credits, below the 48-call / 96-credit hard cap.
- Database writes, imported records, import runs and checkpoints: all zero.
- Verifier result: `BOUNDED_COVERAGE_PASS_PENDING_MANUAL_RECONCILIATION_AND_TERMS_REVIEW`.

This is a bounded coverage pass, not a full-season export or production approval. NWSL's zero scheduled rows are explained by the API returning completed 2026 games but no 2027 scheduled fixtures in the explicit stage queries. This does not establish when the provider will publish the next season's schedule.

### Pagination documentation discrepancy

The endpoint-specific `list_games` page documents an `offset` parameter and returns `next_offset`. The general StrikerAPI documentation's conventions section says endpoints use `limit` and have no cursor or offset. Run #4 exercised multi-page requests and completed all eight bounded checks without truncation, establishing that the verifier's observed offset pagination works for these tested queries. The discrepancy in the provider's general documentation remains worth clarifying with the provider before relying on it as a long-term contract.

The hard budget is 48 calls maximum × 2 documented credits = 96 credits. Run #4 attempt 3 used 29 calls / 58 credits, including pagination for the four explicit NWSL season/stage checks. If a page cap is reached while `next_offset` remains, the result is explicitly marked pagination-incomplete; it is never reported as a complete window.

The workflow runs local unit tests for pagination, non-advancing offsets, scheduled fixtures, final-score validation and timezone-aware kickoff timestamps before making provider calls.

## Free-tier cost control

The provider documents 500 free credits/month and 2 credits per `list_games` call. The verifier is capped at 96 documented credits per run (48 calls). No event, odds, shot-map or lineup endpoints are called in this qualification step.

## Credential

GitHub Actions repository secret:
`STRIKERAPI_API_KEY`

Never paste the key into chat, source code, workflow YAML or logs. The workflow is manual-dispatch only; no schedule, push or pull-request trigger is configured.

## Qualification boundaries

A passing bounded probe does not certify:
- full-season or complete historical pagination beyond the selected windows/page cap;
- full historical depth for each competition;
- account-level entitlement to every listed competition;
- completeness of lineups, team/player statistics, shot locations or xG;
- timestamp/odds coverage for value betting;
- legal permission to store, use commercially or redistribute raw provider data.

The atlas describes different coverage periods by league and dataset. Provider-computed xG must be labelled provider-modelled xG, not independently observed xG. Odds coverage is partial and must not be presumed adequate for value-bet certification.

## Acceptance sequence

1. Clarify the 20-match discrepancy between the NWSL API's 244 2026 final rows and the provider's public page's 224-match season count.
2. Run the live, read-only Premier League reconciliation using the verified 5Dollar overlap only. The Free-tier catalogue contains no Argentina or Brazil competition, so those StrikerAPI competitions cannot be cross-reconciled against the current 5Dollar account.
3. Review every unmatched, ambiguous and conflicting source row without merging or rewriting provider identities.
4. Review the provider's current timing, storage, commercial-use and redistribution terms and retain a dated copy.
5. Approve only competition- and data-type-specific source authority after all evidence passes.

No production imports, migrations, deployments, paid upgrades or prediction-delivery changes are part of this qualification.


## NWSL zero-scheduled follow-up

The provider documents NWSL seasons as calendar years and exposes both `season` and `stage=league|knockout` filters. The verifier now checks 2026 final games split by stage and 2027 scheduled fixtures split by stage. This distinguishes completed 2026 season coverage from whether the next calendar-year schedule has been published. Each request costs two credits.

Reference: https://strikerapi.com/nwsl and https://strikerapi.com/docs/list-games.


## Explicit NWSL season/stage diagnostics

The verifier now follows the documented `season` and `stage` filters to investigate the zero-row rolling schedule response. The API documentation defines NWSL seasons by calendar year and supports `stage=league|knockout`; each request costs two credits. See the [official list_games reference](https://strikerapi.com/docs/list-games).

The diagnostic performs four read-only checks:
- NWSL season 2026, `status=final`, `stage=league`;
- NWSL season 2026, `status=final`, `stage=knockout`;
- NWSL season 2027, `status=scheduled`, `stage=league`;
- NWSL season 2027, `status=scheduled`, `stage=knockout`.

These checks distinguish historical season coverage from publication of the next calendar-year schedule. They are separately accounted and do not inflate the original rolling-window row totals. Run #4 attempt 3 completed all four scoped checks using eight paginated calls, for 29 calls / 58 documented credits overall. The API returned 244 final NWSL fixtures for 2026 (240 league and 4 knockout) and no 2027 scheduled fixtures. The provider's public NWSL page lists 224 matches for 2026; that 20-match discrepancy remains unresolved.


## Continuous integration for offline reconciliation

A separate pull-request workflow, `.github/workflows/strikerapi-reconciliation-tests.yml`, runs the complete `test_strikerapi*.py` suite on PR changes to the reconciliation implementation/tests. It has no provider credential and makes no API calls. This keeps deterministic unit testing independent of the manual, credit-bounded provider qualification workflow.

## NWSL 2026 public-page count reconciliation — 2026-11-11

Additional official evidence was checked after the original 2026-11-09 probe:
- StrikerAPI API returned 240 2026 league-stage finals and 4 completed knockout-stage finals (244 total).
- StrikerAPI's public NWSL page lists 224 matches for 2026.
- The official NWSL 2026 competition rules specify 16 teams, each playing 30 regular-season games: 16 × 30 ÷ 2 = 240 regular-season fixtures.
- The official NWSL 2026 schedule footprint describes 248 matches including an eight-team playoff and the Challenge Cup.

Interpretation: the API's 240 league-stage count is consistent with the official regular-season format; its four additional rows are knockout fixtures. The public page is 16 below the official regular-season fixture count. This narrows the discrepancy but does not establish why the public page undercounts; it may reflect a page count/data coverage issue, but that has not been confirmed by StrikerAPI.

No written provider support response has been obtained. Keep NWSL fixture/results provisional until StrikerAPI explains the public-page count and confirms the 240 league-stage records. Do not use this arithmetic as proof of complete NWSL match data or authorize NWSL odds, xG, shot data or player statistics.

Official references:
- https://strikerapi.com/nwsl
- https://strikerapi.com/docs/list-games
- https://www.nwslsoccer.com/news/nwsl-announces-2026-schedule-footprint
- https://images.nwslsoccer.com/image/private/t_q-good/prd/tstudhfledlk7z8ygtzd.pdf

## 2026-11-11 follow-up — NWSL discrepancy decision

The public documentation was rechecked on 2026-11-11. The endpoint docs explicitly support separate `stage=league` and `stage=knockout` queries. The existing bounded API evidence remains 240 league-stage finals plus four knockout finals (244 total). The public NWSL page still reports 224 for 2026. Official NWSL rules specify 16 clubs playing 30 regular-season matches each, yielding 240 fixtures; the official 2026 schedule footprint includes 248 matches across regular season, playoffs and Challenge Cup.

This resolves the arithmetic and categorization, not the provider's data discrepancy. The page's 224 count is 16 below regular season and 20 below the API's all-stage total. No provider support response is recorded in issue #49. NWSL therefore remains **not approved for import or production model use**. The exact approved fixture/results scope remains StrikerAPI EPL, Argentina and Brazil within the bounded 90-day probe, plus 5Dollar EPL within its Free-plan three-month entitlement. No odds, xG, shots, lineups, events or other stats are approved by this fixture/results qualification.
