# VELTRIX FOOTBALL 2.0 — Historical/Closing Odds Source Acceptance Contract

**Date:** 15 November 2026  
**Stage:** 2 — data foundation  
**Status:** Draft; no full-universe closing-odds source accepted.

## Frozen universe

| Competition | Fixtures |
|---|---:|
| Brazil Serie A | 115 |
| Brazil Serie B | 151 |
| England Premier League | 100 |
| France Ligue 1 | 90 |
| Germany Bundesliga I | 81 |
| Italy Serie A | 110 |
| Spain La Liga | 116 |
| **Total** | **763** |

Kickoff range: 2026-08-17 through 2026-11-11 UTC.

## Mandatory acceptance gates

1. **Entitlement:** A real VELTRIX key with documented paid historical-odds access and a successful historical endpoint response. Catalogue access alone is not entitlement evidence.
2. **Rights:** Current approval for all seven competitions and intended collection, storage, benchmarking, model-training and user-facing derived uses. Preserve terms URL/version and approval ID. Raw redistribution stays disabled unless licensed.
3. **Coverage:** Verify all seven competition keys and actual event-level historical 1X2 coverage. At least 748/763 fixtures (98%) must have valid closing evidence; target 763/763.
4. **Market:** Home/draw/away outcomes, bookmaker key, decimal price, market last-update timestamp and provider snapshot timestamp. Consensus-only prices are not bookmaker-specific closes.
5. **PIT integrity:** Use the closest snapshot at or before kickoff. Require snapshot timestamp and market last-update <= kickoff; preserve retrieval/availability time. Reject post-kickoff or retrospectively revised values.
6. **Identity:** Active, versioned provider-event-to-canonical-fixture crosswalk. Unresolved or ambiguous mappings are excluded.
7. **Provenance:** Raw response bytes/hash, endpoint, request parameters, HTTP status, quota headers, requested/retrieved times, source snapshot time, provider response ID and rights approval ID persisted in staging.
8. **Safety:** Staging only, fresh quota preflight, bounded batches, pacing, no automatic retries; reconcile each batch before proceeding. No production, publication, Telegram, schedule or value-betting activation.
9. **CLV comparability:** Compare the taken/published price with the close for the same fixture, market, outcome, odds format and bookmaker, or an explicitly defined benchmark. Do not label consensus as bookmaker-specific CLV.

## Provider assessment — 15 November 2026

### The Odds API — strongest technical candidate; not yet accepted

Public documentation lists all seven required competition keys with historical coverage beginning before the VELTRIX universe. Featured 1X2/h2h snapshots begin in 2020; snapshots are 10-minute intervals initially and 5-minute intervals since September 2022. The historical endpoint returns the nearest snapshot at or before the requested time and costs 10 credits per region per market. Historical odds require a paid plan.

VELTRIX account evidence is insufficient:
- Three persisted `GET /v4/sports/?all=true` calls show 205 credits used and 295 remaining (500 total), consistent with the published Free tier, though the account probe records plan code as undisclosed.
- Zero event-odds and zero historical-odds responses are persisted.
- Existing approval `approval-the-odds-api-v4-owner-authorized-2026-11-14` covers five competitions only; Brazil Serie A and B are excluded.
- Public terms permit storage, derived outputs, model training and commercial user-facing use, but prohibit raw-feed resale/redistribution. Terms do not establish paid entitlement or expand VELTRIX approval scope.

**Acceptance condition:** verify paid historical endpoint access, actual bookmaker/1X2 response coverage in all seven competitions, and rights approval including Brazil A/B. No paid plan has been purchased or activated.

Official sources:
- Historical coverage/API: https://the-odds-api.com/historical-odds-data/
- Pricing: https://the-odds-api.com/
- Terms: https://the-odds-api.com/terms-and-conditions.html

### OddsIntel Data — rejected for this frozen universe

Its published history begins 10 October 2026. Of the 763 VELTRIX fixtures, 415 kick off before that date and only 348 fall within its history window. It supplies consensus closes, not named bookmaker prices; takeable grading is unchecked; terms exclude betting operators/affiliates and prohibit presenting CLV grades as proof of a betting record. It cannot meet the full-universe 98% gate.

Sources: https://data.oddsintel.app/coverage · https://data.oddsintel.app/pricing · https://data.oddsintel.app/terms

### Other candidates

SockOdds and Odds-API.io remain unqualified: no VELTRIX entitlement, complete seven-competition response coverage, rights approval or persisted evidence has been verified.

## Release decision

Opening quotes are complete at 763/763 and remain a separate dataset. Until a provider passes every mandatory gate, historical/closing odds and CLV remain BLOCKED / NOT CERTIFIED. Stage 2 remains NO-GO; Stage 3, production deployment, prediction publication, Telegram delivery, scheduling and value betting remain disabled.

## Next execution sequence

1. Resolve The Odds API paid historical entitlement and Brazil competition rights-scope extension.
2. Run one bounded historical 1X2 probe per competition; verify bookmaker, timestamps and canonical event mapping.
3. Calculate exact quota usage from distinct snapshot times, regions and markets before bulk capture.
4. If the probe passes, acquire closing snapshots in controlled batches and reconcile to all 763 fixtures.
5. Recompute CLV and market-specific walk-forward/prospective certification. If entitlement or rights fail, retain NO-GO and evaluate another source without weakening the gates.


### Quota and bookmaker benchmark refinement — 15 November 2026

A read-only grouping of the frozen 763 fixtures found **589 distinct (competition, five-minute kickoff) snapshot buckets**. The Odds API's sport-level historical odds endpoint returns the event/bookmaker set for a requested snapshot and is documented at 10 credits per region per market. A planning estimate is therefore **5,890 credits for one region and the h2h market across the 589 buckets**, before any additional regions/markets or retries. This is an estimate only; final cost must be recomputed from actual snapshot timestamps and region coverage before purchase or execution. The published START 20K plan is 20,000 credits/month at US$30/month and includes historical odds.

Bookmaker qualification is still unresolved. The public bookmaker list includes Pinnacle in the EU region and Betfair Exchange in UK/EU, but does not list Bet365 for soccer; the only Bet365 entry shown is Bet365 AU, limited to AFL/NRL h2h, spreads and totals. Therefore The Odds API cannot currently be assumed to supply a Bet365 soccer closing quote. A Pinnacle or Betfair close could be considered only as an explicitly declared benchmark, not same-bookmaker Bet365 CLV, and only after actual seven-competition event responses prove coverage.

Sources: https://the-odds-api.com/historical-odds-data/ ; https://the-odds-api.com/sports-odds-data/bookmaker-apis.html ; https://the-odds-api.com/
