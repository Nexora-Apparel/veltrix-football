# VELTRIX FOOTBALL 2.0 — Provider Alternatives Assessment
Date: 2026-11-11
Status: research-only; no new source is approved for import by this document.

## Decision constraints

- No API-Football/API-Sports dependency.
- No new paid subscription or credit purchase assumed.
- Preserve point-in-time availability, source provenance, competition/data-type rights and immutable provider identity rules.
- A source that only supplies fixtures/results cannot be treated as a replacement for xG, lineups, shot events or odds.
- A public source is not automatically an approved production source. Qualification still requires exact coverage, rights, freshness, identity and reconciliation checks.

## Candidates

### 1. OpenFootball — strongest zero-cost supplemental results candidate
- Public datasets are dedicated to CC0/public domain and include fixtures/results in JSON/Football.TXT.
- Coverage includes major European leagues and additional competitions; the world repository lists Nigeria Premier Football League, Brazil and other regional competitions.
- Current-season JSON is generated daily at 05:00 UTC, but the project notes that upstream Football.TXT source updates are not themselves automated daily.
- No API key or credit quota.
- Data is fixtures/results only; no bookmaker odds, lineups, shot locations or xG.
- Timing fields are not guaranteed to be full timezone-aware kickoff timestamps. Any date-only or local-time records must not be fabricated into UTC. A conservative availability policy and explicit timestamp precision are required before they can enter point-in-time features.
- **Freshness spot-check:** the public 2026/27 EPL JSON snapshot opened on 2026-11-11 contained Matchday 10 fixtures dated 2026-11-07 with no score fields. This confirms that the generated current-season file can be incomplete for recent results despite the daily generation process. It is not accepted as a current-results primary without overlap reconciliation and freshness checks.
- Candidate use: independent historical results supplement and fixture cross-check, not the sole production feed and not an xG/odds substitute.
- Official sources: https://github.com/openfootball/football.json ; https://github.com/openfootball/world ; inspected snapshot: https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json

### 2. football-data.org — possible free fixtures/results supplement, licensing clarification required
- Free tier advertises 12 competitions, delayed scores/schedules, fixtures and tables, with 10 requests/minute.
- Public coverage includes several major European leagues, Champions League, Brazil Serie A and selected other competitions.
- Visible attribution is required: "Data provided by football-data.org".
- Public terms identify one API key/application and remove rights to reference the data on the user's service after subscription cancellation. Commercial use and retention scope are not sufficiently explicit in the public material reviewed for this project; obtain written clarification before production use.
- No confirmed xG, shot-location or historical odds entitlement on the free tier.
- Candidate use: secondary fixture/results cross-check only after written rights/retention approval.
- Official sources: https://www.football-data.org/pricing ; https://www.football-data.org/coverage ; https://www.football-data.org/about ; https://www.football-data.org/documentation/api

### 3. FootyStats API — strong paid model-data candidate; free tier too narrow
- Official API page advertises 1,500+ competitions, 170+ data points per league, 710+ per team, 65+ per player and result refreshes every 20 minutes.
- Free tier: Premier League only, 180 requests/hour, limited endpoints.
- Hobby: £29.99/month for 50 leagues and 1,800 requests/hour; described as suitable for building soccer learning models.
- API terms explicitly permit use in public apps/websites and models, while prohibiting raw API/data resale or redistribution.
- xG/shot-location support was not confirmed in the reviewed API page; do not assume it supplies xG.
- Candidate use: future paid alternative if budget changes; free tier can only be a limited EPL cross-check and does not solve broad competition coverage.
- Official sources: https://footystats.org/api ; https://footystats.org/api/documentations/terms-of-use-and-legal

### 4. Sportmonks — technically rich but outside current budget
- Free tier is limited to Danish Superliga and Scottish Premiership.
- Starter plan begins at €29/month for five leagues; xG and odds are separate paid bundles, and historical data older than three seasons is a separate add-on.
- Candidate use: technically credible paid replacement, but not a no-budget solution.
- Official sources: https://www.sportmonks.com/football-api/free-plan/ ; https://www.sportmonks.com/football-api/plans-pricing/

### 5. Excluded or not approved

- Football-Data.co.uk free downloads: the owner explicitly restricts free data to personal/academic use and says it is not for commercial or AI/model-training projects. Do not scrape or train on it for VELTRIX.
- StatsBomb Open Data: its stated purpose is research and genuine interest, with source and logo attribution for published work. Do not treat it as a commercial product licence without written permission.
- football-data.org: do not use in production until commercial use, retention and post-cancellation rights are clarified in writing.
- Unauthorised scraping of FBref, Understat or other websites is not an acceptable replacement.

## Recommended no-new-spend path

1. Keep 5DollarFootballAPI as the qualified bounded primary for its existing Free-plan scope only.
2. Keep StrikerAPI as a targeted enrichment candidate when its monthly free credits refresh; do not assume its exhausted balance can be used now. Its official site advertises 500 free credits/month and paid tiers, but usage must be budgeted by endpoint credit cost.
3. Qualify OpenFootball only as a supplemental historical results source, beginning with read-only EPL reconciliation and then a separate Nigeria/Brazil coverage audit. Do not write to Neon during this qualification.
4. Request written rights clarification from football-data.org before any production use.
5. Keep all unqualified competitions and data types blocked. Never promote fixture/results-only qualification into xG, lineups, odds or shot-data approval.

## Acceptance checklist before any import

- Pin a dated source snapshot and exact repository commit/file hashes.
- Confirm CC0 licence for the exact source repository and dataset.
- Normalize competition/season and team identities with explicit approved crosswalks; ambiguous names fail closed.
- Preserve original date/time text and declared precision. Never invent timezone or kickoff time.
- Reconcile a bounded overlapping date window against 5Dollar and an independent trusted source; quarantine mismatched score, orientation, status or kickoff rows.
- Confirm no duplicate fixture identity and report coverage gaps.
- Run isolated dry-run only; compare database counts before/after and require zero writes.
- Obtain separate source approval for each data type. This candidate currently covers fixtures/results only.


## Existing VELTRIX integrations audited for StrikerAPI replacement

This section distinguishes existing credentials/adapters from providers that can actually supply the missing historical match data. Credential names are recorded only; secret values are never read or exposed.

| Existing integration | Repository/config evidence | Can replace StrikerAPI historical fixtures/results? | Decision |
|---|---|---:|---|
| 5DollarFootballAPI (`FIVEDOLLARFOOTBALL_API_KEY`) | Existing primary adapter; Free entitlement previously verified at 60 requests/hour, last three months, five competitions. Bounded StrikerAPI ↔ 5Dollar EPL reconciliation previously matched 100/100 fixtures. | **Partially** | Retain as the already qualified bounded primary for EPL only. It does not replace StrikerAPI's broader Argentina/Brazil results coverage under the known Free entitlement. |
| football-data.org (`FOOTBALL_DATA_TOKEN`) | Historical workflow used this exact variable; the 2026-10-25 results refresh returned HTTP 400 invalid-token. No successful replacement-token verification is recorded. | **Potentially, after requalification** | Best existing API candidate for a fixture/results supplement if the credential is corrected, exact competition coverage is confirmed, and written rights clarification covers model training, retention and post-cancellation use. Do not ingest now. |
| The Odds API (`THE_ODDS_API_KEY`) | Existing odds adapter; historical register records successful auth and soccer market discovery. | **No** | Odds-only role. Not a historical results/fixture source. Preserve for separately approved timestamped bookmaker odds and CLV work. |
| OddsPapi (`ODDSPAPI_API_KEY`) | Optional repository odds-enrichment adapter. Fresh live coverage not established in the current qualification record. | **No** | Odds-only candidate; require its own live coverage and timestamp audit. |
| InferSports (keyless) | Existing adapter; prior read-only probe returned 200 same-day events, but three bounded event-odds probes returned no current quotes. Schema supports 1X2/totals, not BTTS. | **No, not yet** | Not qualified as a historical-results source; keep disabled until a separate data endpoint and coverage are proven. |
| Highlightly | Legacy adapter retained for audit/compatibility; prior 429 rate-limit warning. | **Not approved** | Do not reactivate or use as a silent fallback. Fresh entitlement and coverage qualification would be required. |
| API-Football/API-Sports (`API_FOOTBALL_KEY`) | User-reported suspended; explicitly excluded from active runtime dependencies. | **No** | Remains excluded. |
| Open Matchday | Existing reference in provider register; README describes non-commercial-only use. | **No for VELTRIX production** | Excluded unless licensing is independently changed in writing. |

### Replacement decision

No currently verified existing API fully replaces StrikerAPI's qualified historical results coverage. The viable no-new-spend route is:

1. Keep 5DollarFootballAPI for its already reconciled EPL scope only.
2. Qualify OpenFootball as a CC0 supplemental historical-results dataset, using the read-only overlap and freshness checks in this document. Its current-season freshness spot-check already showed recent fixtures without scores, so it cannot be promoted to current-results primary.
3. Re-test football-data.org authentication only after confirming the credential has been updated; keep it blocked from production until its licensing/retention questions are answered in writing.
4. Do not treat odds providers as match-history replacements.
5. Keep Argentina/Brazil and all other unqualified competition/data-type combinations blocked until a source passes coverage, rights, identity and reconciliation gates.

The prior StrikerAPI HTTP 402 indicates exhausted credits, not invalid credentials. The existing evidence does not provide a supported way to refill those credits from this repository. Retry only after the account balance/monthly allowance is restored; never spend credits on exploratory probes before defining the bounded acceptance sample.


## OpenFootball qualification implementation update (2026-11-11)

Owner decision: proceed with OpenFootball as the selected no-cost supplemental historical-results source instead of waiting for StrikerAPI credits. This is a source-selection decision, not production data approval.

Implemented on the VELTRIX 2.0 branch:
- `veltrix_v2/ingestion/openfootball.py`: strict JSON parser for fixture date, optional local clock time, team names and half/full-time scores.
- Timestamp precision is explicit: `date_only` or `local_datetime_unzoned`. The parser never invents UTC offsets or kickoff times.
- Invalid dates, malformed score arrays, negative/non-integer goals, missing team identities and malformed dataset rows fail closed.
- `veltrix_v2/ingestion/openfootball_reconcile.py`: read-only, in-memory reconciliation against a supplied reference snapshot. Exact team-ID crosswalk is mandatory; no fuzzy name matching. Missing OpenFootball scores are counted separately. Duplicate identities, unmatched rows, unknown teams and score conflicts block pass status.
- Unit tests cover timestamp precision, malformed data, exact identity mapping, missing scores and score conflicts.

CI evidence:
- Foundation test run #42999675419: 91 passed, 0 failed.
- Reconciliation follow-up runs #42999792932 and #42999796260: 94 passed, 0 failed on each run; legacy-import boundary step succeeded.

**Qualification status: implementation and unit-test gates passed; live paired-snapshot reconciliation remains pending.** The next execution must retrieve a pinned OpenFootball EPL snapshot and a same-window 5Dollar reference snapshot, record both payload hashes and source retrieval times, provide an approved exact team crosswalk, then run the comparator without writing to Neon. A successful unit test is not a live data reconciliation and must not be represented as one.

No production source approval, provider import, Neon write, model training, deployment or Telegram activation has occurred.
