# V2 Provider Adapter Research — 2026-11-06

**Status:** Public documentation reviewed; account-specific capabilities remain unverified.  
**Scope:** Design evidence only. No credentials were read and no provider API request was made.  
**Activation:** Disabled until account plan, supported competitions, historical depth, endpoint rights and quota budgets are verified.

## 1. 5DollarFootballAPI — intended primary fixture/results source

Official documentation:
- [API overview and authentication](https://5dollarfootballapi.com/docs)
- [Fixture list](https://5dollarfootballapi.com/docs/fixtures)
- [Team fixtures](https://5dollarfootballapi.com/docs/team-fixtures)
- [Odds movement history](https://5dollarfootballapi.com/docs/odds-history)
- [Changelog](https://5dollarfootballapi.com/docs/changelog)
- [Terms](https://5dollarfootballapi.com/terms)

### Transport contract

- Base URL: `https://api.5dollarfootballapi.com/v1`.
- Read-only REST API; JSON response has a top-level `success` flag and `data`.
- Authentication uses `Authorization: Bearer <key>` (or `X-API-Key`). Secrets must remain server-side and never enter logs.
- Timestamps are UTC ISO-8601; fixture IDs, league IDs and team IDs are provider identifiers, not canonical V2 IDs.
- List responses include pagination; standard list `per_page` maximum is 100, while `include=odds,events,stats` reduces it to 50.
- `GET /v1/fixtures` is a time-window endpoint with a maximum 24-hour window; `status=live` has a separate high-page-size mode.
- Bulk historical access is through `GET /v1/leagues/{id}/fixtures` and `GET /v1/teams/{id}/fixtures`, with pinned `start_time`/`end_time` Unix-second windows and pagination. League fixture order defaults to newest first; pinning time windows is required for stable incremental traversal.
- League IDs retired by provider merges may return HTTP 301 with `error.canonical_id`; adapter must preserve the retired ID and record the provider's canonical redirect instead of silently rewriting provenance.
- Fixture payloads expose provider fixture ID, nested league/team IDs, kickoff, status and goals. The adapter must retain the original raw response and all source IDs.

### Plan and quota constraints

The public docs currently describe:
- Free: last 3 months of results/odds; 60 requests/hour, with a 20 requests/minute ceiling.
- Pro: last 12 months; 10 requests/minute.
- Ultra: full available history (major competitions back to 2014); 40 requests/minute.
- Free/Community hourly limits and paid per-minute limits are account-wide across keys; creating more keys does not multiply quota.
- Response headers expose `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`; HTTP 429 includes `Retry-After`.
- The per-fixture odds movement history endpoint `GET /v1/fixtures/{id}/odds/history` requires Ultra or above. It is not an economical or permitted assumption for broad per-fixture polling.
- The provider publishes plan-dependent competition/season completeness. Historical depth varies by competition.

**Account gate:** The user's active 5Dollar plan, rate window, actual history floor and competition coverage remain unknown. Do not infer them from a previously connected API key or marketing page. The adapter must remain disabled until a dated account-capability profile is recorded. Do not use broad fixture-by-fixture odds-history scans.

## 2. The Odds API — supplementary market prices

Official documentation:
- [V4 API guide](https://the-odds-api.com/liveapi/guides/v4/)
- [Terms and conditions](https://the-odds-api.com/terms-and-conditions.html)

### Transport contract

- Live market endpoint: `GET /v4/sports/{sport}/odds`, with explicit regions and markets.
- Sport keys must be discovered from the sports endpoint; do not hardcode unverified event identifiers.
- The events endpoint can discover event IDs and kickoff/team identity without odds and is documented as not counting against usage quota.
- The single-event odds endpoint is available for additional markets but is one request per event and can be materially more expensive than the bulk odds endpoint.
- `h2h` maps to 1X2-style head-to-head prices; `totals` maps to Over/Under lines. Market availability varies by sport, bookmaker and time.
- Do not assume BTTS is present in the selected soccer feed. Discover actual market keys/bookmaker coverage before scheduling requests.
- Preserve provider event ID, sport key, commence time, bookmaker key/title, market key, outcome name/point/price and each quote timestamp. Never join on team names alone.

### Historical odds and credit protection

- Historical odds snapshots are available from 2020-06-06; cadence is 10 minutes initially and 5 minutes from September 2022.
- Historical odds endpoints are paid-plan only.
- Documented historical odds cost: 10 credits per region per market. Cost therefore grows multiplicatively with regions and markets.
- Historical event odds are also available per event; use the bulk historical endpoint for featured markets where it is more cost-effective.
- Every response includes `x-requests-remaining`, `x-requests-used` and `x-requests-last` usage headers.

**Account gate:** Actual subscription, available monthly credits, sport/competition coverage, historical endpoint access and BTTS market availability remain unverified. No historical odds crawl is authorized until a strict credit budget and reserve are recorded. Use a small, explicitly budgeted sample for coverage verification only after account access is confirmed.

## 3. Adapter implementation rules

1. Provider clients implement only transport, parsing and provider-native record envelopes. They do not resolve canonical team/competition/fixture identity or calculate predictions.
2. Preserve exact response bytes and SHA-256, provider record IDs, fixture IDs, competition IDs, timestamps, pagination metadata, endpoint and request ID.
3. Treat provider 301 canonical-ID redirects as explicit provider identity events. Do not silently discard old IDs.
4. Pagination is bounded by an explicit maximum page count and request budget. Stop on malformed pagination, repeated cursor/page, plan error or quota exhaustion.
5. Retry only transient network/5xx/429 responses with bounded backoff and Retry-After. Never retry authentication, insufficient-plan, invalid-request or permission errors.
6. Cache successful responses with provider/data-class TTLs. Never use cache freshness as proof of account history depth or market coverage.
7. Do not make one API request per fixture when a bulk league/date endpoint exists.
8. Odds matching and canonical fixture reconciliation remain separate V2 services. Odds from a provider response must not be attached to a canonical fixture until identity is verified.
9. Record quota units exactly as provider defines them: request-window units for 5Dollar, credits for The Odds API. Never compare unlike units.
10. Provider adapters remain inactive until the account capability, rights, quota, storage and operational stop-condition gates all pass.

## 4. Current activation status

| Provider | Intended use | Public schema | Account access | Quota evidence | Runtime status |
|---|---|---|---|---|---|
| 5DollarFootballAPI | Primary fixtures/results | Reviewed | Not verified | Public limits known; user's actual plan unknown | DISABLED |
| The Odds API | Supplementary live/historical odds | Reviewed | Not verified | Historical cost formula known; user's credits unknown | DISABLED |
| OddsPapi | Optional independent odds | Not reviewed in this milestone | Not verified | Unknown | DISABLED |
| API-Football/API-Sports | Legacy only | Not required | Suspended | Not applicable | EXCLUDED; never access its key |

No API credentials or account values were accessed in this research milestone.


## 5. V2 implementation checkpoint

Offline response parsers now exist at:
- `veltrix_v2/ingestion/providers/five_dollar.py`
- `veltrix_v2/ingestion/providers/the_odds_api.py`

They parse response bodies supplied by a future transport adapter. They do not issue HTTP requests, load credentials, reserve quota or persist data. Their output uses the provider-neutral `RawProviderRecord` envelope and retains the exact raw response bytes. The 5Dollar parser also preserves source team IDs and league redirect events; The Odds API parser captures quota headers and only records market keys actually present in the response.

The account and runtime status table above remains unchanged: both providers are DISABLED pending account-specific verification and measured budgets.


## 6. Verified 5Dollar fixture schema details (official documentation, 2026-11-06)

The V2 fixture parser and request builder are aligned to the current official endpoint descriptions:

- `GET /v1/fixtures` is a UTC window endpoint with a **maximum 24-hour span**; `start_time` is inclusive and `end_time` exclusive. It supports a league filter, and defaults `esports=false` for real football. The adapter always sends explicit window bounds and blocks esoccer.
- `GET /v1/leagues/{id}/fixtures` is the historical league/season entry point. It accepts a season or an explicit kickoff window without the 24-hour cap. V2 requires one of those bounds; it never requests an unbounded provider default.
- `GET /v1/teams/{id}/fixtures` returns home/away fixtures and supports an explicit time window without the 24-hour cap. V2 requires the window to be supplied.
- Fixture response identity fields are `id`, `league.id`, `teams.home.id`, `teams.away.id`; kickoff is `kickoff_utc` with optional `kickoff_ts`. The typed parser checks the timestamp pair and preserves all original IDs.
- Fixture statuses are `scheduled`, `in_play`, `finished` and `unknown`. The feed does not expose explicit postponed/cancelled statuses; unknown or incomplete result rows are never treated as settled.
- Published history depth is 3 months on Free, 12 months on Pro and back to 2014 on Ultra. This is a published plan description only; the connected account plan remains unverified.

Official references:
- [List fixtures](https://5dollarfootballapi.com/docs/fixtures)
- [League fixtures](https://5dollarfootballapi.com/docs/league-fixtures)
- [Team fixtures](https://5dollarfootballapi.com/docs/team-fixtures)
- [Fixture response](https://5dollarfootballapi.com/docs/fixture)
- [API overview and fixture status](https://5dollarfootballapi.com/docs)

The request adapter still has no enabled account instance. No credential or provider request was used to produce this schema alignment.
