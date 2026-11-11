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

## Signed canonical season crosswalk

`app/canonical_season_crosswalk.py` defines a KMS-signed registry for exact
provider + competition ID + source-season label mappings to canonical season
IDs. Each mapping binds evidence SHA-256 digests, reviewer, review timestamp,
validity interval and optional revocation timestamp. The registry signature is
verified only through explicitly injected out-of-band KMS clients. A key ARN
inside the signed registry cannot introduce a trust anchor.

The coverage builder accepts the registry, trusted clients and an explicit
evaluation timestamp. Every accepted record must resolve using its exact
provider, competition and unmodified source-season label. Missing, ambiguous,
expired, revoked or out-of-scope mappings remain unverified. A signed registry
does not make the underlying evidence factually correct; reviewer evidence
still requires independent governance review.

The audited dataset pipeline can pass this registry into coverage reporting.
Without it, source-reported season labels remain unverified. Synthetic fake-KMS
tests validate the contract only; no production season crosswalk or signing key
has been configured.

## Signed canonical team identity crosswalk

`app/canonical_team_crosswalk.py` defines a separate KMS-signed registry
mapping exact provider + competition + source-team IDs to canonical team IDs.
Each mapping carries a reviewed evidence digest, reviewer, review timestamp,
validity interval, revocation timestamp and an explicit team scope:
men's first team, women's first team, men's reserve, women's reserve, men's
youth, women's youth or other.

The registry rejects duplicate source identities and any canonical team ID
reused across incompatible team scopes. The coverage report distinguishes
source-team IDs from canonical teams. It does not report a verified distinct
team count or pass the team-coverage threshold until every accepted home/away
team identity in that competition resolves through the trusted crosswalk.
Unknown aliases, missing IDs and incomplete mappings remain unverified.

The crosswalk signature is checked against out-of-band KMS clients. The
signature establishes registry integrity and trusted issuance, not the truth
of a team's identity; mapping evidence and reviewer decisions still require
independent review. Synthetic fake-KMS tests do not qualify real team IDs.

## Signed feature-source qualification

`app/feature_source_qualification.py` defines a KMS-signed registry of
feature-source contracts. Each source entry explicitly lists qualified feature
names, supported competitions, observation and availability timestamp
semantics, qualification evidence digests, reviewer, qualification timestamp,
validity interval and optional revocation timestamp.

The point-in-time dataset adapter verifies this registry at each target's
feature cutoff. A source qualification issued after that cutoff cannot
retroactively admit the historical snapshot. Each feature cell carries the
registry digest, signer ARN, verification timestamp, timestamp semantics and
evidence digests. The coverage report re-verifies the same signed registry
against each snapshot and rejects missing, changed, revoked, expired or
out-of-scope qualifications.

This qualification establishes a reviewed source contract and provenance
binding, not the factual correctness of feature values or historical
availability. Source evidence and licensing still require independent review.
Synthetic fake-KMS tests do not qualify any real feature source.

## Screening thresholds

Defaults are 100 settlement-eligible fixtures per competition, 16 distinct teams per competition and 95% feature-cell coverage. They are configurable screening thresholds only. They are not model-training sample-size guarantees, market certification criteria, or evidence of predictive performance.

Historical feature availability must separately be set by an evidence-backed pipeline proof. A retrospective download is not sufficient. The current pipeline deliberately reports it as unproven.

## Safety

The report never trains, calibrates, certifies, publishes, enables value betting, writes to a database, or sends Telegram messages. Even if coverage thresholds are met, `training_authorized`, `value_betting_enabled` and `publication_allowed` remain false.

Current real-source status: no production settlement source has been qualified, no real historical dataset has passed admission, and no season coverage is verified.
