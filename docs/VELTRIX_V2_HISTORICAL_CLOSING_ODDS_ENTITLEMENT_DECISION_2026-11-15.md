# VELTRIX FOOTBALL 2.0 — Historical and closing-odds source decision

**Decision date:** 2026-11-15  
**Scope:** Stage 2 historical / closing-odds evidence  
**Project use:** Internal, non-commercial research only  
**Disposition:** ALTERNATIVE IDENTIFIED; ACCOUNT ENTITLEMENT NOT VERIFIED; HISTORICAL ODDS GATE BLOCKED

## 1. Decision summary

No currently evidenced account entitlement provides a usable, timestamped historical closing/tick series for the seven-competition Stage 2 universe.

The acceptable technical alternative is The Odds API V4 historical odds snapshot service, subject to confirmation that the connected account has paid historical-odds access and the required soccer sport-key / UK bookmaker coverage. Its snapshots are point-in-time evidence at the provider's returned snapshot timestamp, not tick-by-tick bookmaker close records. Historical snapshots are documented at 10-minute intervals initially and five-minute intervals from September 2022. The historical endpoint is paid-plan-only; the documented event-level endpoint cost is 10 credits per region per market per event. The aggregate historical sport-odds endpoint has a documented 10-credit cost per region per market per request.

No credit-consuming request was made for this decision. The prior no-credit catalogue probe does not prove historical endpoint entitlement, bookmaker availability, event coverage, or market-level timestamps.

## 2. 5DollarFootballAPI

### Community-access route

GET /v1/fixtures/{id}/odds exposes Bet365 opening, closing and in-play price fields. The opening 1X2 quote includes opened_at (UTC), and the capture workflow stores this as the source publication/availability timestamp. The 325 independently reconciled opening observations are admitted only as opening-price evidence.

The closing and in-play fields in this fixture response do not carry their own timestamped quote history. They cannot establish when the quote was observed, cannot be treated as point-in-time features, and cannot support defensible CLV or price-movement calculations. Do not substitute the fixture's retrieval time, kickoff time, or opening timestamp for a missing closing timestamp.

### Historical tick route

GET /v1/fixtures/{id}/odds/history?market=1x2 provides timestamped price ticks, ordered oldest first, but the provider documentation explicitly requires Ultra or above; Free and Pro receive 403 insufficient_plan. The connected account's Ultra entitlement has not been evidenced. No request has been made to this restricted endpoint.

**Disposition:** retain the Community opening route; formally block tick-history acquisition pending actual Ultra entitlement evidence. No upgrade or paid request is authorized by this decision.

## 3. The Odds API V4 alternative

Official documentation describes:
- Historical odds snapshots from 2020-06-06; 10-minute intervals initially and five-minute intervals from September 2022.
- Historical odds endpoints are available only on paid usage plans.
- Historical event odds can retrieve a single event's odds at a specified timestamp; the endpoint returns the closest snapshot equal to or earlier than the requested time.
- Historical event odds cost 10 credits per region per market per event.
- Historical sport odds cost 10 credits per region per market per request.
- Historical events / markets discovery endpoints can be used to inspect coverage on any plan, at one credit per request, but they do not return odds.

This source is acceptable for **snapshot-based historical odds evidence** if all of the following are proven:
1. Account entitlement permits the historical endpoint.
2. The relevant soccer sport keys map unambiguously to the seven canonical competitions.
3. UK-region bookmaker coverage includes the selected bookmaker(s) and h2h (1X2) market at the requested historical timestamps.
4. The returned snapshot timestamp is retained exactly and is strictly before kickoff for pre-match use.
5. Event identity, bookmaker, market, outcome prices, snapshot time, response hash, retrieval time, and quota headers are preserved.
6. Missing snapshots and bookmaker gaps remain missing; no interpolation or assumed close is permitted.

A five-minute snapshot immediately before kickoff is a defensible **near-close snapshot**, not proof of the bookmaker's exact final closing tick. The project must label it as snapshot-derived and must not claim tick-perfect CLV.

The existing catalogue-only account probe (three /v4/sports/ responses in the earlier audit) is not sufficient to prove any of these conditions. The previously observed no-credit quota headers are historical observations, not a current quota preflight. No credit-consuming probe is authorized here.

## 4. Certification and coverage impact

- Current 5Dollar Community opening observations: 325 / 763 = 42.60% of the frozen 90-day seven-competition fixture universe, subject to the latest independent read-back.
- Opening-only quotes do not establish closing-price coverage.
- 5Dollar tick-history observations: zero.
- The Odds API event-odds responses: zero.
- The Odds API historical-odds responses: zero.
- Timestamped closing / near-close snapshots: zero.
- CLV and price-movement evidence: unavailable.
- The 98% timestamped odds-coverage certification threshold is not met.
- Market certification and value betting remain locked.

The absence of historical/closing evidence does not invalidate the 325 valid opening observations. It limits their use to the explicitly timestamped opening-price context and prevents closing-line benchmarks, CLV evaluation, and any certification gate requiring 98% timestamped odds coverage.

## 5. Required next evidence

Before any The Odds API credit-consuming probe:
- Verify current account historical endpoint entitlement from account/provider evidence.
- Confirm sport-key-to-competition mappings and UK bookmaker/market availability using non-credit documentation or permitted discovery.
- Run a fresh no-credit quota preflight.
- Set a one-request, one-region, one-market hard cap (maximum documented estimate: 10 credits for a historical odds request), no retries, staging-only persistence, and preserve exact response plus quota headers.
- Do not run the probe unless the separate credit cap is explicitly authorized.

Before any 5Dollar tick-history request:
- Obtain evidence that the actual API key/account has Ultra access.
- Revalidate current rights, scope, quota and rate limits.
- Keep the existing no-retry, staging-only and bounded-request controls.

## 6. Formal decision

**Historical/closing odds source decision: BLOCKED — ENTITLEMENT NOT VERIFIED.**

The Odds API V4 is the technically acceptable alternative for timestamped historical snapshots, with a clear distinction between near-close snapshots and exact closing ticks. The 5Dollar Ultra history endpoint remains the direct tick-level source but is not entitled on the evidence currently available. Neither route has been used to collect historical/closing observations.

Stage 2 cannot pass the historical/closing-odds gate or the 98% timestamped odds-coverage requirement on current evidence. Keep model certification, value betting, production publication, Telegram delivery and schedule activation disabled.

## 7. Official provider documentation

- 5Dollar odds history: https://5dollarfootballapi.com/docs/odds-history
- 5Dollar fixture odds and plan history: https://5dollarfootballapi.com/docs
- The Odds API V4 historical odds guide: https://the-odds-api.com/liveapi/guides/v4/
- The Odds API historical data and usage-cost guide: https://the-odds-api.com/historical-odds-data/

## 8. Opening-odds acquisition continuation — 2026-11-15

Eleven additional bounded batches have now been independently reconciled after manifests 109 and 110, bringing manifests 109–121 to 325/325 opening quote observations across 325 distinct fixtures. Each completed batch had 25 requests, 25 responses, 25 PIT-eligible observations, zero duplicates, zero ineligible quotes, fresh Community quota preflight, no retries and no more than 25 fixture requests. Latest verified batch: workflow #43734327570, artifact #14170016337, ZIP SHA-256 `f752a53019de07e1a3b3c23b139fc5edf5f0d20dbe8e3bc2b06ff4912751a559`. The fixed 763-fixture denominator leaves 438 fixtures (57.40%) without a captured opening quote. This progress does not change the historical/closing odds entitlement decision or Stage 2 release gate.
