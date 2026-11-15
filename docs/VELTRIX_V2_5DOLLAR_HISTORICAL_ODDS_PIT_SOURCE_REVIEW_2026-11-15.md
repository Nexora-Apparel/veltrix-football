# VELTRIX FOOTBALL 2.0 — 5DollarFootballAPI historical odds PIT source review

Review date: 2026-11-15.

## Rights basis

Provider Terms (October 2026): https://5dollarfootballapi.com/terms

The Terms permit data use in models and internal tools, caching/storing responses, and display in user-facing products, while prohibiting redistribution of raw data as a competing feed. Free/Community/Education public-facing products require attribution. The planned use is private model research and internal storage; no raw-feed redistribution.

## Timestamped historical data

Official endpoint: GET /v1/fixtures/{id}/odds/history?market=1x2

The provider documents full pre-match and in-play price ticks, oldest first, each with a UTC recorded_at timestamp, score state, line and prices. Ticks can therefore be reconstructed strictly as-of a historical forecast cutoff. Pre-match features must exclude any in-play tick and any tick at or after kickoff. Null/suspended ticks are preserved as evidence but never converted into prices.

The endpoint requires Ultra. Free and Pro plans receive HTTP 403 insufficient_plan. The provider documents history windows of three months on Free, twelve months on Pro and complete supported history back to 2014 on Ultra. Actual season/market coverage varies by competition.

## Approval state — 2026-11-15

A separate non-commercial staging approval is now recorded:
- Approval ID: `approval-5dollar-community-odds-quote-noncommercial-2026-11-15`
- Data type: `odds_quote`; permitted uses include COLLECTION, STORAGE, MODEL_TRAINING and BENCHMARKING.
- Competition scope: the seven already-approved canonical competition IDs.
- `commercial_use_allowed=false`; raw redistribution prohibited.
- Terms version: October 2026; evidence hash is the existing legal terms review hash.
- An append-only `APPROVED` status event was recorded.

The project owner has separately imposed a project-wide non-commercial rule. VELTRIX will not monetise any source data, regardless of broader permissions in upstream provider terms.

## Current account status and decision

The account's Free/Community opening 1X2 quote route is now implemented as a manual, staging-only capture workflow. It uses the provider's per-fixture endpoint and only the Bet365 1X2 opening object with its explicit `opened_at` timestamp. Closing and in-play values remain excluded because their individual source timestamps are absent.

The full tick-history endpoint remains unavailable on the current Free plan and requires Ultra. No paid historical tick request or subscription change has been made. The new opening-odds workflow is capped at 25 fixtures per run, 90-day lookback, no retries, 3.1-second pacing, and no schedule. No opening quote has yet been acquired by that workflow.

**Disposition:** opening 1X2 quote acquisition is technically ready for a bounded manual run; full tick history remains blocked by plan entitlement. Existing fixture-result rows remain non-PIT for pre-match feature reconstruction; do not fabricate their publication times.


## 2X. Community Access opening 1X2 quote — timestamped subset

The provider's per-fixture odds endpoint is available on Free and Community Access. Its 1X2 opening object carries home/draw/away prices and an explicit UTC opened_at timestamp. That timestamp is a valid point-in-time quote time when it is timezone-aware, no later than retrieval, and strictly before kickoff.

The Community Access 12-month dataset can therefore supply one timestamped Bet365 1X2 opening quote per fixture without Ultra. This is not full odds tick history:
- closing and in-play snapshots in the fixture response do not expose their own quote timestamps and must not be treated as timestamped observations;
- no CLV or price-movement path can be reconstructed from opening-only data;
- the 1X2 benchmark cutoff must be the quote's opened_at time, not an assumed later 06:00 report time;
- quote coverage must be measured per fixture and must reach the certification target; do not infer 98% from the provider's general coverage claims.

An offline parser was added for this timestamped opening quote. It ignores closing/in-play values, preserves the source opened_at separately from retrieval time, and rejects missing/naive timestamps, malformed prices, and quotes at or after kickoff. It is not yet connected to live collection or staging persistence.

This gives Stage 2 a viable no-cost 1X2 PIT acquisition route once the separate Community Access credential is added. The offline parser and regression tests now pass on integration commit e30d6d870da8cebc61eab483e7fcf587fa72ffc8. It does not solve historical team-form result availability or full CLV/tick-history coverage, and no live data has yet been acquired.
