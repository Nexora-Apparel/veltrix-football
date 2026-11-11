# Historical source coverage qualification

## Purpose

`app.historical_source_coverage.build_historical_source_coverage_report` measures whether settlement-admitted historical records have sufficient source, competition, team and feature coverage for later evaluation. The report is attached to the audited provider dataset pipeline as `source_coverage`.

It is a fail-closed screening report, not proof of model quality, a source licence review, or authorization to train or publish.

## Measurements

- Settlement eligible and rejected record counts and eligibility rate.
- Accepted record counts by provider and settlement source.
- Per-competition eligible fixtures, included dataset rows, feature snapshots, distinct teams and distinct kickoff dates.
- Per-team fixture appearances within each competition.
- Per-feature dataset coverage and feature-source/source-ID counts.
- Explicit domain coverage for team strength/form, xG, lineups, fatigue/travel and bookmaker odds.
- Explicit absence of injury availability and PPDA when those features are not in the point-in-time feature catalogue.
- Historical feature-availability status.

Dataset rows must join to an admitted fixture, the same competition, and the exact retained feature snapshot digest. Predictor values must equal the snapshot values. A mismatch aborts report generation.

## Season identity limitation

The normalized acquisition record already retains a provider-reported `season` value where supplied. The eligibility audit now carries that value forward as `source_season`. The report distinguishes missing season labels from source-reported labels that still lack a reviewed canonical competition-season crosswalk. It does not infer seasons from calendar years, league schedules or kickoff dates. Even complete source-reported labels remain unqualified until an explicit crosswalk is reviewed and verified.

A future qualification step must bind each provider/competition/source-season label to a canonical season ID, with source provenance and review evidence. Until that crosswalk exists, `season_crosswalk_unverified` blocks source qualification.

## Screening thresholds

Defaults are 100 settlement-eligible fixtures per competition, 16 distinct teams per competition and 95% feature-cell coverage. They are configurable screening thresholds only. They are not model-training sample-size guarantees, market certification criteria, or evidence of predictive performance.

Historical feature availability must separately be set by an evidence-backed pipeline proof. A retrospective download is not sufficient. The current pipeline deliberately reports it as unproven.

## Safety

The report never trains, calibrates, certifies, publishes, enables value betting, writes to a database, or sends Telegram messages. Even if coverage thresholds are met, `training_authorized`, `value_betting_enabled` and `publication_allowed` remain false.

Current real-source status: no production settlement source has been qualified, no real historical dataset has passed admission, and no season coverage is verified.
