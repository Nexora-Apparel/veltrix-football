# VELTRIX V2 — The Odds API one-event market verification runbook
Date: 2026-11-15
Status: BLOCKED pending current account billing evidence and bounded dispatch authorization

## Objective

Verify actual bookmaker coverage for one upcoming event in the configured UK region and capture trustworthy market-level timestamps. This is a verification-only probe. It does not activate recurring odds collection, model training, prediction publication, Telegram delivery, or value betting.

## Fixed probe envelope

- Provider: The Odds API v4
- Sport key: `soccer_epl` (must be returned by the current no-credit sports catalogue response)
- Event count: exactly 1 upcoming event
- Region: `uk`
- Markets: `h2h`, `totals`, `btts`
- Credit estimate: at most 3 credits (1 region × 3 markets)
- Provider request cap: 1 credit-consuming request
- Attempts: 1; no automatic retry
- Timeout: 15 seconds
- Persistence: staging only; exact raw response bytes, SHA-256, request/retrieval timestamps, allowlisted quota headers and parsed market observations
- Publication: disabled
- Telegram: disabled

The provider documents live odds cost as one credit per region per market. Its event-odds response exposes market-level `last_update`; that is the source timestamp for the quote, distinct from our `retrieved_at`. The `btts` market is an additional market and coverage is limited by sport and bookmaker. See:
- https://the-odds-api.com/liveapi/guides/v4/
- https://the-odds-api.com/sports-odds-data/betting-markets.html

## Mandatory preflight — before any credit-consuming request

1. Re-read the active The Odds API source approval and status events from the staging database. Confirm collection and storage rights for the exact competition, region and markets.
2. Refresh `GET /v4/sports/?all=true`. Require HTTP 200, all three quota headers, and `x-requests-last=0`. Persist the exact response and retrieval timestamp.
3. Obtain current provider-account evidence for plan name, billing-period start/end, monthly allowance and current remaining credits. Do not infer the plan or allowance from `used + remaining`.
4. Record an immutable budget snapshot with:
   - monthly hard cap no greater than the documented allowance;
   - per-run hard cap exactly 3 credits or lower;
   - request-count cap exactly 1;
   - evidence URI and SHA-256 for provider billing/quota evidence;
   - short validity window ending before the dispatch.
5. Require the current provider remaining balance to be at least 3 and ensure the request fits both the monthly and per-run caps.
6. Select one future event from the zero-credit `/v4/sports/soccer_epl/events` endpoint. Confirm the event identity, competition, teams and kickoff are valid and kickoff is after the prediction cutoff.
7. Build and persist the immutable request manifest. Commit the exact credit reservation before dispatch. Require the reservation fingerprint to match the manifest.
8. Require a single attempt, no retry, no emergency stop, approved operator dispatch and successful prior-attempt reconciliation.

If any item is missing, stop before the odds request. No fallback budget, guessed billing period, or implicit retry is permitted.

## Credit-consuming request

Use the event-specific endpoint:

```
GET /v4/sports/soccer_epl/events/{eventId}/odds
    ?regions=uk
    &markets=h2h,totals,btts
    &dateFormat=iso
    &oddsFormat=decimal
```

Send the API key in the `x-api-key` header, not in a logged URL. Capture the raw response bytes and only the allowlisted quota headers.

## Acceptance checks

- HTTP status is 200 and the response event ID equals the selected event ID.
- At least one bookmaker in the UK region is returned.
- Report actual returned bookmaker keys and actual returned market keys; requested markets are not presumed available.
- Every retained quote has a valid decimal price and a timezone-aware market-level `last_update`.
- Preserve `last_update` as source-published time and `retrieved_at` as collection time. Never substitute one for the other.
- Independently recompute raw-response SHA-256 from stored bytes.
- Reconcile `x-requests-used`, `x-requests-remaining` and `x-requests-last` against the preflight snapshot and reservation. Any missing, malformed or over-cap result becomes an unresolved/overrun event; never retry automatically.
- If no bookmaker or no requested market is returned, record the negative coverage result. Do not report entitlement as verified merely because the endpoint returned HTTP 200.
- Do not use historical odds endpoints for this probe. Historical odds have a materially higher documented credit cost.

## Current verified state

- The persisted no-credit sports-catalogue probe returned HTTP 200, all five configured soccer keys, `x-requests-used=205`, `x-requests-remaining=295`, and `x-requests-last=0` at 2026-11-14T23:12:29.755Z.
- The staging database currently contains one The Odds API response: the sports catalogue. It contains zero `/odds` responses and zero event-odds responses.
- Account plan, billing period, monthly allowance and operational hard caps are not established.
- No market request has been sent. No timestamped bookmaker quote has been captured.

## Release boundary

Passing this probe establishes only the returned bookmaker/market coverage for this one event and region at the captured time. It does not certify the odds provider across all five competitions, establish 98% coverage, certify any model, or authorize publication. All release gates remain fail-closed.
