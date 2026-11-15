# VELTRIX FOOTBALL 2.0 — Stage 2 non-commercial odds acquisition
Date: 2026-11-15

## Governing use restriction

The project owner confirmed that source permissions permit VELTRIX project use only while monetisation is prohibited. This restriction applies across the source estate regardless of whether an upstream provider's standard terms would permit commercial use.

- No monetisation, resale, sublicensing or raw-feed redistribution.
- Internal storage, analysis, model research and non-commercial evaluation only, within each provider's endpoint, plan, competition and retention entitlements.
- Keep attribution, provenance, exact response bytes, hashes, source timestamps and actual VELTRIX recording times.
- Rights approval never waives provider authentication, account-plan, quota, endpoint or temporal eligibility restrictions.

## 5DollarFootballAPI opening odds

The staging database now has a dedicated non-commercial approval:
- Approval: `approval-5dollar-community-odds-quote-noncommercial-2026-11-15`
- Data type: `odds_quote`
- Permitted uses: collection, cache, storage, historical import, model training and benchmarking.
- `commercial_use_allowed=false`; raw redistribution prohibited.
- Competition scope is restricted to the seven already-approved canonical competition IDs.
- Evidence: October 2026 provider Terms and the existing legal review, SHA-256 `e818940f894b924ec3e25fbf36e3a43e3969b17d509b21b7a476ddf14a10d879`.

The manual workflow `phase2-5dollar-opening-odds-capture.yml` and script `scripts/phase2_capture_fivedollar_opening_odds.py` capture only Bet365 1X2 opening quotes from `GET /v1/fixtures/{id}`. They preserve the provider `opened_at` timestamp separately from retrieval and database-recording clocks. Closing and in-play prices are ignored because this response shape does not give them their own timestamps.

Safety envelope:
- Manual `workflow_dispatch` only; no cron or automated schedule.
- Maximum 25 fixture requests per run, 90-day lookback, at least 3.1 seconds between requests.
- One request per fixture; no retries.
- Staging only, immutable response bytes and hashes, capture manifest and request lineage.
- Rights are rechecked before every request.
- Quotes missing a valid timezone-aware opening timestamp, malformed prices, or timestamps at/after kickoff are stored as ineligible evidence, never repaired.
- The paid Ultra tick-history endpoint is not called.

As of this review, 763 5Dollar canonical fixtures fall within the last 90 days in staging. The workflow is intentionally bounded to 25 per run; repeated manual runs are required for broader coverage. No opening quote has yet been acquired by this new workflow.

## OpenPlay row-level data qualification

The pinned OpenPlay `data-v0.1.0` release has been acquired and verified in isolated staging. The row-level temporal audit covers 2,927,621 records across cards, formations, lineups, player-match statistics, shots and team-match statistics. All rows join to a match page with a documented UTC `matches.scraped_at` page-save timestamp; no orphan rows were found. 646 duplicate natural-key rows are explicitly quarantined (644 formations, 2 player-match-stat rows). The shot, player-match and team-match tables retain one xG model identifier: `openplay_xg_v1`.

Identity reconciliation currently resolves 89 of 422 OpenPlay teams and 5 of 22 competitions against the 5Dollar canonical registry. Across the five mapped competitions, 10,110 of 21,563 match snapshots currently have both teams and competition resolved. Unresolved teams and competitions remain quarantined; no fuzzy/display-name-only mappings are admitted.

The 15 pinned release assets and 26,547 match-page snapshots are persisted in staging. The six detailed feature tables remain in the immutable Parquet release assets; the row-level audit is an acceptance report, not a claim that 2.9 million feature rows have been normalized into individual SQL observations.

Temporal rule: the source page-save timestamp and actual VELTRIX import/recording time are distinct. These post-match features may be used to train or inform forecasts only for prediction cutoffs after VELTRIX actually recorded the dataset and after the relevant match had completed. They cannot be backdated into historical walk-forward cutoffs before import, and post-match features from a fixture cannot be used to predict that same fixture.

## The Odds API

A quota-free `GET /v4/sports/?all=true` probe passed on 2026-11-15:
- HTTP 200, all five configured soccer sport keys present.
- Account status `ACTIVE`.
- 205 requests used, 295 remaining, last request cost 0.
- All quota headers present.
- Response hash `7c93d242daebfc56b4af178ca9cd4f2dbbdeb916d280f60614e38d9bfde7567b`.
- Evidence persisted in staging as provider response 416.

This is a no-credit account/catalogue check only. No live event odds request or historical odds request has been made. The one-event live odds probe remains a separate 3-credit operation; the paid historical odds endpoint remains disabled pending historical-plan entitlement and its own explicit credit reservation. No credits were spent by the successful probe.

## Remaining Stage 2 gates

1. The pure OpenPlay team-match feature adapter is now implemented in `veltrix_v2/data/openplay_features.py`. Its regression suite verifies canonical IDs, xG model provenance, team/player/lineup/shot/card/formation features, duplicate rejection and strict post-import cutoff eligibility. Still outstanding: wire it to the pinned Parquet assets and staging recording-time/crosswalk tables, then persist or expose the derived feature bundle to the chronological loader.
2. Run the manual 5Dollar opening-odds capture after the workflow is available on the default branch; continue bounded runs until the declared fixture universe is measured.
3. Measure timestamped quote coverage against a predeclared fixture × bookmaker × market universe; do not infer the 98% gate from source claims.
4. Reconcile OpenPlay identities beyond the 89 exact matches using evidence-backed aliases only; unresolved entities stay quarantined.
5. Run prospective and chronological challenger evaluation using only observations eligible at each cutoff.

No prediction publication, value-bet activation, Telegram delivery, schedule activation, production database write or Vercel deployment is authorized by this Stage 2 acquisition work.

## 5Dollar opening-odds capture query audit — 2026-11-15

A read-only staging audit found and corrected a scope-join defect before any odds API requests were made.

The approval stores the seven provider competition IDs, while the original target query compared them to VELTRIX's internal `fixtures.competition_id`. That mismatch returned zero targets. The query now compares the approval scope against `competitions.provider_competition_id`.

Independent read-only staging count after applying the corrected predicate:
- 763 fixtures in the 90-day lookback.
- 763/763 match the seven approved provider competition IDs.
- 763/763 have a currently valid RESOLVED fixture crosswalk.
- 763/763 have no prior `odds_opening_quote` observation and are capture candidates.

The correction and regression test are committed on PR #120:
- Script commit: `58a7c79f052416f9a3fd14eb439b7b731bc7254d`.
- Regression test commit: `4a9b41ca69c63932bc17184c6e7cb2be0a416233`.
- Test-fixture context-manager correction: `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a`.
- Exact-head Phase 2, PostgreSQL 16/18, Phase 5 shadow, historical audit and certification-integrity checks: PASS on `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a`.

No provider odds requests have been made. The 763 count is a fixture-universe count, not a quote-coverage result. The manual workflow is still on the draft PR branch and cannot be dispatched until the workflow exists on the default branch; no merge is authorized here. Once available, execute bounded batches (maximum 25 fixture requests, one request per fixture, no retries) and measure actual timestamped quote coverage from persisted observations.


## 5Dollar opening-odds capture and historical-odds gate — 2026-11-15
The first bounded Community capture completed successfully:
- Workflow [#43727509783](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727509783), job `132852553767`, exact commit `70b1a8ef1742975464f74dfefcf8dac265d46d86`; 26 focused tests passed.
- 25 fixture requests, no retries; 26 provider requests including fresh status preflight. Community quota profile: 300/hour, 20/minute; remaining 299 before fixture calls and 274 after.
- 25 Bet365 1X2 opening quotes inserted and independently read back from staging; all 25 have provider opening timestamps before kickoff and retrieval after opening. All 25 exact-match their canonical fixture crosswalks.
- Capture manifest 109; 25 request rows; provider response IDs 462–486; observation IDs 431621–431645. Artifact #14166689086; ZIP SHA-256 `b8a6b0594294fdd4b6178ebab0e010c2a30fb15b87686c3ba30457dae82fd171`.
- Eligible 90-day universe: 763 fixtures; 25/763 = 3.28%; 738 outstanding. All 763 have exactly one active RESOLVED fixture crosswalk. Per-competition quote counts: Brazil Serie A 1/115; Brazil Serie B 10/151; England Premier League 6/100; France Ligue 1 2/90; Germany Bundesliga I 0/81; Italy Serie A 0/110; Spain La Liga 6/116.
- Historical odds: 0 5Dollar historical tick observations; the full history endpoint requires Ultra, not entitled. The Odds API has 3 catalogue-only `/v4/sports/` responses and 0 event/historical odds requests. No CLV/closing movement evidence. The 98% timestamped odds coverage target remains unmet.
- The 25 opening observations are an eligible timestamped subset only; do not infer full competition/season coverage or model certification. Keep value betting locked.
