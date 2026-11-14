# StrikerAPI 17-Competition Coverage Qualification

Status: BLOCKED — live qualification returned HTTP 402 (insufficient provider credits) on 2026-11-09. No complete 17-competition report was produced. No data import is authorized.

## Provider scope

The official StrikerAPI catalogue documents these 17 competition keys:

| Key | Competition |
|---|---|
| `soccer` | English Premier League |
| `mls` | Major League Soccer |
| `laliga` | Spanish La Liga |
| `seriea` | Italian Serie A |
| `bundesliga` | German Bundesliga |
| `ligue1` | French Ligue 1 |
| `ucl` | UEFA Champions League |
| `championship` | EFL Championship |
| `nwsl` | NWSL |
| `ligamx` | Mexican Liga MX |
| `uel` | UEFA Europa League |
| `uecl` | UEFA Conference League |
| `eredivisie` | Dutch Eredivisie |
| `primeira` | Portuguese Primeira Liga |
| `scotland` | Scottish Premiership |
| `brazil` | Brazil Serie A |
| `argentina` | Argentina Liga Profesional |

Official endpoint reference: https://strikerapi.com/docs/list-games

## Qualification design

`scripts/verify_strikerapi_17_competitions.py` runs a read-only, bounded sample:

- Final results: rolling 90-day window.
- Scheduled fixtures: rolling 60-day window.
- 50 rows per page.
- Maximum three pages per competition/status check.
- 34 checks total.
- Hard ceiling: 102 API calls / 204 documented credits.
- Empty schedules are reported, not fabricated.
- Pagination truncation, duplicate IDs, invalid fixture identities or malformed scores prevent acceptance.
- No Neon connection, imports, checkpoints, canonical merges or production writes.

The free account's documented allowance is 500 credits/month. The API rate limit is 60 requests/minute at balances of 100 credits or more and 10 requests/minute below 100 credits. The verifier therefore spaces requests by seven seconds and has a bounded 65-second HTTP 429 cooldown retry. A 429 is a rate-limit condition, not proof of invalid credentials. Official rate limits: https://strikerapi.com/docs

## Live qualification attempts — 2026-11-09

Two live Actions attempts were inspected:

- Run `42681364817` (commit `3c2621e48dd9139d7aebe0cd8a0bb0966024b51f`): local verifier tests passed (6); live probe stopped with HTTP 402.
- Run `42681395011` (commit `127af00eaa344dac38771e1d14be01ddac95325f`): local verifier tests passed (8); live probe stopped with HTTP 402.

Both attempts ended before the 34 checks completed. Neither generated a coverage JSON report or uploaded an artifact. Consequently, no 17-competition live coverage conclusion can be drawn. HTTP 402 is treated as a credit/billing constraint, not an authentication failure. Do not repeat the live probe until the provider account's available credit balance and reset date are checked. The verifier's theoretical 204-credit ceiling is not a recommendation to spend the entire free allowance in one run.

The workflow is manual-dispatch only. Pushes to the qualification branch must not automatically consume provider credits; secret-free unit tests are handled by the separate CI workflow.

## Dataset limitations that affect modelling

The 17-competition catalogue does not mean every data product is equally complete:

- Fixtures and results: available for every match listed.
- Lineups and box scores: partial by competition and season.
- Match events: partial historically; shot/foul/corner/offside events are available from 2012-13 in the documented coverage.
- Shot locations and provider-modelled xG: competition-specific start dates; full coverage generally from 2013-14 in the main European competitions, but later or partial in several newer competitions.
- Odds: partial. Daily feed has one or two books per match since 2024-25; the deeper archive covers 16 competitions from June 2020 and excludes NWSL.
- Player props: only seven competitions.
- Elo ratings: available across all 17 competitions.

Source: https://strikerapi.com/docs/atlas

## Point-in-time and rights constraints

- Provider xG is a model fitted using later seasons and can be retrospectively refitted. It is not automatically leakage-safe for historical backtests. VELTRIX should preserve shot locations and fit its own point-in-time model for strict out-of-sample evaluation.
- Provider records are overwritten when corrected; there is no per-record revision history. Store retrieval timestamps, endpoint, source ID and payload hash.
- Odds are pre-match only. Do not label them live or in-play.
- The terms allow storing data while the account remains open, building derived values and using them in research/backtesting/training and commercial apps. Raw/bulk feed redistribution and resale are prohibited. Continued product use of the data requires an active account.
- StrikerAPI does not grant league marks or official league rights.

Source: https://strikerapi.com/docs/timing-and-rights

## Acceptance boundary

A successful rolling-window probe proves only that the provider returned valid, paginated records for the measured windows. It does not certify:

- complete season coverage;
- 25 suitable daily fixtures on every date;
- complete xG, lineup or odds coverage;
- 98% timestamped odds coverage;
- model accuracy or value-betting profitability;
- permission to import into production.

Phase 3 remains open until the live report is inspected, data rights are reviewed for the intended product, and the production import contract is separately authorized.
