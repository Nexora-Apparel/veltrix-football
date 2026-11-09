# StrikerAPI Read-Only Qualification

Status: initial API sample passed; bounded pagination qualification implemented; full coverage and terms review pending.

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

The verifier now labels `soccer` as English Premier League; it is not an unidentified generic sample. League keys must remain explicit in provider provenance.

## Bounded read-only probe

The verifier checks:
- final results over the preceding 90 days;
- scheduled fixtures over the next 180 days;
- Argentina, Brazil, NWSL and the English Premier League;
- response schema, stable game IDs, dates/timestamps, status, team IDs/names and final scores;
- pagination via `next_offset`, with no more than three pages per competition/status check;
- timezone-aware kickoff timestamps;
- duplicate IDs within each competition across returned pages.

### Pagination documentation discrepancy

The endpoint-specific `list_games` page documents an `offset` parameter and returns `next_offset`. The general StrikerAPI documentation's conventions section says endpoints use `limit` and have no cursor or offset. The initial live sample returned `next_offset`, but did not test a second page. The expanded workflow will test the endpoint behavior directly. Until that run passes, multi-page pagination remains unverified.

Hard budget: 24 calls maximum × 2 documented credits = 48 credits. The probe makes no database connection and performs no imports. If a page cap is reached while `next_offset` remains, the result is explicitly marked pagination-incomplete; it is never reported as a complete window.

NWSL's previous scheduled query returned zero rows for a 30-day horizon. The revised 180-day horizon tests whether this was simply an offseason/window issue. A zero result remains a coverage question, not proof of provider failure or proof of no scheduled fixtures.

The workflow runs local unit tests for pagination, non-advancing offsets, scheduled fixtures and final-score validation before making provider calls.

## Free-tier cost control

The provider documents 500 free credits/month and 2 credits per `list_games` call. The verifier is capped at 48 documented credits per run. No event, odds, shot-map or lineup endpoints are called in this qualification step.

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

1. Run this manual workflow and inspect unit-test results, request count and page counts.
2. Resolve any truncated pagination windows with narrower date slices and a separately approved credit budget.
3. Investigate NWSL scheduled coverage using the 180-day horizon and provider season/fixture documentation.
4. Compare explicit Premier League, Argentina and Brazil fixture samples against 5DollarFootballAPI.
5. Reconcile only with deterministic provider identity evidence; preserve both source observations and quarantine ambiguous/conflicting matches.
6. Review the provider's timing, storage, commercial-use and redistribution terms.
7. Approve only competition- and data-type-specific source authority after the evidence passes.

No production imports, migrations, deployments, paid upgrades or prediction-delivery changes are part of this qualification.
