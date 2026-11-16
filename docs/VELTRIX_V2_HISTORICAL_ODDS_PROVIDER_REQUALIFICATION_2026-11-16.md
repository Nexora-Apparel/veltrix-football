# VELTRIX FOOTBALL 2.0 — Historical Odds Provider Requalification

**Checked:** 2026-11-16  
**Branch:** integration/v2-report-bundle-wiring-20261114  
**Purpose:** Continue historical and closing-odds provider qualification without purchasing an upgrade, topping up credits, or changing existing source authorizations.

## Decision summary

- **5DollarFootballAPI Ultra:** NOT AVAILABLE on the current account. Fresh status-only run [43816256678](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43816256678) returned HTTP 200 at 2026-11-16T06:22:09Z with exact plan value community, 300 requests/hour and 299 remaining. One GET /v1/status request only; odds-history requests 0. The raw response SHA-256 is 3e9d45a8a605349357ffe0911eea10ecbdc8da98eacdbc7457b49ed0b02e1b48. Do not call the Ultra-only odds-history endpoint.
- **No upgrade or credit purchase:** No provider upgrade, paid add-on, wallet top-up, or new subscription is authorized or performed.
- **The Odds API:** Retain as the already-approved prospective bookmaker benchmark. It has real provider timestamps on current odds and a paid historical snapshot API. The existing account is used only within its current quota and the one-event/three-credit capture guard. Historical archive snapshots are not fetched on the current plan.
- **AI Midas:** Remains an authorized historical-statistics and additional-odds source, including Brazil Série B where available. Its authorization is not proof of a bookmaker-specific, point-in-time closing archive. Continue source-level identity, timestamp, coverage and rights qualification without assuming closing-line eligibility.
- **New alternatives:** SockOdds, Sportmonks Premium Odds and iSportsAPI are research candidates only. No credentials were used, no provider endpoints were called, and none is admitted to the V2 evidence corpus by this desk review.

## Candidate comparison

| Provider | Publicly documented history | Timestamp semantics | Seven-competition fit | Current decision |
|---|---|---|---|---|
| The Odds API | Historical snapshots from 2020 for featured markets; 10-minute snapshots initially and 5-minute intervals from Sep 2022. Historical snapshots require a paid usage plan. | Snapshot response contains a snapshot timestamp; each bookmaker/market also has last_update. | Broad bookmaker/sport coverage, but each target sport/market/bookmaker must be checked in the free historical coverage discovery endpoint. | Existing approved provider; use current plan for prospective timestamps only. Do not purchase historical access. |
| SockOdds | History and opening/closing snapshots require Pro. Own recordings only; EPL history from 22 Feb 2026 (with explicit gaps), La Liga from 17 Aug 2026 (with a gap), Bundesliga/Ligue 1/Serie A from 18 Aug 2026. Every other league begins 8 Oct 2026. | Each price-change row has observed_at, kind, bookmaker, market and outcome IDs. Closing snapshot is the last price observed before scheduled start. | The extended-history table does not list Brazil Serie A or Brazil Serie B. SockOdds says every other covered league began recording on 8 Oct 2026, but live coverage of both Brazil competitions is not proven by the public history table. Full seven-competition coverage therefore remains unverified. | Strong timestamp model, but Pro-only and incomplete target-league coverage. Do not buy Pro. Reconsider only if terms and exact coverage are accepted. |
| Sportmonks Premium Odds / TXODDS | Opening odds and subsequent changes retained until 7 days after kickoff. This is a rolling post-kickoff retrieval window, not a deep multi-season archive. | Historical records expose bookmaker update time; current premium feed documents per-odd latest update time. | Sportmonks has broad football coverage, but exact odds availability for each of the seven VELTRIX competitions and required markets still needs fixture-level proof. | Technically promising for prospective capture and short rolling history, but Premium is an optional paid add-on. No activation or purchase. |
| iSportsAPI | Public catalogue claims opening/latest pre-match odds up to one year; changed-price records for 18 agencies; in-play odds history up to one month. | Historical change records describe an operation time; exact field semantics and source-time guarantees require sample verification. | Exact availability for England, Spain, Italy, France, Germany, Brazil Serie A and Brazil Serie B not established. | Research-only. Rights, timestamp semantics, bookmaker coverage and account entitlement are unverified. No account or endpoint request. |
| 5DollarFootballAPI | Community account has not demonstrated access to per-price history; previous BTTS history attempt returned 403. Ultra endpoint requires Ultra or above. | Dedicated status-only probe currently reports Community; do not infer Ultra from rate limits or other endpoints. | Seven competitions previously fixture-qualified; this does not prove per-market odds-history coverage. | No Ultra access claim. Do not call odds-history or buy upgrade. |

## Qualification implications

1. **Historical archive:** None of the new alternatives is currently accepted as a complete, rights-cleared archive across all seven target competitions. AI Midas remains authorized for historical statistics and additional odds, but its bookmaker-specific timestamped closing-line suitability must be proven separately.
2. **Prospective collection:** Continue timestamped collection from the already-approved The Odds API only within existing quota, exact fixture crosswalk, one-event cap and idempotent commit controls. Preserve source timestamps separately from retrieval timestamps.
3. **Rolling close collection:** Sportmonks Premium could technically support a short rolling capture window if existing access is discovered without activating an add-on; no purchase is permitted. A quote retrieved after the seven-day retention window cannot be recovered from that feed.
4. **SockOdds:** Its observed_at field is suitable in principle for price-change chronology, but a Pro-only endpoint cannot be used without a paid plan. The extended-history table does not enumerate the two Brazil competitions; the provider's general 8 Oct 2026 start for other leagues is not enough to prove that both Brazil competitions are actually covered.
5. **iSportsAPI:** Do not use its advertised one-year opening/latest archive as a substitute for a fully timestamped bookmaker-specific closing archive until a sample proves the exact bookmaker, market, selection, line, source timestamp, and event identity.
6. **Certification:** No source-level desk review changes the unchanged certification thresholds. Every market still requires at least 1,000 chronological walk-forward matches; at least 300 prospective settled selections; at least 90 distinct dates; at least 98% valid timestamped bookmaker-quote coverage; net ROI greater than zero with lower 95% ROI confidence bound greater than zero; and 1X2 Brier score and log loss better than the bookmaker benchmark. The value-betting lock remains in force.

## Next no-purchase actions

- Keep the 5Dollar status-only entitlement workflow isolated; the fresh 2026-11-16 status result confirms Community. Rerun only when a later fresh status observation is needed. Do not call /odds/history without explicit Ultra evidence.
- Continue The Odds API prospective event capture for the remaining already-admitted V2 forecast fixtures, one exact-match fixture per bounded workflow run, only when staging persistence is available and provider quota is checked first.
- Request no new provider credentials or paid plan. If an existing authorized AI Midas credential is already configured, qualify only documented history/odds endpoints with a bounded, read-only schema-and-timestamp probe after checking current quota and account access.
- For each candidate, require a fixture-by-fixture matrix for the seven competitions, bookmaker IDs, market IDs, source timestamp semantics, retention, historical start date, gaps, corrections, result linkage, and accepted rights before admitting any rows.

## Public references checked

- The Odds API historical archive: https://the-odds-api.com/historical-odds-data/
- SockOdds history and snapshots: https://sockodds.com/docs/history/
- SockOdds API reference: https://sockodds.com/docs/
- Sportmonks Premium Odds history: https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/premium-odds-feed/premium-pre-match-odds/get-all-historical-odds
- Sportmonks Premium Odds product: https://www.sportmonks.com/football-api/premium-odds-feed/
- iSportsAPI football odds catalogue: https://www.isportsapi.com/en/products/detail/football-api-product-53.html

**No purchase, upgrade, provider request, database write, prediction publication, Telegram delivery or schedule activation was performed for this desk qualification.**
