# StrikerAPI Read-Only Qualification

Status: bounded 90-day history / 180-day schedule probe passed on 2026-11-09; NWSL scheduled coverage, cross-provider reconciliation and contractual terms review remain open.

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
- NWSL API therefore returned 244 final fixtures for 2026 and no 2027 scheduled fixtures at probe time. The provider's public NWSL page lists 224 matches for 2026, so the 20-match discrepancy is an explicit provider-data reconciliation issue; do not silently treat either count as authoritative until clarified.
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

1. Investigate the zero-row NWSL scheduled response using provider season, stage and schedule documentation; do not infer coverage from the empty response.
2. Implement and run deterministic read-only comparisons for the verified Premier League overlap only. The 5Dollar Free-tier catalogue contains no Argentina or Brazil competition, so those StrikerAPI competitions cannot be cross-reconciled against the current 5Dollar account.
3. Record all unmatched, ambiguous and conflicting source rows without merging or rewriting provider identities.
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

These checks distinguish historical season coverage from publication of the next calendar-year schedule. They are separately accounted and do not inflate the original rolling-window row totals. The overall hard limit remains 48 calls / 96 documented credits; run #4 used 21 calls, and the four new diagnostic requests are expected to bring a fully paginated execution to 25 calls / 50 credits. The result must be read from the next workflow log; this documentation alone is not evidence that the diagnostic has run.
