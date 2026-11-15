# VELTRIX 2.0 — OpenPlay staging feature pipeline

**Date:** 2026-11-15  
**Scope:** PR #120, integration branch only  
**Execution mode:** staging read-only feature extraction  
**Rights:** non-commercial use only; monetisation prohibited

## Pinned release and schema

The pipeline reads the pinned OpenPlay data-v0.1.0 release at commit
ac0bd9aff52016066433ebebf818bec4278fcf54. The ten Parquet assets contain
2,975,394 rows in total. The six row-level match feature tables contain
2,927,621 rows:

| Asset | Rows |
|---|---:|
| player_match_stats.parquet | 775,994 |
| lineups.parquet | 1,068,162 |
| shots.parquet | 669,404 |
| formations.parquet | 245,468 |
| cards.parquet | 115,499 |
| team_match_stats.parquet | 53,094 |

The remaining Parquet assets are matches.parquet (26,547), players.parquet
(20,782), teams.parquet (422) and competitions.parquet (22).

## Staging evidence contract

The builder reads the raw release bytes from staging provider_responses and
validates each linked source_observations record before extracting any
features. It verifies the raw SHA-256, payload SHA-256, exact response link,
release commit, asset set, rights approval and non-PIT asset classification.

For each match it retrieves the exact match_result_snapshot observation and
uses its persisted source_published_at, available_at and actual VELTRIX
recorded_at. It checks the page-save timestamp against the documented
matches.scraped_at semantics and the pinned data-dictionary evidence hash.
The recording timestamp is never inferred from the source page timestamp.

Only currently valid, evidence-backed RESOLVED mappings are accepted:
- Team mappings must use EXACT_NAME_AND_COMPETITION_OVERLAP and cite the
  pinned teams.parquet asset observation.
- Competition mappings must use EXPLICIT_REGION_NAME_ALIAS and cite the
  pinned competitions.parquet asset observation.
- Missing, pending, rejected, expired, ambiguous or unsupported mappings are
  excluded; no names or IDs are guessed.

The current staging inventory has 89 resolved team mappings and five resolved
competition mappings. Before feature-quality exclusions, 10,110 match records
have both teams and their competition mapped.

## Bounded-memory extraction and quarantine

scripts/veltrix_v2/build_openplay_feature_bundle.py writes the pinned assets
to a temporary directory one response at a time. DuckDB scans the Parquet files
and yields ordered match groups in bounded batches. Python retains only one
match's rows at a time and calls the already-tested
veltrix_v2/data/openplay_features.py adapter for that match.

The builder excludes:
- Matches outside the pinned v1 competition-season scope.
- Matches whose event score does not reconcile.
- Match IDs in known_gaps.csv or data_issues.csv.
- Matches without a persisted, valid staging snapshot.
- Matches without exact resolved team and competition mappings.
- Every row in a duplicated natural-key group for player, lineup, shot, card
  and formation tables.
- The entire match if any team-match-stat natural key is duplicated.

The duplicate audit counts are retained in the bundle manifest. No duplicate
row is silently selected as the winner.

## Point-in-time eligibility

Each output row preserves:
- Provider match/team/opponent IDs and canonical team/opponent/competition IDs.
- The exact source publication/page-save timestamp, available timestamp and
  actual VELTRIX recording timestamp.
- The OpenPlay xG model ID.
- The match snapshot observation ID, raw provider response ID and payload hash.
- The raw asset response/observation IDs and SHA-256 hashes.
- All three crosswalk version IDs, evidence observation IDs, validity windows
  and recording timestamps.
- The rights approval ID, evidence hash, attribution and feature hashes.

The row's eligibility_at is the maximum of the source publication,
availability and VELTRIX recording clocks, the approval's effective/recorded/
valid-from clocks, and the team, opponent and competition crosswalk
valid-from/recorded clocks.

A feature is selectable only when the evaluation cutoff is strictly later
than every required clock, all mappings and approval remain valid, and the
source match date is strictly earlier than the target fixture date. Same-day
features are excluded because the archive does not provide a canonical kickoff
timestamp for every source match. Consequently, these post-match statistics
cannot be used to predict their own match or any earlier historical cutoff.

## Output and evaluation exposure

The workflow produces:
- openplay_team_match_features.jsonl: derived feature rows with row-level
  SHA-256 and complete provenance.
- openplay_feature_bundle_manifest.json: bundle digest, asset hashes,
  exclusions, duplicate quarantine counts, mapping counts, rights and temporal
  rules.

The JSONL loader verifies the manifest digest, every row hash, source assets,
crosswalk evidence, approval and non-commercial restrictions before yielding
rows. walk_forward_evaluate(..., openplay_features=...) accepts this verified
iterator and reports only the strictly eligible home/away feature context for
each chronological cutoff.

**Important model boundary:** this first integration exposes validated
OpenPlay context to chronological evaluation but does not yet feed it into the
baseline Poisson probabilities. A feature-aware challenger must be trained and
walk-forward validated separately before any model or publication decision
changes.

## Rights and release controls

- Non-commercial use only; monetisation is prohibited.
- Attribution: openplay (Noah Bair).
- Raw Parquet and CSV assets remain in staging and are not uploaded as workflow
  artifacts. The workflow artifact contains derived features and non-raw audit
  evidence only.
- The builder performs zero Neon writes.
- No production database changes, PR merge, Vercel deployment, schedule
  activation, Telegram delivery, prediction publication or value-bet unlock.
