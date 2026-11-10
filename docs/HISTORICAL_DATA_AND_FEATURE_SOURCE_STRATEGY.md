# Historical Data and Pre-Match Feature Source Strategy

**Status:** architecture decision record  
**Date:** 2026-11-10  
**Applies to:** VELTRIX FOOTBALL 2.0  
**Decision:** keep the current xG-dependent inference model non-publishable until licensed, point-in-time xG inputs exist; evaluate a separate results-only model using strictly pre-kickoff score history. Do not manufacture xG from final scores.

## 1. Verified source position

### 5DollarFootballAPI — current primary source

The authenticated qualification evidence admits exactly five competition IDs:

- Italy Serie A: `3405541143`
- France Ligue 1: `3614399544`
- England Premier League: `4160026622`
- Spain La Liga: `4212821298`
- Germany Bundesliga I: `686337048`

The reviewed 90-day qualification artifact contains 501 accepted finished results, with complete pagination for the measured provider queries and zero duplicate IDs, invalid rows or missing team IDs. This proves the measured response set was retrieved and validated; it does not prove the provider catalogue is complete.

The current coverage profiler explicitly records xG, shots, lineups, player minutes, odds, point-in-time Elo, PPDA, travel and fatigue as unavailable from the acquired 5Dollar results archive. Do not infer these fields from scores.

### StrikerAPI — limited supplemental evidence

The 17-competition live qualification remains blocked by HTTP 402 insufficient credits. The only verified cross-provider reconciliation is the bounded EPL comparison. Provider xG/shot data must not be treated as complete or leakage-safe point-in-time features without a separate coverage and timestamp audit. A provider's retrospective xG value is not automatically a valid pre-match predictor.

### Sportmonks — potential paid xG source, not activated

Official documentation describes team/player expected-data endpoints. Its Basic xG add-on makes xG available after a match has finished; Advanced makes xG available in real time. The official FAQ says xG data begins in the 2024 season. The current public pricing page lists a base Starter plan from EUR 29/month and an xG & Pressure Index add-on from EUR 24/month (displayed promotional pricing may change).

Implications:
- Post-match xG can support retrospective descriptive analysis, but cannot be used as a pre-match feature for the same match.
- Only values captured and timestamped before a future fixture's prediction cutoff can become pre-match features.
- Historical xG coverage is bounded from 2024 onward according to the provider FAQ.
- Do not subscribe or incur spend without explicit budget approval and a rights/coverage review.

Official references:
- https://docs.sportmonks.com/v3/endpoints-and-entities/endpoints/expected-xg
- https://www.sportmonks.com/faq/
- https://www.sportmonks.com/football-api/plans-pricing/

### StatsBomb Open Data — research dataset only pending rights review

StatsBomb publishes selected competition-season event, match and lineup JSON for research. Its repository asks users who publish or distribute research/analysis based on the data to credit StatsBomb and use its logo. It is a curated subset, not a complete archive of the five admitted 5Dollar competitions. Do not assume commercial prediction-service or model-training rights from the public repository description; obtain and record applicable permission before integrating it into a commercial workflow.

Official reference:
- https://github.com/hudl/open-data

### Football-Data.co.uk — excluded from automated model acquisition

The provider's current contact/fair-usage policy says its free CSV files are for private individuals and academic research, with manual download or at most light twice-weekly automated download. It expressly says they are not intended for commercial or data-training projects using automated bots/scrapers. This source is therefore excluded from VELTRIX automated acquisition and model training unless the provider grants written permission or a separately licensed service is used.

Official references:
- https://football-data.co.uk/data
- https://football-data.co.uk/contact.php

### football-data.org — possible fixture/results cross-check, not xG/history substitute

The official free tier lists 12 competitions, delayed scores/fixtures/schedules and tables, with 10 calls/minute. The paid ML Pack Light lists 10 seasons of history at EUR 29/month. The published coverage includes the five European competitions already admitted through 5Dollar. Its FAQ requires visible attribution, and its terms restrict continued use of API data on a service after subscription cancellation. No xG entitlement is established by the free-tier description.

Implications:
- It may be evaluated as a low-volume independent fixture/results cross-check.
- It is not a replacement for a point-in-time xG feed.
- Historical data and ongoing product rights require plan-specific confirmation.
- Do not activate or spend without explicit budget approval.

Official references:
- https://www.football-data.org/coverage
- https://www.football-data.org/pricing
- https://www.football-data.org/documentation/api
- https://www.football-data.org/documentation/faq
- https://www.football-data.org/about

## 2. Model architecture decision

Maintain two separate model families:

1. **xG-informed Dixon-Coles/Poisson model** — the existing `app/pre_match_prediction_engine.py`. It continues to require point-in-time xG-for/xG-against plus Elo. It must withhold when those fields are unavailable. Do not weaken its requirements by substituting final goals and labelling them xG.
2. **Results-only Poisson/Dixon-Coles candidate** — a separately versioned model to be implemented and evaluated from historical finished scores. Candidate predictors may include team attack/defence strengths, rolling goals for/against, competition home/away scoring baselines and Elo. Every feature must be reconstructed strictly from matches completed and available before that fixture's prediction cutoff.

The results-only candidate must:
- use provider team IDs and reviewed aliases, not fuzzy name joins;
- derive each feature from an immutable chronological history snapshot;
- exclude the target fixture and every later fixture from the feature window;
- use explicit minimum-history and shrinkage rules, with missing/insufficient history causing withholding rather than fabricated team statistics;
- preserve source ID, retrieval/availability/observation timestamps and payload hashes;
- train and evaluate chronologically with an embargo, never random train/test splitting;
- report its performance separately from the xG-informed model;
- remain non-publishable and value-betting-disabled until real walk-forward and prospective certification passes.

Results-only goal rates are not xG. They are a different statistical input family and must be labelled accordingly.

## 3. Data sufficiency gates

The current 501-result qualification sample is not enough to claim robust model performance or meet the certification contract. The model and each market still require:
- at least 1,000 chronological walk-forward records per market;
- at least 300 prospective settled selections per market;
- at least 90 distinct Africa/Lagos kickoff dates among those prospective selections;
- at least 98% timestamped pre-cutoff odds coverage;
- positive net ROI with a positive lower 95% date-clustered confidence bound;
- for 1X2, both Brier score and log loss better than the de-vigged bookmaker baseline.

A provider's historical data count is not interchangeable with prospective evidence. Backtest records do not satisfy the prospective-selection requirements.

## 4. Immediate implementation sequence

1. Complete review and authorized integration of PR #42, PR #43 and PR #46 in dependency order. Do not merge without explicit authorization.
2. Once the manual workflow is available on the default branch, acquire small, non-overlapping historical batches only within the qualified five-competition scope and provider's available history window. The rolling-hour quota ledger must be reserved and settled with the same `run_id-run_attempt` identity.
3. Validate each report and archive hash; profile team IDs, duplicate match slots, coverage by month and team, and source completeness limitations.
4. Build point-in-time score-derived features and a separate results-only candidate. Keep xG model withheld until licensed xG data is available.
5. Acquire a sufficiently large, rights-cleared historical dataset and timestamped odds source before attempting certification.
6. Keep Neon imports, prediction publication, Telegram delivery and schedules paused until separately authorized release gates pass.

## 5. Safety and rights

This document is a technical source assessment, not legal advice. Provider terms, retention rights, model-training rights, attribution and redistribution restrictions must be reviewed for the actual subscription and deployment use before integration. Public availability is not equivalent to commercial-use permission.
