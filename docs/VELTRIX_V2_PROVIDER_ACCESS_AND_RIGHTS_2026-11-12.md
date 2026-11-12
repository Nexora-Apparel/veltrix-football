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

**Timestamp limitation for odds certification:** the documented Community-access odds endpoint returns an `opened_at` timestamp for the Bet365 1X2 opening quote, but the documented closing quote and most other market-stage objects do not carry a provider quote timestamp. The full tick-history endpoint, which returns per-tick `recorded_at`, requires Ultra. Therefore Community-access 5Dollar odds may be used for bounded market-availability checks and only for quote rows whose actual provider timestamp is present; they must not be assumed to satisfy the 98% timestamped-odds certification gate. The Odds API remains the preferred certification benchmark source. The 5Dollar smoke workflow's market counts are not timestamp-coverage evidence.


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
one fixture from each of the five top-five country codes plus one identifiable
country-pack league. It tries a scheduled fixture first and falls back to one
finished fixture when no upcoming game exists. It then checks the complete
1X2, BTTS and 2.5 totals market groups for each returned fixture. The hard
maximum primary-provider smoke sequence is 20 requests (status + league
catalogue + six scheduled lookups + six finished fallbacks + six odds lookups),
within the 20/minute burst ceiling. The optional The Odds API market probe remains
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


### Wyscout Soccer Match Event Dataset (Pappalardo et al. 2019) — historical shot-event training

**Approved for historical model training with attribution.**

**Decision:** approved as a historical shot-event dataset for building VELTRIX's own xG model, subject to retaining the CC BY 4.0 attribution and change notice. It is not a live data provider and does not supply current-season shot events.

The peer-reviewed data descriptor states that the seven datasets are released under CC BY 4.0. The dataset contains 1,941 matches across the 2017/18 Spanish, Italian, English, German and French first divisions, the 2018 FIFA World Cup and UEFA Euro 2016. The processed event files contain shot events, event tags, player/team identifiers, event times and pitch positions.

VELTRIX must train its own xG estimator from shot locations and event context. The dataset does not provide a ready-made xG target. Do not describe a derived VELTRIX xG value as an official Wyscout xG value. Retain original source metadata, payload hashes, license and attribution. Do not use the dataset as a current-season feature feed or claim current lineups, player availability or match statistics from it.

Required attribution:
**Shot-event training data: Pappalardo et al. (2019), “A public data set of spatio-temporal match events in soccer competitions”, CC BY 4.0. Adapted to train the VELTRIX xG model.**

Official references:
- https://www.nature.com/articles/s41597-019-0247-7
- https://figshare.com/collections/Soccer_match_event_dataset/4415000
- https://creativecommons.org/licenses/by/4.0/
- https://github.com/koenvo/wyscout-soccer-match-event-dataset (processed mirror; the Figshare collection remains the canonical source)


## Current xG feed status

The Wyscout CC BY dataset provides licensed historical shot events for training
an independent xG estimator, but it is not a current-season feed. 5Dollar and
The Odds API do not supply shot-level xG inputs. StrikerAPI exposes shot events
and locations, but its 500-credit free allowance is limited, its current
provider xG is not point-in-time safe, and the upstream source list is not
published per dataset; it remains conditional pending credit refresh and
written source-lineage clarification. OpenFootAPI's xG shot maps require the
$14/month Developer plan and inherit a separate licence for each upstream
competition. PitchAPI remains excluded pending written data rights, while
GOAL API remains excluded pending upstream rights. Consequently, the V2
system may train and evaluate a historical xG model, but it must not claim
live team xG or current shot-quality features until a rights-approved,
operationally sufficient current shot-event source is connected. Missing live
xG remains missing and cannot be imputed from bookmaker odds.


The ingestion adapter records the dataset publication date (2019-10-28) and
uses a conservative availability cutoff of 2019-11-01 00:00 UTC (four days
after the date-only publication record). This prevents the 2017/18 and 2018
shot events from appearing in historical training folds whose forecast cutoff
predates public availability. The internal rights approval identity is
`approval-wyscout-open-data-cc-by-4.0`; the corresponding source approval must
carry collection, storage, model-training, benchmarking, public-display and
commercial-use permissions with the CC BY 4.0 attribution.


The Community acceptance workflow now fails unless the account reports
`plan=community`, exposes all five top-five country codes (GB-ENG, ES, IT,
DE, FR), and exposes at least one additional non-top-five country code for the
selected country pack. It probes one fixture in each top-five country plus
one country-pack fixture, using a recent finished fixture if no scheduled
fixture exists. The entire sequence is capped at 20 requests. A five-league
Free-plan catalogue or an unidentified country pack cannot pass. Both the 5Dollar and The Odds API odds adapters require a nonblank
source-observation ID for every parsed or fetched quote; missing lineage is
rejected before a snapshot can be produced. The Odds API now has separate
1X2 (h2h) and totals parsers/fetchers, with same-bookmaker selection groups,
exact total-line identity, provider quote timestamps, and request-quota headers
preserved for benchmark and CLV evidence.


The V2 odds normalization and certification path now require all selections in
a bookmaker market group to share the exact provider quote timestamp and
immutable source-observation ID, in addition to fixture, source, bookmaker,
line, local capture time and kickoff. Coverage ignores incomplete or mixed
groups. When multiple complete 1X2 quote captures exist for one fixture, the
benchmark selects the latest provider quote timestamp (then latest capture);
ambiguous ties fail closed. This preserves historical odds movement records
without double-counting one fixture in the bookmaker comparison.


The source approval contract now refuses `status=approved` unless the record
contains a rights-evidence URI, SHA-256 digest of the reviewed document,
timezone-aware review timestamp, reviewer identity and a declared legal basis
(`terms`, `written_permission`, `open_license` or `contract`). Provisional
records may remain incomplete but cannot pass source eligibility. A provider
key, successful HTTP response or a bare approval boolean is not sufficient.


## Provider requalification update — official terms checked 2026-11-12

### StrikerAPI — conditional commercial shot-event candidate

**Updated decision:** conditional candidate for fixtures/results, lineups, shot locations and event-derived features; not yet fully cleared for production model training because the provider does not publish a source list per dataset and expressly disclaims granting league rights.

Official Terms last updated 2026-11-12 (effective 2026-10-17; for accounts created before 2026-10-17, the new version applies from 2026-12-16). The terms expressly allow commercial apps, websites and tools, storage, deriving values, research and training proprietary models. They prohibit reselling/repackaging the raw data as a feed, file, dataset or API, and prohibit redistributing odds as a raw/bulk feed. No attribution is required. The provider states that it is not the original producer of sports facts, that third-party sources can impose restrictions, and that league/team/player marks are not licensed.

The official timing/rights guide states:
- Free accounts receive up to 500 credits monthly; failed/empty requests may be refunded under the terms.
- `get_events` costs 10 credits per request (up to 50 such requests from 500 credits before any other calls).
- Events and box scores refresh daily at 10:00 UTC and can be refetched for about 1.5 days after full time; each refresh replaces the current record.
- No per-record revision history or revision ID is retained.
- Provider xG is **not as-of**: its location model is fitted using later seasons and refitted, which revalues prior shots. Do not use StrikerAPI xG as a historical point-in-time feature. If approved, retrieve shot locations and train a separate VELTRIX-owned xG model.
- The provider's terms permit use while the account is open; after account closure, retained data is limited to internal research/backtesting and cannot continue powering a customer-facing product.

**Integration constraints:** retain each retrieval as a new immutable observation; never overwrite an earlier response; store the exact retrieval timestamp and payload hash; do not backdate corrected events; use only source-backed shot coordinates to train VELTRIX xG; exclude provider xG from model features and evaluation targets unless a separately documented research comparison is explicitly isolated. The provider's source list is not published per dataset, and it does not grant league rights. Request written source-lineage and sublicense clarification before approving all competition datasets for public commercial use. Verify which Terms version applies to the account before activation.

Official references:
- https://strikerapi.com/terms
- https://strikerapi.com/docs/timing-and-rights
- https://strikerapi.com/docs/get-events
- https://strikerapi.com/pricing

### OpenFootAPI — conditional fixtures/results and paid xG candidate

**Decision:** free Starter may be tested for fixtures/results/standings; xG, shot maps, lineups and live events are not in the free Starter plan. Developer is currently advertised at $14/month, outside the present no-software-budget constraint.

The official Terms (effective 2026-09-07) permit indefinite caching/retention and internal statistical research, model training, evaluation and validation for data lawfully received. They do not grant blanket rights over upstream feeds. Every response includes source metadata; each competition entry exposes the applicable source licence. Attribution and any share-alike or redistribution restriction from that upstream licence attach independently and cannot be waived by OpenFootAPI. Raw feed redistribution is not granted.

Current plan details:
- Starter: $0, 5,000 requests/month, 60 requests/minute; fixtures, scores, schedules, standings and search.
- Developer: $14/month, 250,000 requests/month; adds live events, confirmed lineups, shot maps and xG for supported competitions (top five European leagues for xG).
- xG is upstream-sourced from FotMob and not guaranteed for every match; a missing shot map is an explicit unavailable state, not zero xG.

**Integration constraints:** inspect `meta.sources` and the competition's licence metadata for every source/competition/data type before ingestion. Store the licence and attribution with each observation. Do not assume a single OpenFootAPI permission covers every upstream competition. Starter may serve as a fixture/results discovery fallback after its own account/key and source metadata are verified; Developer is not activated under the current budget.

Official references:
- https://openfootapi.com/terms
- https://openfootapi.com/docs
- https://openfootapi.com/pricing

### OpenPlay dataset — expanded coverage, upstream review still open

The v0.1.0 preview declares CC BY 4.0 and reports 26,536 matches with event data, 41.6 million events and approximately 669,404 shots with xG, covering major European leagues, UEFA competitions and selected international tournaments through 2025/26. It also publishes checksums, coverage, known gaps and data-issue files. It is a static snapshot, not a current-season feed. Its xG is the dataset author's model; do not relabel it as VELTRIX xG.

**Decision:** retain as a research candidate, not yet part of the production training corpus, until upstream source lineage and rights authority are confirmed. The repository's CC BY 4.0 declaration is necessary evidence but the current source documentation does not establish a complete upstream sublicensing chain for every event record. Any later approval must retain attribution to "openplay (Noah Bair)", preserve the licence, and exclude rows listed in known gaps/data issues.

Official references:
- https://github.com/nlbair/openplay
- https://github.com/nlbair/openplay/releases
- https://creativecommons.org/licenses/by/4.0/

### Updated source decision matrix

| Source | Fixtures/results | Shot events / xG | Commercial model training | Public product use | Current decision |
|---|---|---|---|---|---|
| 5DollarFootballAPI | Yes, account/competition scoped | No shot-level xG | Only within documented data rights and approved scope | Attribution and plan terms apply | Primary fixtures/results after Community activation |
| The Odds API | No core result feed | Odds only | Benchmarking/value lane only | Subject to its terms; no raw feed resale | Preferred odds benchmark |
| StrikerAPI | Yes | Shot events/locations; vendor xG is not PIT | Provider terms expressly permit training; upstream rights still need written confirmation | Provider terms permit commercial derived outputs while account remains open; third-party limits may apply | Conditional shot-event candidate |
| OpenFootAPI Starter | Yes | No xG | Terms allow internal training on lawfully received data; source licence per competition | Per-source licence/attribution controls | Fixture/results fallback candidate |
| OpenFootAPI Developer | Yes | xG/shot maps on supported competitions | Same source-specific restrictions | Per-source licence/attribution controls | $14/month; not activated |
| PitchAPI | Yes | Yes | No published rights chain verified | No published commercial/public-display grant verified | Technical-only; blocked |
| GOAL API | Yes | No verified shot-event feed | No blanket grant | No blanket grant | Technical-only; blocked |
| Wyscout 2019 open dataset | Historical match/event data | Historical shot events | CC BY 4.0; train own xG | Attribution required | Approved historical research/training source |
| OpenPlay v0.1.0 | Historical only | Shot events and xG | CC BY 4.0 declared; upstream chain unresolved | Attribution required; upstream review open | Quarantined research candidate |


The StrikerAPI read-only qualification harness is capped at 48 calls / 96
documented credits across its eight rolling-window checks and four NWSL
season/stage diagnostics. Each window is capped at four pages of 50 games.
Unit tests assert the hard global budget, pagination truncation and missing-key
fail-closed behaviour. The workflow remains manual-only; do not dispatch it
while the account balance is exhausted. A successful probe is coverage
evidence only, not a rights approval or historical import authorization.


### OpenMatchday — excluded from commercial V2

**Decision:** exclude from the VELTRIX commercial training and publication corpus.

The repository offers 2026/27 fixtures, results and selected match statistics across 75 competitions, but its own README labels the dataset "Free for non-commercial use" and states that the data is free for informational, non-commercial use. This is not a commercial-use grant. Do not ingest it into the commercial model-training corpus, retain it as a production source, or publish it through VELTRIX unless the maintainer grants separate written commercial permission.

Official repository:
- https://github.com/oladeeayo/open-matchday

### American Soccer Analysis (ASA) — MLS-only share-alike candidate

**Decision:** conditional MLS research candidate; not approved as a production training source until the share-alike consequences for model weights and derivative predictions are clarified.

The official API documentation states that returned data is licensed CC BY-SA 4.0 and exposes MLS games, shots, xGoals, team/player xGoals and related analytics. Commercial reuse is not categorically prohibited by CC BY-SA, but adaptations must comply with the same licence and attribution requirements. Whether a VELTRIX-trained model, model weights or prediction outputs constitute an adapted/derived database or other adapted material requires explicit legal review; do not silently treat CC BY-SA as equivalent to CC BY.

Official API documentation:
- https://app.americansocceranalysis.com/api/v1/__docs__/
- https://creativecommons.org/licenses/by-sa/4.0/



## Phase 2 acceptance checklist and manual blockers

The automated work is prepared, but provider qualification cannot be signed off until these external actions are completed and their outputs are retained.

1. **5Dollar Community activation (account owner action).** Sign in to the existing account, select Community Access and choose the Argentina country pack only if it is offered and covers the intended Argentina competitions. Do not buy Pro or any paid tier. Community is a $0 self-attested access path, not an API feature that can be enabled by code. After activation, the existing read-only workflow requires `plan=community`, all five top-five country codes (GB-ENG, ES, IT, DE, FR) plus at least one identifiable non-top-five country code, and a bounded fixture/odds smoke test. Maximum primary-provider requests: 20 (including one finished-fixture fallback per league).
2. **5Dollar verification dispatch (manual GitHub action).** Dispatch `Verify Data Providers` on `veltrix-2.0-architecture-blueprint`. Do not dispatch the daily prediction workflow. If Argentina was selected, set the workflow's `required_country_code` input to `AR`; otherwise leave it blank and verify the returned non-top-five country code. Leave `probe_historical_odds` false unless deliberately spending up to 10 additional Odds API credits to check paid historical access; leave `probe_odds_markets` false unless deliberately spending up to 8 credits. Retain the workflow artifact/log showing plan, competition IDs, country-pack identity and market coverage. A Free-plan response is a hard failure.
3. **StrikerAPI free-credit refresh and dispatch.** The prior account probe returned HTTP 402 because the 500-credit allowance was exhausted. Wait until the account's free credits have replenished, then manually dispatch `Verify StrikerAPI Read-Only Coverage`. The verifier is capped at 48 calls / 96 credits and writes nothing. Do not raise the cap. Its result is coverage-only; it does not approve provider xG or upstream rights.
4. **PitchAPI written rights response.** Obtain explicit written answers on upstream providers, commercial sublicense authority, retention, model training, evaluation, public display, and attribution. Store the dated response and its SHA-256; only then can a reviewer create an approved `SourceApproval`.
5. **GOAL API written rights response.** Obtain upstream source identity and rights for historical storage, model training, benchmarking, commercial derivative outputs and public display. The active API key and successful endpoint calls do not substitute for this approval.
6. **OpenPlay / ASA review.** OpenPlay remains quarantined until upstream source lineage is documented. ASA remains conditional until the CC BY-SA 4.0 implications for model weights and public prediction outputs are resolved.

No manual action above authorizes production writes, a production deployment, Telegram delivery, daily scheduling or value-bet activation. Those remain Phase 7 release-gate decisions.


### The Odds API — timestamp semantics and historical-plan constraint

The current odds response exposes `last_update` at market level; preserve that value as the provider quote timestamp and keep the local retrieval time separately as `captured_at`. Do not substitute the retrieval time for a missing provider quote timestamp.

Historical odds are served as timestamped snapshots with an explicit response `timestamp` (the closest snapshot at or before the requested time): 10-minute intervals from 2020-06-06 and 5-minute intervals from September 2022. The historical odds endpoints are available only on paid usage plans. The historical events/markets discovery endpoints are available on all plans, but they do not return historical prices.

**Release implication:** verify the actual account's historical-odds entitlement before planning 1X2 bookmaker benchmarking across the 1,000-match walk-forward sample. If the account lacks historical-odds access, do not synthesize bookmaker prices from current lines or use local retrieval time as quote time. Keep the value-betting lane locked until an approved timestamped historical benchmark source is available. Prospective current-odds collection can still accumulate timestamped records for future qualification.

Official references:
- https://the-odds-api.com/liveapi/guides/v4/
- https://the-odds-api.com/historical-odds-data/
