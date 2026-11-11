# VELTRIX FOOTBALL 2.0 — Free Data and Cloud Infrastructure Research

**Research date:** 2026-11-11  
**Status:** Research register; no new provider is production-approved by this document.  
**Prediction isolation:** This work does not import, train, calibrate, publish or modify prediction logic.

## Executive decision

Use a layered, source-specific architecture rather than trying to force one free provider to supply everything:

1. **GitHub Actions** for controlled, reproducible Python ingestion, validation and scheduled jobs after explicit activation.
2. **OpenFootball** for CC0 fixtures/results and the current paired-snapshot qualification.
3. **OpenPlay** as the leading historical event/player-statistics dataset candidate: 2014/15–2025/26, big-five European leagues and selected international competitions, with lineups, player-match statistics, team-match statistics, shots and shot-level xG. Data is CC BY 4.0; attribution is required.
4. **FPL public API** as an EPL-only player-statistics and availability candidate (minutes, goals, assists, xG/xA, player status), but it is undocumented and has no upstream compatibility guarantee. Treat as a limited research candidate until terms and live responses are checked.
5. **PitchAPI** as the leading current-data API candidate to probe for player stats, shots/xG, lineups, events and advanced metrics. Its docs claim 77 leagues and free access, but no discoverable terms, privacy policy or upstream data provenance were found in this research. It is **not approved** for persistence, model training or public product use until the provider clarifies rights and lineage.
6. **5DollarFootballAPI** remains the qualified bounded EPL fixture/results reference. Its published statistics endpoint provides team-level attacks, dangerous attacks, shots and possession; it does not provide the player-level, lineup or injury coverage required for the full intelligence layer.
7. **Neon** for structured accepted records and metadata; **Cloudflare R2** is the preferred optional object store for larger immutable raw snapshots and Parquet datasets.

No single source currently supplies a complete, rights-cleared, free, all-competition package for player statistics, xG, lineups, injuries, odds and fixtures. Missing fields must remain explicitly missing rather than be fabricated.

## Source qualification register

### A. OpenPlay — high-priority historical dataset candidate

Repository: https://github.com/nlbair/openplay  
Python package: https://github.com/nlbair/openplay-py

Published dataset characteristics:
- Approximately 26,536 matches and 41.6 million events.
- Big-five European leagues, UEFA club competitions and selected international tournaments.
- Match, player, team, lineup, event, shot, card and formation tables.
- Approximately 780,000 player-match-stat rows and 1.07 million lineup rows.
- Every shot carries an xG value from the dataset maintainer's model.
- Static snapshot through 2025/26; not a current-season live feed.
- CC BY 4.0 data licence; credit “openplay (Noah Bair)”.
- Known gaps and data issues are published. The release lists 39 matches without events and 58 known problematic matches.

Use:
- Historical player/team feature research, shot-quality summaries, event-derived features, lineup research and model-development experiments after source checks.
- Keep OpenPlay's xG model as a separately identified provider/model feature. Never silently combine its xG with another provider's xG as though the values were identical.
- Consume published checksums and known-gap/data-issue registers.
- Do not commit the full dataset into the Git repository. Download into ephemeral GitHub Actions runner storage and move accepted immutable files to object storage if the measured size fits the free allowance.

Limitations:
- No current 2026/27 season snapshot in the published release.
- No broad African domestic league coverage.
- It is a static research dataset, not current injury, lineup or fixture intelligence.

### B. FPL public API — EPL-only player and availability candidate

Base URL: https://fantasy.premierleague.com/api/

Common public read-only endpoints documented by the community:
- `bootstrap-static/`: players, clubs, gameweeks and season totals.
- `fixtures/`: Premier League fixtures.
- `element-summary/{player_id}/`: player match history and previous seasons.
- `event/{gameweek}/live/`: gameweek player performance.

Useful player fields include minutes, goals, assists, expected goals, expected assists, form, ICT metrics and availability/status fields. It is particularly useful for EPL player form and squad availability signals.

Qualification caveats:
- This is an undocumented internal API used by the official FPL website. The Premier League does not publish a formal API specification or compatibility guarantee.
- Field names and payloads can change without notice.
- FPL availability status is not a fully authoritative injury report; preserve the exact source timestamp and status meaning.
- It only covers the Premier League and FPL-defined player metrics.
- Confirm the applicable Premier League/FPL terms for the intended use before commercial display, long-term retention or model-training use.

Decision: test read-only for EPL research; do not make it a required dependency or use it to fill data for other competitions.

### C. PitchAPI — high-priority live API candidate, rights gate unresolved

Documentation: https://pitchapi.dev/

Its documentation claims:
- Free access, no paid tier, no request allowance (subject to fair-use burst protection).
- 77 leagues and history back to 2021.
- Match events, shots, xG, lineups, team statistics, player statistics, player profiles, momentum, heatmaps and advanced player/team metrics.
- Player statistics include minutes, goals, assists, xG/xA and defensive/duel/passing categories where available.
- Lineups can be predicted before kickoff; each side has a `confirmed` flag. A predicted lineup must never be recorded as a confirmed lineup.

Critical unresolved checks:
- The documentation reviewed did not expose a terms of service, privacy policy, data-source lineage, underlying rights statement or clear retention/model-training permission.
- The public claims need a live read-only endpoint probe and a completeness audit against the already qualified EPL fixtures.
- Confirm who supplies the underlying event feed, what leagues actually have player stats and xG, whether historical records can be stored, whether commercial model training is allowed, and what attribution is required.

Decision: top API candidate to investigate, **not approved** for persistent production ingestion, training or public use until rights and data provenance are documented.

### D. StatsBomb Open Data — research-only event data

Repository: https://github.com/statsbomb/open-data

Provides selected competitions/seasons as JSON match, event, lineup and selected 360 data. StatsBomb requests source attribution and describes the release as intended for research projects and genuine interest in football analytics.

Decision:
- Use for research, event schema understanding and independent methodology testing only.
- Do not assume it grants commercial production, redistribution or commercial model-training rights.
- It is not a live feed and does not cover all requested competitions/seasons.

### E. 5DollarFootballAPI — fixture/results plus team-level match statistics

Documentation: https://5dollarfootballapi.com/docs

The current Free plan has a three-month result-history window and request limits already recorded in the provider qualification register. The published fixture statistics endpoint contains team-level attacks, dangerous attacks, shots on/off target and possession (including first-half splits). The provider's migration notes explicitly identify player/squad stats, lineups and injuries as areas not supplied by its API-Football-compatible feed.

Decision:
- Keep within its previously qualified EPL fixture/results scope.
- Continue using as the paired reference snapshot for OpenFootball.
- Do not treat its team statistics endpoint as player-level statistics or xG.
- Public-facing Free-plan use requires visible attribution “Football data by 5DollarFootballAPI” linked to the provider.
- The provider's terms permit use in commercial products and caching but prohibit raw-data resale/redistribution as a competing feed.

### F. TheSportsDB — low-volume metadata/lineup cross-check only

Documentation: https://www.thesportsdb.com/docs/api

The free v1 API uses a shared public key and documents 30 requests/minute, but several operations have small free result limits. Examples include event-lineup lookups capped at five results and player-stat lookups capped at ten results. It can be useful for low-volume metadata or spot checks, but is not a scalable player-statistics feed and does not establish xG coverage.

Decision: optional secondary verification only, after endpoint-specific live tests.

### G. Sources not approved as the core data backbone

- **API-Football/API-Sports:** the user-reported credential suspension history makes this unsuitable as a dependency. Its public free plan advertises 100 requests/day and many endpoints, but the existing project credential is not approved for use.
- **football-data.org:** free tier is useful for fixtures/results/tables, but squads and deeper data are paid. The project's previous token check failed; do not assume corrected access.
- **TheSportsDB:** free limits are too restrictive for bulk match-by-match lineups/player-stat ingestion.
- **FBref:** advanced Opta data ended in January 2026; scraping is not approved as a production ingestion method.
- **Understat:** xG is attractive for selected top leagues, but scraping and storage/training rights have not been cleared. Do not build a production scraper.
- **football-data.co.uk:** existing project research identified restrictions incompatible with commercial AI model training; exclude.
- **Open Matchday:** existing project decision excludes it from production due non-commercial-only use.
- **StatsBomb:** research-only until written rights say otherwise.
- **StrikerAPI:** account credits exhausted (HTTP 402); do not retry until credits are restored. It is not a prerequisite for the OpenFootball snapshot path.

## Data coverage required by VELTRIX

Every provider must be qualified independently for each competition and season. A provider that supplies EPL xG does not thereby qualify for Nigeria, Brazil or Argentina.

| Data domain | Required fields | Best free candidate(s) | Current decision |
|---|---|---|---|
| Fixtures/results | Stable match ID, teams, competition, kickoff, status, FT/HT score | 5Dollar EPL; OpenFootball CC0 | Paired reconciliation pending |
| Player match stats | Minutes, starts, goals, assists, shots, passes, tackles, cards, goalkeeper saves | OpenPlay historical; FPL EPL; PitchAPI probe | Historical candidate; live candidate pending |
| xG / xA | Shot-level xG, xA, model/version, penalty flag, shot coordinates | OpenPlay historical; PitchAPI probe; FPL EPL aggregate | Must preserve provider/model identity |
| Shots | Attempts, on-target, blocked, shot location, body part, situation | OpenPlay historical; PitchAPI probe | Pending live qualification |
| Lineups | Starting XI, bench, formation, confirmed/predicted flag, publication timestamp | OpenPlay historical; PitchAPI probe; TheSportsDB spot checks | Pending |
| Injuries/availability | Player, status, reason, effective time, last update, confidence | FPL EPL status; PitchAPI provider confirmation required | EPL candidate only; other leagues missing |
| Match events | Goals, cards, substitutions, penalties, event timestamps | OpenPlay historical; StatsBomb research; 5Dollar events; PitchAPI probe | Source-specific qualification required |
| Team style | PPDA, field tilt, possession, pressing, build-up, transitions | OpenPlay derived; PitchAPI probe | Do not accept undocumented derived metrics |
| Odds | Bookmaker, market, line, price, quote time, source timestamp | The Odds API / existing 5Dollar Bet365 feed | Separate odds pipeline; no model contamination |

## Free cloud execution and storage assessment

### GitHub Actions — recommended ingestion/ETL compute

Official billing documentation: https://docs.github.com/en/billing/concepts/product-billing/github-actions

- Standard GitHub-hosted runners in public repositories are free.
- GitHub Free private repositories include 2,000 runner minutes/month; artifact storage is 500 MB.
- Public-repository compute does not consume the private-repository minute allowance.
- Use Linux standard runners, pinned Python versions, bounded timeouts, concurrency controls, read-only credentials and explicit manual dispatch until a production schedule is separately authorized.
- Artifacts are useful for short-lived audit evidence, not as a long-term data lake. Keep the artifact small and short-lived.

Important: GitHub's `workflow_dispatch` requires the workflow file to exist on the repository default branch. The workflow can then be run from the Actions tab, GitHub CLI or REST API. The GitHub connector available to this project can create files and inspect runs, but does not expose a workflow-dispatch action; a repository user with write access must press **Run workflow** once.

### Cloudflare R2 — recommended optional raw-data object store

Pricing: https://developers.cloudflare.com/r2/pricing/

Current free allowance:
- 10 GB-month standard storage.
- 1 million Class A operations/month.
- 10 million Class B operations/month.
- No egress charge.

Use for immutable compressed JSON/Parquet snapshots, keyed by provider/competition/season/retrieval timestamp and SHA-256. Do not store any source until its licence and retention rights permit it. Confirm the account's billing setup and usage dashboard before relying on the free allowance.

### Neon — existing structured data store

Free-plan published allowance is 100 CU-hours/project/month, 1 GB PostgreSQL storage/project, 5 GB object storage/project and 5 GB public network transfer/project/month. The user's existing VELTRIX Neon project is already provisioned, but its current plan/remaining quota must be checked before any bulk use.

Use Neon for:
- accepted normalized fixtures, teams, players and crosswalks;
- source-observation metadata, hashes and retrieval timestamps;
- feature snapshots and evaluation records.

Do not write raw provider data into production during source qualification. Continue using the isolated Neon branch for later dry-run acceptance.

### Cloudflare Workers — orchestration, not heavy ETL

Workers Free currently allows 100,000 requests/day, but only 10 ms CPU per HTTP request and 10 ms CPU for Cron-triggered execution. It is suitable for lightweight webhooks, health checks or triggering a GitHub workflow; it is not the correct place for large Python/Parquet processing.

### Google Colab — exploratory notebook only

Colab offers free hosted notebooks, but its resource availability is not guaranteed and usage limits fluctuate. It is useful for one-off exploration and analysis, not for a dependable production scheduler or a persistent data pipeline.

### Supabase Edge Functions / Render — not the preferred ETL runner

Supabase Free Edge Functions have a 150-second wall-clock limit and 2 seconds CPU time; Supabase Cron can schedule database jobs, but heavy parsing belongs in GitHub Actions. Render free services can restart/spin down and do not support one-off jobs, so they are not a reliable scheduled ETL backbone.

## Recommended architecture

```text
Public / approved data providers
  ├─ OpenFootball (CC0 fixtures/results)
  ├─ OpenPlay (CC BY 4.0 historical events/player stats/xG)
  ├─ FPL public API (EPL player metrics; terms/API stability gate)
  ├─ PitchAPI (live API candidate; provenance/rights gate)
  └─ 5DollarFootballAPI (qualified EPL results reference)
              |
              v
GitHub Actions — isolated ingestion workers
  ├─ fetch immutable source bytes
  ├─ record source commit / retrieval time / SHA-256
  ├─ validate schemas and pagination
  ├─ preserve source IDs and native timestamps
  ├─ build explicit identity crosswalks
  ├─ report missingness, duplicates and conflicts
  └─ upload short-lived audit artifacts
              |
              v
Cloudflare R2 (optional raw data lake)
  └─ versioned, immutable, rights-approved JSON / Parquet
              |
              v
Neon isolated branch -> acceptance -> production tables
  ├─ canonical entities and provider crosswalks
  ├─ source observations and provenance
  ├─ time-aware features
  └─ immutable evaluation datasets
              |
              v
Separate VELTRIX_V2 model/evaluation/publication gates
  └─ no prediction changes or publication before certification
```

## Mandatory acceptance gates for every new source

1. **Identity:** exact competition, season, team and player identities; no fuzzy auto-merge.
2. **Temporal integrity:** UTC timestamps or explicit local-time precision; never invent a timezone.
3. **Coverage:** measured match coverage, field-level completeness, missingness by competition and season.
4. **Freshness:** compare provider timestamps and actual update delay; stale data is not current data.
5. **Consistency:** reconcile scores, kickoff, status, lineups and selected statistics against an independent qualified source.
6. **Duplicates/conflicts:** report duplicate IDs, duplicate natural keys, score conflicts, team/player identity collisions and contradictory observations.
7. **Provenance:** store provider, endpoint, retrieval timestamp, source commit/version, payload SHA-256 and transformation version.
8. **Rights:** confirm collection, caching, retention, commercial display and model-training permissions independently.
9. **Point-in-time safety:** only use information available before the prediction cutoff; post-match lineups, stats and corrections cannot leak into pre-match features.
10. **Isolation:** read-only acquisition first; isolated Neon dry-run next; production ingestion only after explicit acceptance.

## Immediate execution status

- Added `.github/workflows/openfootball-5dollar-readonly-reconciliation.yml` on the repository default branch. It is manual-only; it has no schedule trigger and no deployment step.
- Added `scripts/veltrix_v2/fetch_openfootball_5dollar_snapshots.py`. It uses the existing GitHub secret `FIVEDOLLARFOOTBALL_API_KEY` without printing it, pins the OpenFootball file to a source commit, downloads a 90-day EPL reference window, and captures the public FPL player/fixture snapshots. It records hashes and retrieval metadata and uploads an audit artifact.
- The script does not import legacy prediction modules, access Neon or modify predictions.
- **Live acquisition has not yet run.** A repository user with write access must manually trigger the workflow from the Actions tab because no workflow-dispatch action is exposed in the connected GitHub toolset.
- After the artifact is available, implement and run exact fixture-level reconciliation with an explicit team-ID crosswalk. Do not claim a pass based on successful downloads alone.
