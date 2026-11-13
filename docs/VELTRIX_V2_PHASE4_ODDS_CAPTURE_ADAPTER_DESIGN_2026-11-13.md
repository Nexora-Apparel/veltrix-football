# VELTRIX FOOTBALL 2.0 — The Odds API Prospective Capture Design

**Assessment date:** 2026-11-13  
**Status:** Design only; no provider requests, ingestion, schedule, model use or value-bet activation authorized by this document  
**Base:** Phase 3 + merged Phase 4 capture schema

## 1. Decision and activation boundary

The Odds API remains the approved supplemental source for prospective bookmaker-price benchmarking. Its current v4 documentation exposes provider-created market quote timestamps and usage-credit headers. The adapter must be independent of all legacy prediction, odds-selection and fallback logic.

**Credential:** repository secret `THE_ODDS_API_KEY`. Never expose it to the browser, logs, request fingerprints, artifacts or database request metadata. Prefer the documented `x-api-key` request header over a query-string key.

**Rights gate:** Phase 1 documents that current Terms permit storage, derived values, commercial display and statistical/ML training while prohibiting raw-feed resale. The accepted Terms version depends on the account's acceptance history. The dedicated staging `source_approvals` table currently contains the 5Dollar approval only; it has no The Odds API approval row. Therefore, the adapter remains disabled until the account's accepted Terms version is evidenced and a scoped The Odds API approval is recorded. Do not infer acceptance from the public current Terms page.

**Budget gate:** the account's available monthly credit balance and permitted capture budget are not currently recorded in the V2 evidence store. No odds endpoint may be called until a numeric monthly and per-run credit cap is configured.

## 2. Supported v4 endpoint plan

Base host: `https://api.the-odds-api.com`

| Need | Endpoint | Contract |
|---|---|---|
| Discover active soccer sport keys | `GET /v4/sports` | No usage credits; cache the result and do not poll frequently. |
| Bulk 1X2 and totals quotes | `GET /v4/sports/{sport}/odds` | Request `markets=h2h,totals`, one approved region, decimal prices and ISO timestamps. For soccer, `h2h` includes the draw. |
| Discover event identities | `GET /v4/sports/{sport}/events` | No usage credits; use event IDs and kickoff metadata for reviewed crosswalks. |
| BTTS quotes | `GET /v4/sports/{sport}/events/{eventId}/odds` | Event-specific `markets=btts`; one event per request. Coverage is bookmaker/sport dependent and must be measured. |

Important coverage constraints:
- The featured `h2h` market includes the draw for soccer; do not spend credits requesting `h2h_3_way` unless a measured bookmaker-specific reason requires it.
- The featured `totals` market is documented as mainly available for US sports/bookmakers. Soccer totals coverage must be proven for the selected region/bookmakers; a missing market remains missing.
- BTTS is an additional soccer market accessed one event at a time. A successful endpoint response does not establish that every bookmaker or fixture has BTTS.
- The market-level `last_update` is the quote timestamp. The bookmaker-level `last_update` is deprecated and must be ignored.
- Historical odds endpoints are paid-plan snapshots (10-minute cadence historically, 5-minute cadence since September 2022). They are outside this prospective capture design; do not call them.

## 3. Credit model and hard budget controls

The documented current-odds cost is one credit per requested market per region. Event-odds cost is one credit per unique market returned per region. The `/sports` and `/events` discovery endpoints do not consume odds credits. Every response's `x-requests-used`, `x-requests-remaining` and `x-requests-last` headers must be archived as safe quota evidence.

Illustrative one-region daily plan for seven distinct sport keys:
- Bulk `h2h,totals`: 2 credits × 7 sport keys = 14 credits/day.
- BTTS on three selected events: up to 3 additional credits/day.
- Indicative total: up to 17 credits/day, approximately 510 credits per 30-day month.
- BTTS on all 25 fixtures instead: up to 25 additional credits/day, approximately 1,170 credits per 30-day month including the bulk calls.

These are planning estimates, not a claim about the user's current plan or actual response cost. Actual costs depend on unique markets returned, regions/bookmakers and the number of sport keys. Before activation:
1. Record the account's actual monthly credit allowance and current remaining balance.
2. Set a hard per-run and monthly cap below the available allowance, reserving capacity for retries and verification.
3. Estimate cost before every request; refuse the request if it would exceed the remaining budget.
4. Capture quota headers after each response and reconcile estimated vs provider-reported usage.
5. Use bounded retries only for transient network/429 errors; never retry authentication, entitlement or exhausted-credit errors automatically.
6. Never use a paid historical endpoint in the prospective worker.

## 4. Identity and capture pipeline

1. Freeze the V2 fixture universe from the qualified 5Dollar fixture lane and assign a UTC prediction cutoff per fixture.
2. Discover sport keys/events without spending odds credits. Do not map by team names alone.
3. Resolve each Odds API event to the canonical fixture through an evidence-backed `FIXTURE` crosswalk. Non-exact mappings require a reviewed decision and immutable evidence; ambiguous matches are quarantined.
4. Create a capture manifest and one request-attempt record per HTTP request. Store redacted request parameters and a canonical request fingerprint; never store the API key.
5. Archive exact response bytes and SHA-256 before parsing. Preserve safe response headers, including quota counters.
6. Parse one observation per bookmaker × market × selection × line. Preserve bookmaker ID, market key, selection name, decimal price, point/total line and provider event ID.
7. Store market-level `last_update` as `source_published_at`, with raw timestamp and `source_timestamp_basis='provider_timestamp'`. Store VELTRIX receipt time separately as `retrieved_at`; do not substitute it for provider quote time.
8. A missing, invalid or timezone-naive market timestamp is retained as evidence but is ineligible for point-in-time use. A quote published after the frozen cutoff is rejected.
9. Resolve the source approval at actual downstream-use time. Rights approval is independent of historical timestamp eligibility.
10. Freeze selected feature/benchmark links and their hashes. Later corrections create new observations; never update old quote values.

## 5. Coverage and benchmark accounting

The declared universe must be fixed before measuring coverage: fixture × selected bookmaker × market × line/period. Report separately:
- fixture not returned by the provider;
- bookmaker absent;
- market absent;
- selection/line absent;
- quote present but timestamp absent or invalid;
- quote timestamp after cutoff;
- identity mapping ambiguous;
- rights not approved.

Do not remove missing rows from the denominator. The 98% timestamp-coverage gate must be measured over the predeclared eligible universe, with source and bookmaker coverage shown separately. Opening, intermediate and closing quotes are separate observations. Closing price is not available at an earlier prediction cutoff.

## 6. Required parser and planner tests

- Soccer `h2h` preserves home, draw and away outcomes.
- `totals` preserves over/under, numeric point and bookmaker identity.
- Event-level `btts` preserves Yes/No outcomes.
- Market-level `last_update` is used; deprecated bookmaker-level timestamp is ignored.
- Missing, malformed, naive and post-cutoff timestamps fail closed.
- Raw bytes hash matches archived bytes; request and response lineage is complete.
- API key is sent only in a header and never appears in URL, request fingerprint, logs or artifacts.
- One region × two bulk markets costs two credits per sport request; event BTTS cost is estimated independently.
- Budget exhaustion prevents the request before network I/O; 429 and exhausted-credit responses cannot cause unbounded retries.
- Ambiguous event-to-fixture mappings are quarantined.
- Duplicate responses do not create duplicate quote versions; revisions remain append-only.

## 7. Explicit non-goals

This design does not:
- activate The Odds API requests or spend credits;
- assert the user's accepted Terms version or monthly allowance;
- infer bookmaker coverage from the public market catalogue;
- use historical paid odds endpoints;
- reuse legacy model, probability, feature or odds-selection code;
- train models, calculate value bets, publish predictions, activate Telegram or enable scheduling.

## 8. Official references

- [The Odds API v4 documentation](https://the-odds-api.com/liveapi/guides/v4/)
- [Featured and additional market definitions](https://the-odds-api.com/sports-odds-data/betting-markets.html)
- [API error and quota guidance](https://the-odds-api.com/liveapi/guides/v4/api-error-codes.html)
- [Terms and Conditions](https://the-odds-api.com/terms-and-conditions.html)
