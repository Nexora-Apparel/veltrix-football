# VELTRIX FOOTBALL 2.0 — Phase 2: Provider Rights and Access

**Status:** COMPLETE — provider rights/access decisions are scoped, all unqualified sources are explicitly excluded, 5Dollar attribution is implemented, and CI passed 105 focused tests plus 568 full-suite tests on the verified runtime-code snapshot (run #152). Subsequent commits changed only documentation and CI trigger configuration.

## 1. Objective and release boundary

Qualify every provider by actual account entitlement, endpoint access, competition scope, data rights, retention, model-training permission, commercial display, attribution, source timestamps and quota. An API key, HTTP 200 response, SDK licence or public OpenAPI schema is not blanket permission to ingest underlying sports data.

This phase is read-only with respect to external data and production infrastructure. It does not import records into Neon, enable prediction workflows, publish forecasts, send Telegram reports, schedule jobs or deploy production.

## 2. Provider decision register

| Provider | Current access evidence | Rights/use decision | VELTRIX role |
|---|---|---|---|
| 5DollarFootballAPI Community | Account status and bounded provider runs show Community, 300 requests/hour, 20/minute burst and seven competitions: EPL, Ligue 1, Bundesliga I, Italy Serie A, La Liga, Brazil Serie A and Brazil Serie B. The two Brazil competitions suggest the selected country pack is Brazil, but the account evidence did not expose an explicit country-pack code; record that country-pack identity as inferred, not confirmed. | Commercial app/model use, caching and public display are permitted under the provider's October 2026 terms. Public Free/Community products must show linked attribution. Raw-feed resale/redistribution is prohibited. Long-term raw-response retention is not explicitly time-bounded in the terms; retain only for internal evidence/cache pending clarification. | **Approved, scoped** fixtures/results for the seven observed competitions; target labels and non-time-critical history. Never infer original result-publication time from retrieval time. |
| The Odds API | Existing live probes and adapter tests establish API connectivity and h2h/totals/BTTS market support; the account's historical-odds tier is not proven by current access evidence. | Current official terms, last updated 31 August 2026, permit commercial use in websites/apps/dashboards, derived values, model training and indefinite storage. Raw-data resale or redistribution as a standalone feed is prohibited. Attribution is not required. The 12 November live probe returned 46 active soccer sports, h2h/totals/BTTS markets, BTTS available, and 295 credits remaining after 205 used; this verifies current endpoint access, not historical-plan entitlement. | **Approved supplemental** prospective bookmaker quotes and same-fixture benchmarks, retaining provider quote timestamps. Historical price snapshots remain unavailable until the account's paid-plan entitlement is independently verified. |
| InferSports | Prior bounded probe returned 63 same-day events and 1X2/totals odds; current official site describes live/opening snapshots, read-only access and no full tick-history archive. | No dedicated public data-licensing terms were identified in the official material reviewed. Apache-2.0 on the public OpenAPI repository applies to the specification/code, not automatically to the underlying bookmaker data. | **Quarantined candidate** for discovery only. No persistent ingestion, model training, public display or benchmark use until explicit data rights, retention and commercial-use permission are confirmed. |
| GOAL API | Credential was confirmed active, but the current runner's latest request was blocked with HTTP 403/Cloudflare browser-signature restrictions. | Terms expressly disclaim licensing underlying sports-data IP and place third-party rights clearance on the customer. Betting-platform, mass-media and visual-asset uses may require additional rights. | **Excluded** from V2 ingestion, training and public display until upstream rights and permitted use are documented and endpoint access is reliable. |
| StrikerAPI | Latest account request returned HTTP 402 / insufficient credits. No paid credits are authorized. | Existing review records commercial model/app rights with restrictions and third-party lineage caveats; the exact account-accepted Terms version still needs confirmation. | **Excluded** until free credits/access return and accepted terms plus source-specific restrictions are verified. No purchase. |
| OddsPapi | No successful quote acquisition was established by the latest corrected bounded probe. | Existing terms review does not expressly grant model-training, retention or commercial-display rights. | **Excluded** pending written rights clarification and successful quote/timestamp probe. |
| Wyscout public event dataset | Historical public event dataset; approximately 1,941 matches / 3.25m events across seven competitions. | CC BY 4.0 with attribution and change notices, as described in the source paper. Does not grant rights to club/league marks beyond the dataset licence. | **Approved historical research dataset** for VELTRIX-owned shot/xG modelling only; no current-season feed. |
| OpenPlay | Public release reports substantial event/shot coverage, but upstream WhoScored/Opta/Stats Perform lineage is not independently established. | Declared CC BY 4.0 does not resolve upstream rights chain. | **Quarantined** pending upstream rights confirmation. |
| StatsBomb Open Data / Football-Data.co.uk / OpenMatchday | Public or research datasets are accessible. | Their terms/licences do not provide blanket commercial product/model rights; Football-Data.co.uk is personal/academic-use restricted and OpenMatchday is non-commercial. | **Excluded** from commercial V2 training and publication. |

## 3. 5DollarFootballAPI account and usage controls

### 3.1 Verified entitlement

The account's live evidence records:
- Plan: Community.
- Rate limit: 300 requests/hour.
- Burst: 20 requests/minute.
- Competitions and provider IDs from the 12 November account artifact: Brazil Serie A `3118717965`; Brazil Serie B `522514093`; England Premier League `4160026622`; France Ligue 1 `3614399544`; Germany Bundesliga I `686337048`; Italy Serie A `3405541143`; Spain La Liga `4212821298`. Each catalogue row includes its country. Brazil is the only non-top-five country represented and is therefore the country-pack inference; the API evidence does not expose a separate `country_pack_code` field.
- Historical results/odds plan window: last 12 months according to the current Community plan page.
- Exact repository secret name: `FIVEDOLLARFOOTBALL_API_KEY`. Credential bytes must never appear in logs, artifacts, docs or client-side code.

The account probe reported plan `community`, rate limit 300/hour, burst 20/minute, 17/17 bounded requests and zero database writes/imports/deployments/Telegram sends. The 365-day read-only history run retrieved 2,496 finished fixtures across all seven observed competitions with 26 pages, 28/40 requests, zero duplicate/rejected/quarantined rows and no database writes. This verifies the bounded fixture/result acquisition, not source publication timestamps or historical odds completeness.

### 3.2 Data restrictions and attribution

Official sources:
- [Terms of Service](https://5dollarfootballapi.com/terms), last updated October 2026.
- [Community Access](https://5dollarfootballapi.com/community).
- [Pricing](https://5dollarfootballapi.com/pricing).
- [Changelog](https://5dollarfootballapi.com/docs/changelog).

The terms allow commercial products, models, internal tools, response caching and end-user display. They require the linked phrase **Football data by 5DollarFootballAPI** on public-facing Free/Community websites, apps, bots and published datasets. Raw feed resale/redistribution as a competing data product is prohibited.

Attribution implementation:
- The website/dashboard already includes the linked provider attribution in its footer.
- The Telegram report formatter and all Telegram command replies now append the same linked attribution.
- Regression tests require the attribution in report messages and command replies.

The terms do not specify a fixed raw-response retention duration or identify the upstream data supplier. VELTRIX may cache/use the permitted data internally, but will not publish raw response archives or offer bulk downloads. Seek written clarification before treating raw response bytes as an indefinite public archive.

### 3.3 Point-in-time limitations

- Settled scores can be retained as outcome/target labels.
- The API does not expose the original result-publication timestamp for every historical result. The existing four-day post-kickoff availability proxy is not an observed publication timestamp and is not point-in-time feature evidence.
- Community access does not provide the full historical odds-tick endpoint. The sampled historical market timestamp coverage was 7/77 (9.09%), below the 98% certification requirement.
- Preserve provider quote timestamps when supplied; never substitute local retrieval time as the original quote time.

## 4. The Odds API decision

Official [Terms and Conditions](https://the-odds-api.com/terms-and-conditions.html), last updated 31 August 2026, expressly permit:
- storing data indefinitely;
- commercial display in websites, mobile apps and dashboards;
- displaying derived values;
- using data to train statistical and machine-learning models.

They prohibit resale/repackaging/redistribution of raw data as a standalone feed. Attribution is not required. API keys must remain private. The provider also places responsibility for local gambling-promotion compliance on the customer and recommends responsible-gambling messaging (for example, 18+ / Gamble Responsibly) if the product promotes bookmakers or gambling services. VELTRIX must complete a target-market review and add suitable messaging before adding bookmaker promotion, affiliate links or wagering calls to action.

VELTRIX will use The Odds API as the supplemental prospective quote and bookmaker benchmark source. Store the source's event ID, bookmaker, market, outcome, decimal price, provider `last_update`, local fetch time, request/response fingerprints and exact response bytes. Certification uses the provider's quote timestamp, not local fetch time.

Historical odds price retrieval is a separate paid entitlement. Historical events/markets discovery alone does not return historical prices. The 12 November 2026 account probe observed 205 credits used and 295 remaining (500 total by arithmetic); the public pricing page lists 500 credits/month on the Starter Free plan, but the account tier was not returned as an explicit plan field in this probe. Do not treat the arithmetic as definitive account-plan proof. No historical-odds entitlement is assumed until a bounded account probe returns a successful historical price snapshot. Historical featured-market snapshots are spaced at 10 minutes before September 2022 and 5 minutes thereafter; the documented historical endpoint costs 10 credits per region per market and is paid-plan only. See [historical odds documentation](https://the-odds-api.com/historical-odds-data/) and [current pricing](https://the-odds-api.com/).

## 5. Excluded provider controls

### InferSports
Official [site](https://infersports.dev/) currently describes a read-only odds API, opening/current line pairing and current-state snapshots without full tick history. Its public OpenAPI repository is licensed Apache-2.0, but that licence does not prove rights in upstream bookmaker odds. Keep the integration off for V2 training and public display until the provider supplies written terms covering commercial use, storage, model training and redistribution/display of derived values.

### GOAL API
Official [Terms](https://goal-api.com/terms), last updated November 2026, state that GOAL API does not grant a licence to underlying sports-data IP; the customer must obtain third-party authorizations where required. Logos/images have separate rights, and betting-platform/mass-media uses may need additional licences. Preserve the active credential, but do not use the provider until written rights and access are resolved.

### Other excluded sources
- StrikerAPI: HTTP 402, no paid credits authorised.
- OddsPapi: no explicit model-training/retention/commercial-display grant found.
- OpenPlay: upstream data lineage unresolved.
- StatsBomb Open Data, Football-Data.co.uk and OpenMatchday: no blanket commercial-use permission.

## 6. Current implementation changes

- Added required 5Dollar attribution to all Telegram report chunks.
- Added required 5Dollar attribution to every Telegram command response.
- Added regression assertions for linked attribution in both channels.
- Website footer attribution was already present and remains unchanged.
- No database writes, data imports, prediction changes, Telegram sends, scheduling or production deployment were performed.

## 7. Phase 2 exit gates

1. 5Dollar Community plan and seven visible competition IDs were verified from the bounded `/v1/status` and `/v1/leagues` account probe. The country-pack identity remains inferred from the two Brazil competition rows; ingestion is strictly limited to the seven observed IDs.
2. The Odds API account tier is not independently exposed by the live quota probe. Historical prices therefore remain disabled; prospective quotes are the only approved use. No paid upgrade or historical-price purchase is authorized.
3. InferSports data rights were not established; it remains excluded from persistence, training, public display and benchmarking.
4. GOAL API remains excluded because its terms do not license underlying sports-data IP and current runner access is blocked.
5. OddsPapi and StrikerAPI remain excluded due unresolved rights/technical access; no credits or paid plan were purchased.
6. Website, Telegram report and Telegram command attribution are implemented; the focused suite passed 105 tests and the full suite passed 568 tests in run #152.
7. Phase 3 must encode these source-specific decisions as enforceable rights/entitlement records before any ingestion. No unapproved source may enter V2 history or training.

**Phase 2 release status:** COMPLETE. This approves only the explicitly scoped uses above; all unqualified providers and historical-odds access remain disabled.
