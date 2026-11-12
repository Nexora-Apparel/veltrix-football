# VELTRIX FOOTBALL 2.0 — Phase 1 Provider Qualification

**Date:** 2026-11-12  
**Working branch:** `phase1/provider-final-qualification`  
**Phase status:** COMPLETE — PROVIDER STRATEGY VERIFIED AND MERGED  
**Scope:** provider discovery, credential/endpoint access, competition coverage, data rights, historical depth, timestamps, and source selection.  
**Safety:** read-only qualification only. No production imports, database writes, model changes, prediction publication, Telegram delivery, deployment, or scheduling.

## 1. Phase 1 exit decision

The provider inventory is reconciled and a scoped source stack is identified. The consolidated workflow has run and its evidence is recorded in §3.5. The selected stack is 5DollarFootballAPI for fixtures/results, The Odds API for prospective timestamped bookmaker prices, and the licensed Wyscout public event dataset for historical xG research. InferSports remains a non-benchmark live 1X2/totals candidate. StrikerAPI, GOAL API, OddsPapi and other unapproved or inaccessible sources are explicitly excluded from ingestion. The 5Dollar Community account does not satisfy the 98% historical odds-timestamp gate; use prospective timestamped capture and keep value betting locked. The only remaining Phase 1 check is the offline regression suite after the OddsPapi entrypoint fix.

The project will not treat a successful HTTP response, an SDK licence, a public dataset label, or an API key as blanket data-use permission. Approval is scoped by provider, endpoint, data type, competition, season, retention, model training, public display, and commercial use.

## 2. Selected source stack

| Lane | Selected source | Decision | Limits / controls |
|---|---|---|---|
| Fixtures and results | 5DollarFootballAPI | Primary, account/competition scoped | Seven competitions were live-qualified; the exact plan is checked again by the final workflow. Preserve provider IDs and UTC kickoff values. |
| Odds and market benchmark | The Odds API | Approved supplemental benchmark | Current odds carry provider `last_update`; historical events/markets discovery is available on all plans at one credit per request but returns no prices. Historical odds snapshots require a paid plan and are charged by region/market. Do not substitute local retrieval time for provider quote time. |
| Historical shot events for xG research | Pappalardo et al. / Wyscout public event dataset | Approved under CC BY 4.0 with attribution | 1,941 matches across seven competitions; historical only. Train a VELTRIX-owned xG model; do not represent it as provider xG. |
| Non-live player, lineup, shot-event and historical-odds enrichment | No active source; StrikerAPI is conditional future candidate | Excluded from current ingestion | The live account check returned HTTP 402 with zero credits remaining. Do not buy credits. Reconsider only after free-credit refresh, a successful bounded capability probe and accepted Terms-version verification. |
| Supplemental odds | OddsPapi | Excluded pending explicit rights clarification | Terms do not expressly grant model-training, retention or commercial-display rights. The first live probe was blocked by a local Python import-path defect before contacting the provider; the entrypoint is now corrected and regression-tested. No quote result is claimed. |
| InferSports | Supplemental live-odds candidate; not selected as historical source | Current integration probe returned 63 same-day events and an available event-odds response with 1X2 and totals | No BTTS, no verified historical archive or source-created quote timestamps in this probe. Require timestamped sample and coverage measurement before selection. |

## 3. Verified 5DollarFootballAPI evidence

### 3.1 Credential and plan evidence

Run [#43268314432 — Standard vs Community credential comparison](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43268314432) completed successfully.

- Both `FIVEDOLLARFOOTBALL_API_KEY` and `FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY` authenticated.
- Both reported a rate-limit header of 300 requests/hour; remaining values were 289 and 286 at the time of the probe.
- Both returned seven competition rows on catalogue page 1, and the bounded history and fixture-odds checks returned `OK`.
- The 300/hour limit is consistent with Community Access, not the Free plan's 60/hour limit. The new Phase 1 workflow calls `GET /v1/status` directly to verify the plan rather than relying only on rate-limit inference.

Official Community Access documentation describes the top-five leagues plus one country pack, 300 requests/hour, 20 requests/minute, and 12 months of results/odds. See [Community Access](https://5dollarfootballapi.com/community), [pricing](https://5dollarfootballapi.com/pricing), and [changelog](https://5dollarfootballapi.com/docs/changelog).

### 3.2 Fixture qualification

Run [#43269388120 — seven-competition qualification](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43269388120) passed:

- 786 accepted historical fixtures across seven competitions.
- Brazil Serie A: 124; Brazil Serie B: 161; Italy Serie A: 110; France Ligue 1: 90; England Premier League: 100; Spain La Liga: 120; Germany Bundesliga I: 81.
- 12 requests used from a hard budget of 20.
- Zero invalid fixtures, duplicate fixture IDs, or missing team IDs.
- Window: 2026-08-14 through 2026-11-12.

This qualifies fixture retrieval and identity fields for the observed window. It does not establish full-season coverage or advanced-stat completeness.

The provider's public 12-month data-quality table separately reports the following finished-match counts and coverage for these same competitions: England Premier League 370; Spain La Liga 381; Italy Serie A 380; France Ligue 1 284; Germany Bundesliga I 299; Brazil Serie A 391; Brazil Serie B 390. Reported odds and live-stat coverage is 100% for each of these seven rows; events are 99.7% for La Liga and 100% for the others. This is provider-reported aggregate coverage, not an independent fixture-by-fixture audit, and it does not establish timestamp coverage for each market. The table labels these competitions Pro, while the user's two keys returned 300/hour limits and the live fixture probe returned seven competitions; the account's `/v1/status` response and actual accessible catalogue are therefore the authority for this account's entitlement. See [measured data quality by competition](https://5dollarfootballapi.com/docs/data-quality).

### 3.3 Statistics endpoint qualification

Run [#43272673240 — statistics capability probe](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43272673240) passed:

- Seven of seven sampled competition statistics requests returned HTTP 200 and the expected field names.
- 15 requests used from a hard budget of 20.
- The probe selected only one finished fixture per competition.
- The probe checked field presence, not numeric completeness, range validity, match-to-match completeness, or full historical coverage.

The official endpoint is explicitly documented as **live match statistics**: attacks, dangerous attacks, shots on/off target, possession and first-half splits. It is not an xG, player-statistics, injury or confirmed-lineup feed. A successful finished-fixture sample is evidence that those seven records still returned a statistics block; it is not proof that the endpoint supplies a complete historical pre-match feature archive. See [official statistics documentation](https://5dollarfootballapi.com/docs/statistics).

### 3.4 Data rights and timestamp limits

The October 2026 Terms permit use in the customer's own commercial websites, apps, models and internal tools, including caching and end-user display. Free and Community public-facing products must visibly include linked attribution: **Football data by 5DollarFootballAPI**. Raw-feed resale or redistribution as a competing feed is prohibited. See [Terms](https://5dollarfootballapi.com/terms).

Community includes 12 months of Bet365 odds history with opening, closing and in-play prices, but the public plan matrix reserves full tick history for higher tiers. The fixture-odds response documents `opened_at` for 1X2 opening; it does not show a timestamp on every market's opening/closing object. Therefore, Community access alone does not prove the required 98% timestamped coverage for every selected market. The final Phase 1 probe samples one finished fixture per competition and counts timestamped market blocks. Preserve actual provider quote timestamps when present; never substitute local retrieval time. The dedicated `/v1/fixtures/{id}/odds/history` endpoint returns per-price `recorded_at` ticks but explicitly requires Ultra or above; Free and Pro receive HTTP 403. Community is not listed as an eligible tier, so the final probe makes one BTTS history request to verify the actual account response. The full per-price movement history is not assumed available on Community.

## 3.5 Consolidated live qualification — run #43280026573

The final manual workflow completed on branch `phase1/provider-final-qualification` at commit `fd34a68d34bf72d04eab02b216128878f1bcf501`. GitHub reports the job and unit-test step as successful. The provider steps were deliberately configured with `continue-on-error` so independent checks could finish; therefore the overall green workflow is not a provider-qualification pass. Artifact: [veltrix-phase1-provider-qualification](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43280026573).

Observed results:

- **Multi-source integration:** 3/3 providers authenticated and returned valid response schemas. 5Dollar returned one Lagos-today fixture and 12 market keys; The Odds API returned 46 active soccer sports, 20 EPL events and BTTS/h2h/totals; InferSports returned 63 Lagos-today events and an available event-odds response with 1X2 and totals. These are point-in-time connectivity checks, not season coverage.
- **5Dollar account:** `/v1/status` reports Community, 300 requests/hour and 20/minute burst; seven competitions are visible. The 17-request sample returned 77 market blocks across seven finished fixtures, but only 7/77 (9.09%) contained a market timestamp. The 1X2 opening timestamp was present for each sample; the other sampled market blocks lacked timestamps. A BTTS tick-history request returned HTTP 403. Thus this account does not currently satisfy the 98% timestamped-market coverage requirement.
- **GOAL API:** one request returned HTTP 403. Cloudflare's response explicitly says the site owner blocked access based on the request's browser signature. This is not evidence that the user's key is invalid; technical access remains unresolved. Its data rights are separately unresolved.
- **OddsPapi:** the first attempt did not reach the provider; direct script execution failed with `ModuleNotFoundError: No module named 'app'`. The entrypoint has since been corrected to add the repository root to `sys.path`, and a regression test has been added. No live OddsPapi result exists yet; do not count it as qualified.
- **StrikerAPI:** the static one-credit account check returned HTTP 402 with zero credits remaining. The feature and historical-odds probe was correctly skipped; no additional credits were spent.
- **Side effects:** the run performed zero database writes, imports, prediction changes, Telegram messages or deployments.

OddsPapi remains excluded because its data-use rights are not expressly granted; the corrected entrypoint is retained for a future rights-cleared probe, but another live request is not required for the selected source stack. Do not repeat the 5Dollar 17-request sample or spend additional StrikerAPI credits. GOAL API remains excluded; its latest 403 was a Cloudflare browser-signature block, not proof of an invalid key.

## 4. Other provider decisions

### The Odds API

The current Terms permit indefinite storage, commercial display, derived values, and training statistical/ML models, while prohibiting raw-feed resale. Historical odds are timestamped snapshots (10-minute intervals from June 2020, 5-minute intervals from September 2022) but the historical odds endpoint is paid-plan only. Historical events/markets discovery is available on all plans but does not return prices.

Decision: use as an independent odds benchmark and prospective quote source. The 1,000-match benchmark and value-bet gates remain blocked until sufficient approved timestamped odds are available. References: [Terms](https://the-odds-api.com/terms-and-conditions.html), [historical odds](https://the-odds-api.com/historical-odds-data/), [API guide](https://the-odds-api.com/liveapi/guides/v4/).

### StrikerAPI

StrikerAPI is the strongest non-live enrichment candidate found. Its public data catalogue lists 17 competitions and documents fixtures/results, lineups, player match lines, team stats, shot locations/events, xG, and odds. It has no in-play/live match feed. Free accounts receive 500 credits per month without a card; credits refresh within three days of the account's monthly anniversary.

Coverage is substantial but not uniform: fixtures/results are listed from 2001-02; lineups are available from 2001-02; full box scores and player stats are partial by league/season; full shot-event coverage starts in 2012-13 and shot locations are complete from 2013-14. Odds are listed from 2017-18, with opening/closing archive lines from June 2020 for 16 competitions. The data coverage page says odds archive coverage is partial by season and book count; actual selected-competition coverage must be measured.

The documented endpoints directly match VELTRIX needs:
- `get_game` (5 credits): match score, team box scores, each player's line and bookmaker line.
- `get_lineups` (5 credits): starting XIs, benches, formations and substitutions.
- `get_events` (10 credits) and `get_shot_map` (10 credits): shot locations, xG and event detail.
- `get_team_stats` (5 credits): per-match goals, xG, shots, possession, passing and discipline.
- `get_odds` (5 credits): 1X2, handicap and totals, with archived opening/closing lines and a `captured_at` field.
- `get_market_odds` (10 credits): BTTS opening/closing lines with `opening_captured_at` and `closing_captured_at`, history from May 2023.
- `get_line_movement` (10 credits): pre-kickoff sportsbook snapshots with `captured_at`, including hourly captures when requested.

Timestamp interpretation is strict. For `get_odds`, only rows whose `source` is `archive` and whose `captured_at` is valid are counted as historical quote timestamps. Rows marked `final` may carry a later ingestion/update timestamp and must not be treated as the original quote time. For `get_market_odds`, opening/closing capture timestamps are counted separately. For `get_line_movement`, only valid `captured_at` snapshot rows count. This avoids inflating the 98% odds-coverage gate.

The provider's own xG is not point-in-time safe because its model is fitted across seasons. VELTRIX must use raw shot locations to train and validate its own xG model. Confirmed lineups must be distinguished from predicted/unknown lineups; no lineup should be backfilled as if it were known at the 06:00 forecast cutoff.

The current Terms permit storage, research, backtesting, proprietary model training and commercial app/derived-output use, while prohibiting redistribution of raw feeds or raw odds as a standalone product. The provider is not affiliated with leagues, clubs, players or sportsbooks and does not grant their marks. Third-party source-specific restrictions may apply and must be carried through. The applicable Terms version depends on the account's creation/acceptance date; confirm the account's accepted version before production ingestion.

The last recorded VELTRIX account request returned HTTP 402 (insufficient credits). The final workflow now makes one static `list_teams` check (maximum one free credit); only if it succeeds does it run the bounded feature/timestamp probe (maximum 62 additional free credits). If the static check returns 402 or the key is missing, no further StrikerAPI calls occur. No paid credits or wallet top-up is authorized.

Decision: do not select StrikerAPI for the active stack until the free balance is restored and the account Terms version is confirmed. Its public endpoint catalogue makes it the first candidate to re-evaluate later, not a current dependency. References: [official API/data coverage](https://strikerapi.com/docs), [timing and rights](https://strikerapi.com/docs/timing-and-rights), [terms](https://strikerapi.com/terms), [get_odds](https://strikerapi.com/docs/get-odds), [get_market_odds](https://strikerapi.com/docs/get-market-odds), [get_line_movement](https://strikerapi.com/docs/get-line-movement).

### GOAL API

The 2026-11-11 bounded read-only probe passed for Argentina Liga Profesional and Brazil Serie A fixtures/results using Bearer authentication. The 2026-11-12 consolidated probe returned HTTP 403 with a Cloudflare message that the request was blocked based on its browser signature. This does not establish that the key is invalid; it establishes that the current runner cannot reach the endpoint with its present request fingerprint. The provider's Terms do not grant the underlying sports-data IP rights and place third-party rights clearance on the customer.

Decision: preserve the credential, but exclude GOAL API from V2 training, persistent history and public display until upstream rights and permitted uses are documented. References: [documentation](https://goal-api.com/documentation), [Terms](https://goal-api.com/terms).

### Wyscout public event dataset

The Pappalardo et al. public dataset contains approximately 1,941 matches and 3.25 million events across five European first divisions, the 2018 World Cup and Euro 2016. The paper identifies CC BY 4.0 licensing. This is a viable historical shot-event source for training a VELTRIX-owned xG model with required attribution and change notices; it is not a current-season feed. Reference: [Scientific Data paper](https://www.nature.com/articles/s41597-019-0247-7).

### OpenPlay

The v0.1.0 release reports 26,536 in-scope matches, 41.6 million events and 669,404 shots with xG, plus player-match statistics and lineups. It declares CC BY 4.0, but its upstream WhoScored/Opta/Stats Perform lineage is not independently established. Keep it quarantined from production training and display pending upstream rights confirmation. Reference: [OpenPlay release](https://github.com/nlbair/openplay/releases).

### Excluded / not selected sources

- **PitchAPI:** technical candidate; service-data rights, upstream lineage, storage and training permission not verified. No ingestion.
- **StatsBomb Open Data:** research-only under its published agreement; no blanket commercial training approval.
- **OpenFootball:** supplemental fixtures/results only. Prior 90-day EPL comparison had 45/100 exact score matches, six date conflicts and 49 missing scores; not accepted as primary results.
- **OpenMatchday:** repository states non-commercial use; excluded from commercial training/publication.
- **Football-Data.co.uk:** personal/academic-use restrictions; excluded from commercial model training.
- **OpenFootAPI:** source-specific upstream licence controls; top-five samples were labelled FotMob Unlicensed-Beta, so not approved for those competitions.
- **FPL public API:** excluded after terms review.
- **API-Football/API-Sports:** do not depend on it; prior key suspensions.
- **Highlightly:** excluded due limited coverage and rate-limit failures.
- **InferSports:** the latest bounded probe returned 63 same-day events and an available event-odds response with 1X2 and totals. Keep as a supplemental discovery candidate only; no BTTS, historical archive, or quote-time coverage was verified, so it is not a historical benchmark or value-bet source.
- **Club-Football-Match-Data:** do not admit into the training corpus until the exact upstream data rights and per-source licence are cleared.

## 5. Known data gaps

No currently approved source provides the full current-season combination of xG, confirmed lineups, player-level statistics, injuries, PPDA, shot conversion and travel/rest context across all seven qualified competitions.

- 5Dollar covers fixtures/results and selected match/odds fields, but does not claim xG, injuries, transfers, player profiles or player-level statistics.
- The Wyscout event dataset is historical (2017/18, World Cup 2018, Euro 2016).
- No approved current-season source is selected for player-level statistics, confirmed lineups, injuries or broad shot-event enrichment. StrikerAPI remains conditional but the account returned HTTP 402; no paid credits are authorised.
- The Odds API historical price archive requires a paid plan. Until adequate timestamped prices are available, bookmaker benchmark and value-bet certification remain incomplete.
- Missing data must remain explicitly missing. Do not infer xG from odds, call a predicted lineup confirmed, or fabricate fatigue/travel values.

## 6. Consolidated final qualification workflow

The branch updates the existing `Multi-Source Provider Verification` workflow and adds:

- a read-only 5Dollar `/status` + `/leagues` plan/country-pack check, plus at most one finished-fixture odds/timestamp sample per competition and one BTTS tick-history entitlement check (17-request cap, 4-second pacing);
- a sanitized OddsPapi soccer-market/quote probe;
- the existing bounded The Odds API / InferSports integration checks;
- the existing GOAL API read-only probe when its secret exists;
- a machine-readable, SHA-256-checked provider report artifact;
- a one-credit StrikerAPI static account check, followed by at most 62 free credits of feature/odds qualification only when the static check succeeds.

Workflow dispatch is manual only. It does not write to the database, import historical data, train models, change predictions, publish command data, send Telegram messages, deploy Vercel, or schedule jobs.

## 7. Phase 1 acceptance gates

Phase 1 acceptance decision:

1. **Consolidated workflow:** run #43280026573 completed; its offline test step passed. Provider steps use `continue-on-error` to collect independent evidence, so the overall green conclusion is not interpreted as every candidate qualifying.
2. **Primary account:** the manual run verified the 5Dollar Community plan, 300 requests/hour, 20/minute burst and seven-competition catalogue.
3. **Selected provider connectivity:** the same run verified 5Dollar, The Odds API and InferSports response schemas; The Odds API returned BTTS/h2h/totals, and InferSports returned 1X2/totals quotes in its bounded sample.
4. **Source register:** the selected stack, exclusions, rights constraints and missing-feature controls are documented in this file.
5. **No unapproved ingestion:** the run performed zero imports/database writes; no unapproved source is admitted to the training corpus.
6. **Regression correction:** the OddsPapi script's local import-path defect was corrected and a direct-execution regression test was added. PR #57 merged as commit `cd500d0beb4d9f41bbabf80022a52a25947dd1f8`; all three PR checks (`unit-tests`, `foundation`, `verification`) completed successfully.

The 5Dollar 9.09% sampled timestamp rate and HTTP 403 for tick history are explicit historical-odds limitations. They block the later 98% timestamp-coverage/value-betting gate, not fixture-provider qualification. The Odds API is the approved prospective timestamp source; the archive remains insufficient until measured data accumulates.

The next phase is the historical data foundation. It must not begin until these Phase 1 gates are verified. No production deployment, Telegram activation or schedule is authorized by Phase 1 completion.


## 8. Final consolidated provider execution — 2026-11-12

- GitHub Actions run: [43280026573](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43280026573)
- Job: 131398564898
- Artifact: `veltrix-phase1-provider-qualification` (ID `13972845473`)
- Artifact SHA-256: `3c45fdc06fdd5e91bdda332f7f303b01ff434e71f9e793e1137a916206820ffd`
- Run conclusion: `success`; the workflow intentionally continues after individual optional-provider failures so all independent probes finish. A green workflow does not mean every provider qualified.

| Provider | Observed result | Phase 1 disposition |
|---|---|---|
| 5DollarFootballAPI | Community; 300/hour, 20/minute; seven competitions; odds endpoint returned 77 market blocks, only 7 with timestamped quotes (9.09%); BTTS odds-history endpoint returned HTTP 403. Separate statistics probe: 7/7 sampled finished-fixture calls HTTP 200 with documented fields. | Primary fixture/result source; supplemental live-stat fields only. Historical odds archive not qualified. |
| The Odds API | Connected; 46 active soccer sport keys; 20 EPL events; H2H, BTTS and totals markets; 295 requests remaining in the sampled quota response. | Supplemental current-market source; no historical timestamp archive qualification claimed. |
| InferSports | Connected; 63 current-day fixtures; 1X2 and totals available; no BTTS in the sample. | Supplemental discovery/market source only; no historical archive or 98% timestamp evidence. |
| GOAL API | User-confirmed active credential; API request blocked with HTTP 403 by Cloudflare browser-signature challenge before a usable data response. | Excluded pending provider-side access path; key is not classified as invalid. |
| OddsPapi | Qualification script stopped before the provider request with `ModuleNotFoundError: No module named 'app'`. | Harness failure, not a provider rejection; no live-quote qualification claimed. Rights for model training/long-term retention remain unapproved. |
| StrikerAPI | Static account check returned HTTP 402; free credits exhausted. No additional feature calls were made. | Not qualified; no paid credits authorised. |

The final Phase 1 result is **COMPLETE_WITH_EXCLUSIONS**: one primary fixture/result provider and two supplemental current-market/discovery providers are technically accessible; optional providers that failed or lack rights are explicitly excluded. No odds source meets the later 98% timestamped-quote gate, so value betting remains locked. The 365-day 5Dollar historical fixture/results window is a Phase 2 acquisition check, not a Phase 1 claim.

The consolidated artifact contained:
- `fivedollar-account.json` SHA-256: `30d4972ed33b9803634c42fab1066a6fbc95e517d2d4791c46f60bc8e7cd9d43`
- `goal-api.log` SHA-256: `a64fa7656b91a40b800fa5574c4dfce016a2be6ff31b18b49617349170ee400b`
- `multi-source-integration.log` SHA-256: `dacc260954cf8db3cbd31796468877dd5740044e1539eb744120967c219ef6e3`
- `oddspapi.log` SHA-256: `2f49e635e68e32b65ceffc9c26a861e0c63d0df5992731d7f1a722a315acc5ac`
- `strikerapi-account.json` SHA-256: `e69618a6a4367735907e50f219ad536c76226c167a0d4b516c6989b4f740d95d`
- `strikerapi-status.log` SHA-256: `0c1e4775b5b3074a6c09a2c22aec134da93091ed3be9eac6a3bf8b641955cd56`
