# Free Football Data Source Coverage Assessment

Assessment date: 2026-11-08
Status: research complete; candidate credentials and live access still unverified.

## Objective

Close the verified 5DollarFootballAPI Free-plan coverage gap without purchasing a subscription, importing unverified data, or changing the prediction-delivery pause.

The target remains broad: upcoming fixtures and settled results across the competitions Veltrix intends to analyse, including Argentina, Brazil, and women's football. A provider's public coverage catalogue is not proof that its free tier exposes that competition. Every source must pass an authenticated, read-only endpoint test before it is approved.

## Source matrix

| Source | Publicly documented free coverage | Useful data | Limitations / decision |
|---|---|---|---|
| 5DollarFootballAPI (existing) | Verified account exposes five competitions: England Premier League, France Ligue 1, Germany Bundesliga I, Italy Serie A, Spain La Liga | Fixtures and finished results; current account tested | Primary for its verified five competitions only. Free plan and three-month history confirmed in the 2026-11-08 provider run. |
| football-data.org | Free tier explicitly lists 12 competitions, including Brazil Série A, England/European major competitions | Fixtures, results, standings; current season and selected historical seasons via API | Candidate for Brazil and overlap reconciliation. Argentina Liga Profesional is listed in the all-competitions catalogue but is not in the free-tier list; do not assume it is accessible. Free plan limits and delayed score behaviour must be respected. |
| OpenFootball / football.db | Public-domain datasets include Argentina Primera División and Brazil Brasileiro Série A | Historical schedules/results as Football.TXT datasets | Historical/static supplement only. Not a live feed or guaranteed future fixture source. Verify season completeness and last update before importing. |
| GOAL API | Official site advertises a free key with 1,000 requests/day and a broad 1,019-league coverage catalogue; Argentine Liga Profesional is listed with historical matches | Fixtures, results, standings, lineups and match statistics | High-priority candidate for an authenticated free-tier test. Public coverage catalogue does not establish free-tier entitlement per competition. Brazil and women's competition availability remain unverified. Odds/predictions are paid features. |
| StrikerAPI | Published coverage report lists 17 competitions, including Argentine Primera, Brasileirão Série A and NWSL; free tier reported as 500 credits/month across endpoints | Fixtures/results, lineups, player stats, shot locations and modelled xG; odds coverage is separately listed | High-priority candidate for coverage and terms review. It is updated daily, not a live feed. NWSL is one women's competition, not comprehensive women's coverage. Confirm first-party pricing/terms and actual API entitlement before use. No feed redistribution. |
| API Ninjas Football | Its free tier explicitly covers only eight competitions: EPL, La Liga, Bundesliga, Serie A, Ligue 1, Champions League, Europa League and MLS | Current-season fixtures/results, standings, clubs and squads | Not a free-tier solution for Argentina, Brazil or women's competitions. The endpoint catalogue lists more leagues, but the FAQ explicitly limits free-tier competition coverage to eight. Free tier prohibits commercial use. Do not treat its full catalogue as free access. |
| StatsBomb Open Data | Selected historical competitions, including Argentina (specific seasons) and multiple women's competitions | Event-level data, lineups, shots and xG for selected historical matches | Research/training dataset only; selected seasons, not a complete live fixture/result provider. Review repository licence/attribution requirements before use. |

## Proposed no-cost source roles

1. Keep 5DollarFootballAPI as the current primary source for its five verified competitions.
2. Test GOAL API first for broad current fixtures/results coverage, specifically Argentina, Brazil, and the exact women's competitions in Veltrix's target list. Do not promote it to primary until the free key passes live checks and plan-specific coverage is demonstrated.
3. Test StrikerAPI for Argentina, Brazil, NWSL and its available xG/lineup history. Treat its 500 monthly credits as a strict budget; do not spend them on broad polling. Confirm commercial-use terms for Veltrix's intended deployment.
4. Use football-data.org as a focused Brazil and overlapping European source after its free key is available.
5. Use OpenFootball and StatsBomb only as historical/research sources, never as substitutes for current fixtures.
6. Do not use API Ninjas Free as a solution to the missing competition gap; its documented free coverage is only eight competitions.

## Mandatory verification before enabling any candidate

For each source, perform only low-volume GET requests and record:

- Credential presence (never print or copy the credential into logs).
- Actual plan/tier, remaining quota, rate limits, reset time and endpoint-specific restrictions.
- Exact competition identifiers and whether each required competition is accessible on the free tier.
- Upcoming fixture sample and a finished fixture/result sample for each target competition.
- Provider fixture/team IDs, timestamps/timezone, status vocabulary, score shape, pagination and update cadence.
- At least one duplicate/overlap comparison against an already verified source.
- Terms/licensing constraints, including commercial use, attribution, storage and redistribution.
- Historical depth and season completeness from real responses, not marketing claims.

## Import safety and data provenance

- No source is authoritative globally by default. Authority is assigned per competition and data type after validation.
- Preserve each provider's opaque IDs and raw observation provenance.
- Do not merge fixtures by team names, kickoff time, or score alone.
- Cross-provider matches remain reconciliation candidates until a deterministic identity match is established.
- Conflicting scores/statuses are retained as separate observations and quarantined for review.
- Do not treat an API's modelled xG as observed event-derived xG without recording its method and provenance.
- Never create dummy source records, fixtures, import runs or checkpoints to simulate coverage.
- Historical dry-runs must report exact window, pages, source counts, unique IDs, duplicates, missing identities, invalid results, request cost and zero writes.
- No production import until an explicit authorization is obtained after dry-run review.

## Current decision

The source research identifies credible no-cost candidates, but it does not close the production coverage gate yet. GOAL API and StrikerAPI need actual free-account access checks; football-data.org needs a token and a Brazil test; OpenFootball needs dataset completeness review.

Phase 3 remains unsigned for full data readiness. The Neon foundation and 5DollarFootballAPI technical acceptance remain passed. Prediction/report delivery remains paused. No production import, paid upgrade, deployment or reactivation is authorized by this assessment.

## Public references

- 5DollarFootballAPI: https://5dollarfootballapi.com/docs
- football-data.org free coverage: https://www.football-data.org/coverage
- football-data.org API docs: https://www.football-data.org/documentation/api
- OpenFootball South America: https://github.com/openfootball/south-america
- GOAL API coverage: https://goal-api.com/coverage
- GOAL API free-key and quota documentation: https://goal-api.com/mcp
- StrikerAPI: https://strikerapi.com/pricing
- API Ninjas Football documentation: https://api-ninjas.com/api/football
- StatsBomb Open Data: https://github.com/statsbomb/open-data
