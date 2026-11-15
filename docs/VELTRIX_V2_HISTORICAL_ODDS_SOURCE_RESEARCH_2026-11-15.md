# VELTRIX FOOTBALL 2.0 — Historical odds source research

**Research date:** 2026-11-15  
**Scope:** Timestamped bookmaker-specific pre-match odds, historical closing prices and CLV evidence  
**Status:** Source discovery only. No provider credentials used, no paid requests made, no odds data imported.

## 1. Current evidence gap

The latest recorded Stage 2 opening-odds continuation remains 400/763 fixtures (52.42%). There are 363 fixtures without that continuation quote; 748/763 is the 98% coverage threshold, so 348 additional eligible quotes are required to reach the threshold. These are opening-price observations and do not qualify as closing prices or CLV.

The Odds API historical data is now the highest-priority coverage candidate for Brazil Série B because its official league coverage page lists historical odds from 2022-06-30. That is a documented start date, not proof that 98% of the Veltrix fixture universe or all required bookmaker/market combinations are populated.

## 2. Candidate assessment

### A. The Odds API — priority 1 for coverage discovery

Official references:

- Historical data: https://the-odds-api.com/historical-odds-data/
- Brazil Série B coverage: https://the-odds-api.com/sports/brazil-serie-b-odds.html
- Update intervals: https://the-odds-api.com/sports-odds-data/update-intervals.html

Verified documentation:

- Brazil Série B is a supported sport key: soccer_brazil_serie_b.
- Historical Brazil Série B odds start at 2022-06-30 01:05 UTC.
- Historical featured-market snapshots are available every 10 minutes from June 2020 and every 5 minutes from September 2022.
- Historical odds are on paid usage plans.
- Historical coverage-discovery endpoints are available on all plans and cost 1 credit per request.
- Historical odds requests return the actual snapshot timestamp and bookmaker/market last_update fields. The returned snapshot is the closest available timestamp at or before the requested date.
- Historical odds endpoint cost is 10 credits per region per market. The Brazil Série B example uses region eu and demonstrates Pinnacle 1X2, spreads and totals.

Qualification boundary:

- This is a sampled snapshot archive, not a guarantee of the exact final price offered by every bookmaker at kickoff.
- The per-bookmaker or per-market last_update can be older than the enclosing snapshot. The official Brazil Série B example shows a bookmaker update at 06:18 UTC for a 22:00 UTC kickoff. Every quote must therefore be checked against its own timestamp and a defined freshness threshold.
- The last valid pre-kickoff snapshot can be used as a timestamped close proxy only if the quote is genuinely pre-kickoff, its quote-level last_update is fresh enough, and the rule is fixed before evaluation. Do not silently label a stale price as a close.
- Bookmaker and market coverage must be measured per fixture; the league's existence in the API catalogue is not evidence of 98% coverage.

Next technical action: run a fresh quota preflight against the already configured key, then use only the 1-credit coverage-discovery endpoints to build a fixture × bookmaker × market coverage matrix. Do not request paid odds snapshots until the discovery matrix, quota headroom and per-market cost are reviewed. No API request was made during this research.

### B. Odds-API.io — priority 2, exact closing-line API but league coverage unverified

Official references:

- Historical closing lines: https://odds-api.io/historical-odds-api
- API reference: https://api.odds-api.io/v3/docs/index.html
- Pricing: https://odds-api.io/pricing

Verified documentation:

- Historical closing prices are available from December 2025.
- The bulk endpoint supports up to 10 leagues, 366 days, 30 bookmakers and 100 events per page.
- Each bookmaker market record includes an updatedAt timestamp, bookmaker name, odds and final score.
- The bulk closing-lines endpoint is paid; the published entry plan starts at £49/month. New free keys are paused.
- The API advertises 450+ bookmakers, but event and market coverage varies by fixture.

Qualification boundary:

- The official documentation reviewed does not establish that Brazil Série B is supported. Do not infer league coverage from the 450+ bookmaker headline.
- The closing-line data is potentially a stronger direct fit than 5-minute snapshot archives, but must first verify the Brazil Série B league slug, bookmaker selection, market coverage, timestamp semantics and permitted internal use.
- Do not purchase a plan or create a new credential before the league-coverage check is complete.

### C. SockOdds — useful for selected leagues, not Brazil Série B archive

Official references:

- History: https://sockodds.com/docs/history/
- Historical API use case: https://sockodds.com/use-cases/historical-odds-data-api/

Verified documentation:

- The Pro plan records every price change, bookmaker, market, decimal odds and observed_at timestamp; opening and closing snapshots are available.
- History starts 2025-12-22 for a limited list (EPL, MLS, La Liga, Bundesliga, Ligue 1, Serie A and Champions League).
- Other leagues begin only 2026-10-08.
- Brazil Série B is not in the earlier-history league list.
- History and daily Parquet files are Pro-only.

Disposition: supplementary for supported leagues and prospective observations only. It cannot fill the Brazil Série B 2022–2026 historical gap and cannot be assumed to provide a deep archive for unlisted competitions.

### D. Odds.School — Brazil Série B evidence visible, ingestion permission unresolved

References:

- Brazil Série B archive: https://odds.school/soccer/brazil_serie_b/archive
- Example match with bookmaker update times: https://odds.school/soccer/brazil_serie_b/goias/clube_de_regatas_brasil/todds_36706899518f639c53d5d56f4278dcbd

The public archive states that each match page keeps the last bookmaker prices recorded before kickoff. A sampled page shows 49 sportsbooks (18 in the selected model analysis) and per-bookmaker Updated timestamps, including Pinnacle at 23:25 UTC for a 23:30 UTC kickoff.

Qualification boundary:

- The archive says it contains matches the service has analysed, not that it is complete for the full league.
- The public pages provide useful evidence of bookmaker-specific prices and update times, but no documented public API or explicit permission for bulk extraction was found.
- No scraping or automated collection is authorized by this research. Request written permission and a documented export/API before considering ingestion.
- The sampled prices are not yet verified against the exact canonical 763-fixture universe or the required market coverage.

Disposition: manual/source-permission investigation only; not admitted.

### E. SharpPick — not eligible without permission and bookmaker-level evidence

References:

- Brazil Série B archive: https://sharppick.app/en/league/brazil-serie-b/
- Terms: https://sharppick.app/en/terms/

The public league page reports 130 archived Brazil Série B games and 20,710 snapshots, sampled every five minutes. The terms explicitly prohibit bulk crawling/scraping or redistribution without permission. The public summary does not expose the required bookmaker-specific quote identities and timestamps for each snapshot.

Disposition: no automated collection. Written permission and a bookmaker-resolved export would be required before reconsideration.

### F. Betfair Historical Data — exchange benchmark only

References:

- Historical data: https://support.developer.betfair.com/hc/en-us/articles/360002407732-What-data-is-provided-by-the-Historical-Data-service
- Access: https://support.developer.betfair.com/hc/en-us/articles/360002407712-How-can-I-access-the-Betfair-Historical-Data-service

Betfair offers timestamped exchange market, price and settlement data from April 2015, available by purchase/download to registered Betfair.com customers. It is exchange back/lay data, not a named sportsbook's bookmaker close.

Disposition: potentially useful as a separate exchange-market benchmark or independent CLV series. It cannot replace the bookmaker-specific closing-odds requirement. Access eligibility and costs are unverified.

### G. OddsIntel Data — consensus benchmark only, not bookmaker-specific

References:

- API: https://data.oddsintel.app/docs
- Terms: https://data.oddsintel.app/terms

The service publishes derived consensus closing prices with close_ts, source count and price-age fields, but no bookmaker names. History starts 2026-10-10. Its terms describe the service as business-only and exclude betting operators and their affiliates.

Disposition: does not qualify for bookmaker-specific closing odds. Any use as a separate fair-market benchmark would require a separate terms/eligibility review.

### H. Other previously investigated sources

- Olivier Sports Data: technically rich timestamped bookmaker odds, but the accessible Americas dataset does not establish Brazil Série B coverage; no new evidence found to close that gap.
- Football-Data.co.uk / ScoreTape wrapper: source-rights suitability remains unresolved; do not ingest as model-training data.
- OddsPortal: automated scraping restrictions remain; no written permission.
- CheckBestOdds: historical highest odds are visible, but the reviewed archive does not establish quote timestamps sufficient for the strict closing-price gate.
- AI Midas: its average pre-match 1X2 odds are not bookmaker-specific timestamped closing quotes and remain non-PIT.

## 3. Recommended acquisition sequence

1. Preserve the existing 400/763 opening-odds evidence unchanged. Do not relabel it as closing odds.
2. Run a fresh quota preflight for the existing The Odds API key; do not assume prior quota headroom.
3. Use only coverage-discovery requests (1 credit each) to map Brazil Série B historical event and market availability. Group queries by actual 5-minute snapshot timestamps to minimize credits.
4. Build a coverage matrix keyed by canonical fixture ID × bookmaker × market, with source event ID, earliest/latest available snapshot, quote timestamp, snapshot timestamp, and quote age at kickoff.
5. Test a small, representative sample before any bulk price capture. Reject any bookmaker quote whose last_update is after kickoff, missing, or too stale under the preregistered freshness rule.
6. Compare the discovery result with the 98% coverage target. If The Odds API is incomplete, evaluate Odds-API.io's league slug and a permission-based Odds.School export before buying access or expanding capture.
7. Only after rights, coverage, identity and freshness pass should timestamped bookmaker prices be normalized into odds_quote_observations and considered for closing-line/CLV evaluation.
8. Keep opening quotes, sampled pre-kickoff snapshots, exact bookmaker closes, consensus prices and exchange prices in separate evidence classes.

## 4. Stage 2 disposition

- Opening odds continuation: 400/763 (52.42%) at the last recorded ledger checkpoint; 348 additional quotes needed to reach 748/763 (98%).
- Historical closing odds: NOT QUALIFIED.
- Bookmaker-specific close coverage: NOT CERTIFIED.
- CLV: NOT CERTIFIED.
- PIT walk-forward: NOT MET.
- No new historical-odds API requests or paid captures were made in this research.
- Value betting remains LOCKED.
