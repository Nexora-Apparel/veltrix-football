# StrikerAPI Read-Only Qualification

Status: implementation prepared; provider credential and live qualification pending.

## Why this provider

StrikerAPI's published catalogue includes Argentina Liga Profesional, Brazil Série A and NWSL. It explicitly states that it has no live in-match feed and refreshes most non-odds data daily. This matches VELTRIX FOOTBALL's requirement for scheduled fixtures, settled results and historical analysis rather than live-game coverage.

Official references:
- https://strikerapi.com/docs
- https://strikerapi.com/docs/list-games
- https://strikerapi.com/docs/atlas
- https://strikerapi.com/docs/timing-and-rights
- https://strikerapi.com/pricing

## Free-tier cost control

The published free allowance is 500 credits/month. `list_games` costs 2 credits per call. The qualification workflow makes at most seven calls (14 credits):
- Argentina: final and scheduled samples.
- Brazil: final and scheduled samples.
- NWSL: final and scheduled samples.
- Generic soccer/EPL overlap: one final sample for manual reconciliation against the verified 5Dollar source.

No events, odds, shot-map or lineups endpoints are called in this first probe. Those cost more credits and are deferred until basic coverage passes.

## Credential

Create a free provider key and add it to GitHub Actions repository secrets under exactly:
`STRIKERAPI_API_KEY`

Never paste the key into chat, source code, workflow YAML or logs. The workflow is manual-dispatch only; no schedule, push or pull-request trigger is configured.

## Qualification boundaries

The probe checks response shape, match IDs, dates/timestamps, status, home/away team IDs and names, and final scores. It makes no database connection and performs no imports.

A passing sample does not certify:
- complete season/history pagination;
- account-level entitlement to every listed competition;
- completeness of lineups, team/player statistics, shot locations or xG;
- timestamp/odds coverage for value betting;
- legal permission to redistribute raw provider data.

Those require separate documented gates. Provider-computed xG must remain labelled as provider-modelled xG, not independently observed xG.

## Acceptance sequence

1. Run the manual workflow once the secret is present.
2. Inspect exact returned sample counts and schema.
3. Verify full season pagination and historical depth for Argentina and Brazil.
4. Inspect NWSL season completeness and its known partial-data periods.
5. Reconcile overlapping fixtures against 5DollarFootballAPI using provider IDs and deterministic identity rules; never merge by names, score or kickoff alone.
6. Review data timing, storage, commercial-use and redistribution terms.
7. Only then consider adding StrikerAPI as an approved competition-specific source.

No production imports, migrations, deployments, paid upgrades or prediction-delivery changes are part of this qualification.
