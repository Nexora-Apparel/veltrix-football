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

1. Complete the OpenPlay Parquet-to-feature adapter and chronological loader, preserving the post-import temporal gate and xG model ID.
2. Run the manual 5Dollar opening-odds capture after the workflow is available on the default branch; continue bounded runs until the declared fixture universe is measured.
3. Measure timestamped quote coverage against a predeclared fixture × bookmaker × market universe; do not infer the 98% gate from source claims.
4. Reconcile OpenPlay identities beyond the 89 exact matches using evidence-backed aliases only; unresolved entities stay quarantined.
5. Run prospective and chronological challenger evaluation using only observations eligible at each cutoff.

No prediction publication, value-bet activation, Telegram delivery, schedule activation, production database write or Vercel deployment is authorized by this Stage 2 acquisition work.
