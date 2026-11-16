# VELTRIX V2 — The Odds API one-event market verification runbook
Date: 2026-11-15
Status: READY FOR BOUNDED RESEARCH PROBE SUBJECT TO FRESH QUOTA PREFLIGHT

## Objective

Measure actual bookmaker coverage and market availability for one upcoming fixture already admitted into the new V2 prospective forecast series, across the four approved competitions represented in that series (England Premier League, Spain La Liga, Italy Serie A and France Ligue 1). Preserve source quote timestamps separately from retrieval timestamps and assess whether the returned odds data adds measurable value to prediction research (market baselines, calibration comparisons, closing-line research and odds coverage). This is a bounded research probe for the personal-use VELTRIX project.

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

- The latest no-credit sports-catalogue probe returned HTTP 200, all five approved soccer keys, `x-requests-used=226`, `x-requests-remaining=274` and `x-requests-last=0` at 2026-11-16T00:18:36Z. This is historical evidence only; the live probe refreshes quota immediately before any odds request.
- The first exact-match pass over the EPL fixtures found no exact provider event; it stopped before the odds endpoint and consumed zero odds credits.
- The next pass searches only the seven already-admitted V2 forecast fixtures across their four represented, already-approved competitions. It does not use aliases or fuzzy matching.
- The staging database still contains zero event-odds responses and zero timestamped `odds_quote_observations`.
- A fresh no-credit quota/access observation is required immediately before the single credit-consuming request. Commercial billing documentation and monthly allowance proof are not required.

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
