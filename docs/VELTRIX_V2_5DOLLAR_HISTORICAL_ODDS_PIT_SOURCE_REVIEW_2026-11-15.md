# VELTRIX FOOTBALL 2.0 — 5DollarFootballAPI historical odds PIT source review

Review date: 2026-11-15.

## Rights basis

Provider Terms (October 2026): https://5dollarfootballapi.com/terms

The Terms permit data use in models and internal tools, caching/storing responses, and display in user-facing products, while prohibiting redistribution of raw data as a competing feed. Free/Community/Education public-facing products require attribution. The planned use is private model research and internal storage; no raw-feed redistribution.

## Timestamped historical data

Official endpoint: GET /v1/fixtures/{id}/odds/history?market=1x2

The provider documents full pre-match and in-play price ticks, oldest first, each with a UTC recorded_at timestamp, score state, line and prices. Ticks can therefore be reconstructed strictly as-of a historical forecast cutoff. Pre-match features must exclude any in-play tick and any tick at or after kickoff. Null/suspended ticks are preserved as evidence but never converted into prices.

The endpoint requires Ultra. Free and Pro plans receive HTTP 403 insufficient_plan. The provider documents history windows of three months on Free, twelve months on Pro and complete supported history back to 2014 on Ultra. Actual season/market coverage varies by competition.

## Existing approval gap

The staging rights approval approval-5dollar-community-fixture-result-2026-11 is for fixture_result; it does not explicitly authorize odds_quote. The source Terms support model training and evaluation, but the rights engine requires exact data-type and permitted-purpose records. A separate odds_quote approval must explicitly include COLLECTION, STORAGE, MODEL_TRAINING and BENCHMARKING, with competition/season scope, terms version, evidence URI/hash and append-only approval event.

## Current account status and decision

The user's account was previously verified as Free. Full tick-history access is therefore unavailable under the current plan. No historical odds request, paid subscription change, or database rights mutation was performed.

**Disposition: BLOCKED.** The provider is a strong rights-compatible PIT odds candidate, but acquisition cannot begin until Ultra entitlement and the separate odds_quote approval are verified. Existing fixture-result rows remain non-PIT for feature reconstruction; do not fabricate their publication times.


## 2X. Community Access opening 1X2 quote — timestamped subset

The provider's per-fixture odds endpoint is available on Free and Community Access. Its 1X2 opening object carries home/draw/away prices and an explicit UTC opened_at timestamp. That timestamp is a valid point-in-time quote time when it is timezone-aware, no later than retrieval, and strictly before kickoff.

The Community Access 12-month dataset can therefore supply one timestamped Bet365 1X2 opening quote per fixture without Ultra. This is not full odds tick history:
- closing and in-play snapshots in the fixture response do not expose their own quote timestamps and must not be treated as timestamped observations;
- no CLV or price-movement path can be reconstructed from opening-only data;
- the 1X2 benchmark cutoff must be the quote's opened_at time, not an assumed later 06:00 report time;
- quote coverage must be measured per fixture and must reach the certification target; do not infer 98% from the provider's general coverage claims.

An offline parser was added for this timestamped opening quote. It ignores closing/in-play values, preserves the source opened_at separately from retrieval time, and rejects missing/naive timestamps, malformed prices, and quotes at or after kickoff. It is not yet connected to live collection or staging persistence.

This gives Stage 2 a viable no-cost 1X2 PIT acquisition route once the separate Community Access credential is added. It does not solve historical team-form result availability or full CLV/tick-history coverage.
