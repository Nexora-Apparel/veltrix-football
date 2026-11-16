# VELTRIX FOOTBALL 2.0 — Stage 2 Provider and Prospective Evidence Update

**Evidence date:** 2026-11-16 00:15 UTC  
**Branch:** `integration/v2-report-bundle-wiring-20261114`  
**Status:** Staging-only evidence; no release authorization implied.

## 1. 5DollarFootballAPI entitlement — verified without odds-history usage

The isolated status-only workflow completed successfully:

- Workflow: [run 43778306708](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43778306708)
- Request count: exactly 1
- Endpoint called: `GET /v1/status` only
- HTTP 200; response schema valid
- Plan field/value: `data.plan = community`
- Ultra confirmed: `false`
- Rate limit: 300/hour; remaining header: 299
- Usage reported today: 0
- No league, fixture, odds or odds-history requests; no database write, prediction write or Telegram delivery.
- Evidence SHA-256: `9c586e49def7fde463217bca8792f75900cacf51d6a888edc20c9a005ceb9051`
- Raw response SHA-256: `3a185e719c0e8a2b6c71fef0f2241bf846d844f2b345af98aae7157714981781`

**Decision:** Community access is verified; Ultra is not. Do not call `/v1/fixtures/{id}/odds/history`. No upgrade was purchased. Continue historical provider qualification and prospective capture using other already-authorized sources.

## 2. The Odds API account and competition scope — verified at zero credits

The existing no-credit account probe completed successfully:

- Workflow: [run 43778624089](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43778624089)
- Endpoint: `GET /v4/sports/?all=true`
- Request cost: 0 credits
- Returned sports: 187
- All five already-approved competition keys were present:
  - `soccer_epl`
  - `soccer_spain_la_liga`
  - `soccer_germany_bundesliga`
  - `soccer_italy_serie_a`
  - `soccer_france_ligue_one`
- Quota headers: used 226; remaining 274; last request cost 0
- Response SHA-256: `122d317b1bbc057085c10c431a4304286c9dbf04954e342d97c5f84da3319dbb`
- Persisted staging evidence: provider response ID 1293; entitlement observation ID 6.
- Account plan code and exact billing-period dates were not disclosed by this endpoint. No monthly budget snapshot has been activated.
- Existing scoped approval: `approval-the-odds-api-v4-owner-authorized-2026-11-14`; data type `odds_quote`; scope is the five competition keys above; Terms version `2026-08-31`; permitted uses include collection, storage, benchmarking, model training and public display; raw redistribution is prohibited.

The `/v4/sports` and `/v4/sports/{sport}/events` discovery routes are documented as zero-credit. Current `/odds` calls cost one credit per returned market per region. A five-league, one-region, three-market plan would be at most 15 credits, but **no odds request has been dispatched**. The current provider balance is known (274), while the subscription allowance/billing period and a valid immutable budget snapshot are not yet established. The credit-reservation schema requires an evidenced billing period, allowance, hard caps and accepted-Terms evidence; do not invent these values or bypass the reservation ledger.

## 3. Upcoming fixture and PIT feature admission

The 25 upcoming 5Dollar canonical fixtures are present in staging and remain SCHEDULED. Kickoff range begins 18 November 2026.

The verified OpenPlay feature bundle contains 20,178 feature rows, SHA-256 `9ed328dd7c9ae235c47252e32bde0bb06d2a030ec38d151eeda7de264408bdc1`. The current staging feature inventory contains 42 immutable snapshots and 420 feature links across seven target fixtures/cutoffs.

Latest admission workflow: [run 43778306708](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43778306708).

- 25 targets considered.
- 7 targets admitted with complete home/away history and exact competition/team crosswalks.
- Each admitted target has five eligible historical match rows for the home team and five for the away team (10 feature links).
- 18 targets remain quarantined because at least one side lacks eligible OpenPlay team history under the exact resolved identity mappings.
- Latest run reused seven existing snapshots and 70 links; it wrote zero duplicate snapshots/links and passed fresh-connection post-commit verification.
- PIT rule preserves source publication, source availability, VELTRIX recording, rights and crosswalk clocks before the prediction cutoff; historical match date must precede target kickoff date.

## 4. New V2 prospective forecast series

The first successful prospective series is recorded under the independent model version:

`veltrix-openplay-xg-poisson-v1`

- Creator workflow: [run 43775129579](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43775129579)
- Forecast cutoff: `2026-11-15T23:31:35.481497Z`
- Feature snapshot cutoff: `2026-11-15T23:31:28.243079Z`
- Seven predictions appended to the append-only paper ledger; ledger chain and fresh-connection post-commit verification passed.
- Forecasts reference feature snapshot IDs 15–21, each containing five home-team and five away-team historical feature rows.
- Coverage: four competitions (England Premier League, Spain La Liga, Italy Serie A, France Ligue 1).
- The later rerun correctly found all seven already recorded and appended zero duplicates.
- Model artifact SHA-256: `0332c6537e44c189653b4ff74b816beed3c5ab484ee9b205e261c149fef51eda`.

These are PIT-eligible research forecasts, not certified performance evidence. The 18 ineligible fixtures remain excluded. No predictions were published, no Telegram messages sent, no schedules activated, and value betting remains LOCKED.

## 4.1 First prospective timestamped odds capture — committed

The exact-match event discovery was expanded from EPL-only to the seven already-admitted V2 forecast fixtures across their four represented approved competitions. The first exact event match was **Como vs Cagliari**, Italy Serie A.

- Workflow: [run 43780096811](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43780096811)
- Canonical fixture ID: `2508`; provider event ID: `9e8d72c6c27c1667be7b88416a36ca80`
- Kickoff: `2026-11-21T14:00:00Z`
- One event-odds request, one region (UK), markets `h2h`, `totals`, `btts`; no retries.
- Preflight quota: 226 used / 274 remaining / last cost 0.
- Postflight quota headers: 229 used / 271 remaining / last cost 3.
- **3 credits consumed**, within the hard per-event cap; no upgrade or purchase.
- Raw provider response ID 1297; capture manifest 160; capture request 888; resolved exact-name-and-kickoff crosswalk 3169; supporting source observation 433133.
- Raw response SHA-256: `3271ea3f90613ff9c065a525dc73625af84a4b52fef5a16b54e8a10d49eeabf5`.
- **95 quote observations inserted**, 0 duplicates, 0 rejected, 0 missing/invalid timestamps.
  - 1X2: 63 quotes from 21 bookmakers.
  - BTTS: 22 quotes from 11 bookmakers.
  - Totals: 10 quotes from 5 bookmakers.
- Every quote has a provider market timestamp and retrieval timestamp. Source timestamps range from `2026-11-16T00:21:08Z` to `2026-11-16T00:24:01Z`; retrieval was `2026-11-16T00:24:05.284Z`. All 95 were retrieved before the 21 November kickoff.
- The capture state chain reached `COMMITTED`; fresh-connection post-commit verification passed.
- This is an early prospective market snapshot, **not a closing-odds archive**. Closing-line qualification still requires later near-kickoff observations and bookmaker-specific history evidence.

The other six V2 forecast fixtures still have no Odds API quote observations. The 18 fixtures excluded from the first V2 forecast series remain quarantined for incomplete PIT feature history/identity. No schedule was activated.

## 5. Historical odds provider qualification — no purchase

Public documentation reviewed on 2026-11-16:

| Provider | Evidence and limitation | Decision |
|---|---|---|
| The Odds API | Approved prospective quote source for five competitions; current account has 274 credits remaining. Historical snapshots are paid-plan only and carry a 10-credit-per-market-per-region cost. The account's exact billing period/allowance and a valid credit budget snapshot remain unestablished. | Continue prospective qualification; no odds calls until budget reservation evidence is complete. |
| Odds-API.io | Bookmaker-specific closing lines since Dec 2025; its published table includes Brasileirão Série A but not Brazil Série B. Full bulk history is paid; new free keys are paused and the cheapest advertised plan is £49/month. Terms allow analytics/modeling but prohibit raw resale/redistribution; confirm VELTRIX public display scope before use. | Technically promising but does not satisfy the seven-competition scope; no purchase. |
| StrikerAPI | Top-league archive reports 14–22 per-book snapshots per match, with last pre-match capture about 10 minutes before kickoff. Its xG is not as-of (trained across later seasons) and record revisions are not retained. Commercial use of derived outputs is allowed, but raw odds/lines cannot be redistributed. No Brazil coverage established. | Exclude from certified benchmark; do not use provider xG as a PIT feature. |
| SockOdds | Pro-only own-observation history. Published coverage includes several European leagues and MLS, but Brazilian Série A is listed as having no prices delivered; no Série B coverage. | Insufficient competition coverage; no purchase. |
| OddsIntel | Consensus closing prices from 3+ sources, with bookmaker identities and individual bookmaker prices deliberately omitted. | Not suitable for bookmaker-specific CLV certification. |
| OddsRelay | Historical archive begins 17 Oct 2026 and is a UK/Ireland feed; public/business display requires an Enterprise contract. | Insufficient scope/history and licensing fit; no purchase. |
| OddsPapi | Historical response carries bookmaker-grouped `createdAt` price timestamps. Published terms prohibit resale/repackaging/redistribution but do not clearly grant the storage, model-training and public-display rights needed here. | Hold pending written rights clarification; no ingestion or purchase. |

Provider documentation:
- The Odds API: https://the-odds-api.com/liveapi/guides/v4/
- The Odds API usage limits: https://the-odds-api.com/liveapi/guides/v4/api-error-codes.html
- Odds-API.io historical coverage: https://odds-api.io/historical-odds-api
- Odds-API.io Terms: https://odds-api.io/terms
- StrikerAPI timing and rights: https://strikerapi.com/docs/timing-and-rights
- SockOdds history: https://sockodds.com/docs/history/
- SockOdds leagues: https://sockodds.com/leagues/
- OddsIntel closing data: https://data.oddsintel.app/football-closing-odds-api
- OddsRelay historical odds: https://oddsrelay.io/products/historical-odds
- OddsPapi historical odds: https://oddspapi.io/us/docs/get-historical-odds
- OddsPapi Terms: https://oddspapi.io/en/legal/terms

No alternative currently qualifies the full seven-competition bookmaker-specific closing archive with complete timestamp provenance and sufficiently clear rights. Do not substitute consensus-only data for bookmaker-specific closes.

## 6. Settlements, quote capture and certification

Current staging state after the successful workflows:

- `odds_quote_observations`: 95, all timestamped, for one V2 fixture (Como vs Cagliari), 21 bookmakers, all three markets.
- New V2 `PREDICTION` events: 7.
- Legacy `SHADOW_PREDICTION` events: 25, model version `veltrix-results-poisson-v1`; keep separate and do not reuse as V2.
- Settlement events: 0.
- All 25 future target fixtures remain SCHEDULED; no genuine V2 target has finished. Do not settle future or legacy targets as part of this new series.
- Prospective timestamped odds capture is PARTIAL: one of seven V2 forecast fixtures has 95 committed timestamped quotes; six remain uncaptured.
- All market certification thresholds remain unchanged and unmet. Value betting remains LOCKED.

## 7. CI and release boundary

PR #120 remains OPEN / DRAFT / UNMERGED on `integration/v2-report-bundle-wiring-20261114`, HEAD `2f4a85cb1e885e786c189caef5d38ee7240a072c`. Latest exact-head required checks passed: Phase 5 Shadow Regression; Phase 2 Data Foundation; PostgreSQL 16/18 acceptance; Historical Model Audit; Certification Evidence Integrity; AI Midas Brazil Série B identity reconciliation. Daily Fixture Predictions was SKIPPED as intended.

No purchase, paid upgrade, PR merge, production write/deploy, public publication, Telegram delivery, schedule activation or value-bet unlock.
