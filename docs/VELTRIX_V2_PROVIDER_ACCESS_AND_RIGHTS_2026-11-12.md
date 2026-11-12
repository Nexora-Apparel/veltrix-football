# VELTRIX FOOTBALL 2.0 — Provider access and rights register

Reviewed: 2026-11-12
Scope: technical access, collection, retention, model training, benchmarking, public display and commercial use.

This register is a fail-closed source decision. Technical API access is not proof of data-use rights. Every provider approval is scoped by provider, data type, competition, season and permitted use in the V2 source registry.

## Approved source lanes

### 5DollarFootballAPI — primary fixtures, results and bookmaker odds

**Decision:** approved for the uses expressly granted by the current Terms, subject to plan activation and attribution.

The current Terms permit commercial websites, apps, models and internal tools, including display of scores, statistics and odds and caching responses. Free and Community Access public-facing products must show the linked credit **Football data by 5DollarFootballAPI**. Raw-feed resale or redistribution as a competing data feed is prohibited.

Community Access currently provides:
- Top-five leagues plus one country pack.
- Bet365 opening, closing and in-play markets.
- Twelve months of results and odds.
- 300 requests/hour, with a 20 requests/minute burst ceiling.
- Twelve-month activation, renewable through the Community form.
- No card, paperwork or income verification; the provider accepts the applicant's self-attestation.

The existing account was last verified on the Free plan: 60 requests/hour, 20/minute and three months of history. **Community activation is not yet verified.** The exact competition list and plan must be rechecked through `/v1/status` and `/v1/leagues` after activation.

Preferred country-pack candidate: Argentina, subject to its availability in the activation selector and the actual league list. Do not assume the pack is active. If Argentina is unavailable, compare the offered country packs using competition coverage and historical fixture counts before selecting one.

The API does not supply xG, player statistics, injuries, transfers or confirmed lineups. Do not infer these fields from scores or odds.

Official references:
- https://5dollarfootballapi.com/terms
- https://5dollarfootballapi.com/community
- https://5dollarfootballapi.com/pricing
- https://5dollarfootballapi.com/docs/changelog

### The Odds API — independent odds benchmark and CLV lane

**Decision:** approved for odds collection, retention, commercial display, derived values and statistical/ML model training under its current terms.

The current terms permit indefinite storage, user-facing display including commercial use, derived values and training statistical or machine-learning models. Raw-feed resale, repackaging or redistribution as a standalone data product is prohibited. Attribution is not required.

Use it as an independent bookmaker-market benchmark and for timestamped odds movement/CLV. Do not use bookmaker odds as football-strength model features. Benchmark source/bookmaker identity and the exact common fixture sample must remain recorded.

Official reference:
- https://the-odds-api.com/terms-and-conditions.html

## Technically useful, rights not approved

### PitchAPI — xG, shots, lineups, player data and advanced analytics

**Decision:** technical candidate only; no ingestion into the production training corpus, no long-term retention and no public display until written service-data rights and source-lineage clarification are obtained.

The official API documentation describes 77 leagues, historical coverage back to 2021, shot-level xG/xGOT, player statistics, events, lineups, PPDA, field tilt, heatmaps and other advanced metrics. It also warns that analytics may be unavailable for individual matches and that pre-match lineups may be predictions; only `confirmed=true` represents a confirmed lineup.

The published MIT license for the Python SDK covers the client library, not the football data. The SDK's PyPI page explicitly states that the service data is governed separately by PitchAPI's Terms of Service. The official API documentation reviewed on 2026-11-12 did not expose a usable service-data license granting storage, commercial use, model training or public display.

Required before approval: written confirmation of (1) upstream data providers and lineage, (2) collection and storage rights, (3) historical retention rights, (4) model-training and evaluation rights, (5) public display and commercial derivative-output rights, and (6) attribution requirements.

Official references:
- https://pitchapi.dev/
- https://pypi.org/project/pitchapi/

### GOAL API — fixtures/results and broad competition catalogue

**Decision:** technical access verified; sports-data rights not approved for training, long-term storage or public prediction display.

The user's GOAL_API_KEY is active. The 2026-11-11 read-only technical probe succeeded for Argentina Liga Profesional and Brazil Serie A using Bearer authentication and browser-like headers. This confirms endpoint access only.

The Terms updated November 2026 grant no license or representation over underlying sports-data IP and make the user responsible for obtaining any authorization needed to use or publish the data. They also state that competition rights are not granted. The API's technical access therefore cannot be treated as model-training or publication permission.

Required before approval: written upstream data-provider identity and permission covering historical storage, model training, benchmarking, commercial derivatives and public display in every target territory.

Official references:
- https://goal-api.com/terms
- https://goal-api.com/privacy

## Supplemental or restricted sources

| Provider | Current decision | Reason |
|---|---|---|
| OpenFootball | Supplemental fixtures/results only | CC0 dataset; source records can be date-only or unzoned. Never fabricate UTC kickoff or result-availability timestamps. |
| OpenPlay | Not approved for production training/public display | CC BY 4.0 attribution is required, but upstream event-data lineage and rights remain unverified. |
| StatsBomb Open Data | Research-only | Selective open competitions; no blanket commercial model-training permission is assumed. |
| OpenScores | Discovery only | Useful event/lineup coverage, but upstream data lineage and reuse rights remain incomplete. |
| StrikerAPI | Wait for credit refresh | The prior 500-credit monthly free allowance was exhausted; HTTP 402 means quota exhaustion, not invalid authentication. |
| footballapi.org | Excluded from V2 training pending explicit rights | Free quota is small and terms restrict bulk rebuilding/competing products; no blanket model-training grant. |
| API-Football/API-Sports | Excluded | User's key was suspended twice; do not depend on it. |
| Highlightly | Excluded as fallback | Limited coverage and rate-limit failures. |
| FPL public API | Excluded | Automated extraction is not approved under its terms. |
| FBref/Understat scraping | Prohibited | No unauthorized scraping. |

## Data-use controls required in V2

1. A provider may be used only for the specific data type and competition covered by its approval.
2. Separate permissions are required for collection, storage, model training, benchmarking, public display and commercial use.
3. Preserve provider, endpoint, source observation ID, payload hash, retrieval time, source event time, availability time, competition, season and approval ID.
4. A missing permission is a hard exclusion, not a warning.
5. A predicted lineup must never be labelled confirmed.
6. Missing xG, player statistics or lineup data stays missing; do not synthesize provider values.
7. Provider attribution must be present in the website and Telegram output whenever required by the active plan.
8. Raw provider feeds must never be redistributed as a competing data service.

## Activation and verification sequence

1. Manually activate Community Access on the 5DollarFootballAPI account and select the country pack.
2. Dispatch the existing read-only **Verify Multi-Source Football Providers** workflow.
3. Confirm `/v1/status` reports `plan=community`, 300/hour and 20/minute.
4. Confirm the accessible league list includes the top-five plus the selected country pack.
5. Confirm 12-month history is accessible with bounded historical queries.
6. Reconcile actual fixture IDs, kickoff timestamps, results and Bet365 market completeness.
7. Keep PitchAPI and GOAL API excluded from training/publication until their written rights conditions are satisfied.

No production database imports, model training, publication or schedule activation are authorized by a provider smoke test alone.


The provider acceptance workflow now sets `FIVEDOLLAR_REQUIRED_PLAN=community`.
It fails closed if the account still reports Free. Its bounded probe requests
one scheduled fixture from each of up to eight accessible leagues, then checks
the complete 1X2, BTTS and 2.5 totals market groups for each returned fixture.
The maximum primary-provider smoke sequence is 18 requests (status + league
catalogue + up to eight fixture requests + up to eight odds requests), below
the 20/minute burst ceiling. The optional The Odds API market probe remains
off by default and can consume up to eight additional odds credits.


### OpenFootAPI — per-competition fixture/result candidate

**Decision:** conditional discovery candidate; no blanket model-training or commercial approval.

Its current Terms require each response's source metadata to be carried into published outputs and state that the licence attached to each competition/source applies independently. The service cannot waive upstream source restrictions. The free Starter plan provides fixtures, results, standings and search across a 120-competition catalogue at 5,000 requests/month; xG shot maps and lineups require the Developer plan, currently advertised at $14/month.

This may be useful for supplementary fixture/result discovery only where the exact competition's `/v1/competitions` licence metadata is permissive and source rights have been checked. Do not treat the API's own Terms as a blanket grant to train models on FotMob, ESPN or other upstream data. Do not use the paid xG tier under the current no-software-budget constraint.

Official references:
- https://openfootapi.com/terms
- https://openfootapi.com/docs
- https://openfootapi.com/pricing

### StatsBomb Open Data — non-commercial research only

**Decision:** excluded from the commercial VELTRIX prediction/training corpus unless a separate commercial agreement is obtained.

The public repository describes the data as available for research and genuine interest in football analytics and requires StatsBomb attribution/logo. The Public Data User Agreement restricts commercial exploitation of the data and analysis derived from it. It remains suitable for isolated non-commercial research, not the commercial VELTRIX product.

Official reference:
- https://github.com/hudl/open-data
- https://raw.githubusercontent.com/hudl/open-data/master/LICENSE.pdf
