# VELTRIX V2 — The Odds API one-event market verification runbook
Date: 2026-11-15
Status: READY FOR BOUNDED RESEARCH PROBE SUBJECT TO FRESH QUOTA PREFLIGHT

## Objective

Measure actual bookmaker coverage and market availability for exactly one upcoming England Premier League fixture already admitted into the new V2 prospective forecast series. Do not select a fixture from Spain La Liga, Germany Bundesliga, Italy Serie A or France Ligue 1. Preserve source quote timestamps separately from retrieval timestamps and assess whether the returned odds data adds measurable value to prediction research (market baselines, calibration comparisons, closing-line research and odds coverage). This is a bounded research probe for the personal-use VELTRIX project.

This probe does not activate recurring odds collection, model training on its own, prediction publication, Telegram delivery or value betting. It is not a commercial billing or subscription verification exercise.

## Fixed probe envelope

- Provider: The Odds API v4
- Sport key: selected dynamically from the four forecast competitions, and must be present in the fresh no-credit sports catalogue response
- Event count: exactly 1 upcoming event
- Region: `uk`
- Markets: `h2h`, `totals`, `btts`
- Maximum estimated spend: 3 credits (1 region × 3 markets)
- Provider request cap: 1 credit-consuming request
- Attempts: 1; no automatic retry
- Timeout: 15 seconds
- Persistence: staging only; exact raw response bytes, SHA-256, request/retrieval timestamps, allowlisted quota headers and parsed market observations
- Publication: disabled
- Telegram: disabled

The provider documents live odds cost as one credit per region per market. Its event-odds response exposes market-level `last_update`; that is the source timestamp for the quote, distinct from our `retrieved_at`. The `btts` market is an additional market and coverage is limited by sport and bookmaker. See:
- https://the-odds-api.com/liveapi/guides/v4/
- https://the-odds-api.com/sports-odds-data/betting-markets.html

## Preflight — before any credit-consuming request

1. Re-read the active The Odds API source approval and status events from the staging database. Confirm collection and storage rights for the exact competition, region and markets. Personal-use status does not waive provider terms.
2. Refresh `GET /v4/sports/?all=true`. Require HTTP 200, all three quota headers and `x-requests-last=0`. Persist the exact response and retrieval timestamp. This is a no-credit access/quota observation.
3. Confirm the observed remaining quota is sufficient for the capped request (at least 3 credits) and record the observation time, response hash and quota headers. Do not infer a monthly allowance or billing period from `used + remaining`; neither is required for this research probe.
4. Set an immutable per-run guard: maximum 3 credits, request-count cap exactly 1, no retries, timeout 15 seconds, staging-only persistence. The guard is a usage-safety limit, not a model-quality gate. Do not require invoices, billing documents, commercial account evidence, proof of a business subscription, billing-period records or monthly allowance paperwork.
5. Load only the seven upcoming fixtures already recorded under `veltrix-openplay-xg-poisson-v1`. Query the zero-credit `/v4/sports/{sportKey}/events` endpoint for each competition represented by those fixtures. Require exact normalized home/away labels and kickoff within 60 seconds. Choose the earliest exact match deterministically. If no exact match exists, stop before the odds endpoint and preserve only sanitized kickoff-only candidates for later alias review.
6. Build and persist the immutable request manifest. Record the expected maximum cost and exact request parameters before dispatch.
7. Require a single attempt, no retry, no emergency stop, authorized operator dispatch and successful prior-attempt reconciliation.

If any access, rights, event-identity or quota-safety check fails, stop before the odds request. Do not invent quota values, assume provider access, or retry automatically. Continue independent 5DollarFootballAPI collection and model evaluation.

## Credit-consuming request

Use the event-specific endpoint:

```
GET /v4/sports/{sportKey}/events/{eventId}/odds
    ?regions=uk
    &markets=h2h,totals,btts
    &dateFormat=iso
    &oddsFormat=decimal
```

Send the API key in the `x-api-key` header, not in a logged URL. Capture the raw response bytes and only the allowlisted quota headers.

## Acceptance checks

- HTTP status is 200 and the response event ID equals the selected event ID.
- Report actual returned bookmaker keys and actual returned market keys; requested markets are not presumed available.
- Every retained quote has a valid decimal price and a timezone-aware market-level `last_update`.
- Preserve `last_update` as source quote time and `retrieved_at` as collection time. Never substitute one for the other.
- Preserve bookmaker identity, market key, outcome, price, point/line where applicable, event ID and request parameters.
- Independently recompute raw-response SHA-256 from stored bytes.
- Reconcile `x-requests-used`, `x-requests-remaining` and `x-requests-last` against the fresh preflight observation and the 3-credit/one-request guard. Any missing, malformed or over-cap result becomes an unresolved/overrun event; never retry automatically.
- If no bookmaker or no requested market is returned, record the negative coverage result. Do not report entitlement as verified merely because the endpoint returned HTTP 200.
- Quantify analytical usefulness: bookmaker count, market availability by market, timestamp completeness/freshness, price/outcome coverage, and whether the data supports an odds baseline or closing-line comparison. Do not claim predictive value without out-of-sample evaluation.
- Do not use historical odds endpoints for this probe. Historical odds have a materially higher documented credit cost.

## Current verified state

- The last recorded no-credit sports-catalogue probe returned HTTP 200, all five approved soccer keys, `x-requests-used=226`, `x-requests-remaining=274` and `x-requests-last=0` at 2026-11-16T00:18:36Z. This is historical evidence only.
- The subsequent accepted event-odds capture, run [43780096811](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43780096811), selected Como vs Cagliari (Italy Serie A): 95 quote rows, 95/95 provider timestamps, 21 bookmakers, h2h 63 / btts 22 / totals 10, one request and 3 credits. Quota moved from 226 used / 274 remaining to 229 used / 271 remaining. Persisted response 1297, manifest 160, request 888, fixture crosswalk 3169 and source observation 433133. Raw response SHA-256: `3271ea3f90613ff9c065a525dc73625af84a4b52fef5a16b54e8a10d49eeabf5`.
- Como–Cagliari is an early Italy Serie A snapshot, not a closing archive and not the currently authorized EPL-only probe. Six other admitted forecast fixtures remain without Odds API quotes.
- The earlier exact-match discovery pass over EPL fixtures found no exact provider event and stopped before the odds endpoint. The next probe is now strictly restricted to upcoming V2 forecasts in England Premier League (`soccer_epl`); it must not fall back to another competition or use aliases/fuzzy matching. If no exact future EPL event is found, stop before the odds endpoint.
- Current staging table counts cannot be re-read: Neon staging returns HTTP 402. The existing Como–Cagliari capture remains the last accepted Odds API event evidence; no new EPL event request was made in this monitor pass.
- A new no-credit quota/access observation is mandatory immediately before any future credit-consuming request and must show at least 3 credits remaining. Enforce one credit-consuming request maximum, 3-credit cap, no retries, and staging-only persistence. Do not infer a monthly allowance. Commercial billing documentation and monthly allowance proof are not required.

## Release boundary

Passing this probe establishes only the returned bookmaker/market coverage for this one event and region at the captured time. It does not certify the odds provider across all competitions, establish 98% timestamped odds coverage, certify any model or authorize publication. Use the captured observations in prediction research only after provenance and timestamp checks. All prediction and publication release gates remain independently fail-closed.


## Governing project policy

This runbook is subordinate to the personal-use and separated-control policy in:
- `docs/PROVIDER_PLAN_CORRECTION.md`
- `docs/VELTRIX_V2_ACCURACY_AND_MODEL_STANDARD_2026-11-11.md`
- `docs/VELTRIX_V2_REPORT_TELEGRAM_RELEASE_CONTRACT_2026-11-14.md`

No commercial monetisation or billing-document requirement may be reintroduced as a model-quality, certification or publication gate. Provider terms, endpoint entitlement, quota and the bounded one-request/3-credit safety guard remain applicable.


## Historical odds are a separate, higher-cost operation

This runbook's one-request / three-credit guard applies only to the **live** event-odds endpoint. It does not authorize or budget a historical snapshot request.

The provider's official historical-data documentation states:
- Historical odds snapshots are available only on paid usage plans; historical coverage discovery is available on all plans.
- Historical coverage discovery endpoints each cost 1 credit per request.
- The historical odds endpoint costs 10 credits per region per market. The historical event-odds endpoint costs 10 credits per region per market per event.
- A one-event, one-UK-region request for h2h, totals, and btts therefore has a documented maximum endpoint cost of **30 credits**, before any separately billed coverage-discovery requests.
- Historical responses include a snapshot timestamp and market-level last_update; both must be retained and checked against the prediction cutoff.

Official source: https://the-odds-api.com/historical-odds-data/ (accessed 2026-11-15).

No historical request is authorized by the three-credit live-probe cap. Historical collection requires a fresh quota preflight, confirmed paid-plan historical endpoint entitlement, a separate immutable credit reservation sized to the exact request, and an explicit operator-run workflow. Until then, the historical odds capture path remains disabled.


## 2026-11-16 — EPL-only scope lock and execution blockers

- The owner’s current authorization is for one eligible future EPL event only, UK region, markets `h2h`, `totals`, `btts`, one credit-consuming request, maximum 3 credits, one attempt and no retries.
- The collector now filters eligible V2 forecasts to `competition=England Premier League` and `sport_key=soccer_epl` before event discovery. It returns `BLOCKED_NO_UPCOMING_EPL_V2_FORECAST_FIXTURES` when no eligible future EPL V2 forecast exists; it never falls back to another competition.
- The connected GitHub integration exposes no workflow-dispatch action. The Neon staging branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`, returns HTTP 402 for database reads/writes. No new preflight or odds request is attempted until the required staging evidence can be persisted and a fresh quota observation is available.
- This is a provider/platform access guard, not a model-quality criterion. No invoice, commercial subscription evidence or monthly allowance paperwork is required.
