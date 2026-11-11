# Historical source coverage qualification

## Purpose

`app.historical_source_coverage.build_historical_source_coverage_report` measures whether settlement-admitted historical records have sufficient source, competition, team and feature coverage for later evaluation. The report is attached to the audited provider dataset pipeline as `source_coverage`.

It is a fail-closed screening report, not proof of model quality, a source licence review, or authorization to train or publish.

## Measurements

- Settlement eligible and rejected record counts and eligibility rate.
- Accepted record counts by provider and settlement source.
- Per-competition eligible fixtures, included dataset rows, feature snapshots, distinct teams and distinct kickoff dates.
- Per-canonical-season eligible fixtures, canonical teams, distinct WAT kickoff dates, feature snapshots, dataset rows and per-feature coverage.
- Per-team fixture appearances within each competition.
- Per-feature dataset coverage and feature-source/source-ID counts.
- Explicit domain coverage for team strength/form, xG, lineups, fatigue/travel and bookmaker odds.
- Explicit absence of injury availability and PPDA when those features are not in the point-in-time feature catalogue.
- Historical feature-availability status.

Dataset rows must join to an admitted fixture, the same competition, and the exact retained feature snapshot digest. Predictor values must equal the snapshot values. A mismatch aborts report generation.

## Competition-isolated team history

The results reconstruction layer now restricts team form, Elo updates and
competition scoring baselines to the target fixture's exact competition ID.
A canonical team ID appearing in another competition is not sufficient to
make that competition's matches eligible history. Cross-competition borrowing
remains disabled until a separately evaluated competition-strength adjustment
and cross-competition history policy exist. If the target competition lacks
enough pre-cutoff history, the target is withheld rather than filled from a
different competition.

This is intentionally conservative. It prevents domestic-league results,
cups and unrelated competition formats from being silently pooled into the
same raw rates or Elo scale.

## Source-season preservation

The normalized acquisition record retains the provider-reported `season` value where supplied. The eligibility audit carries it forward as `source_season`; the normalized record and raw provider payload remain hash-bound. Missing season labels are never inferred from calendar years, league schedules or kickoff dates.

## Signed canonical season crosswalk

`app/canonical_season_crosswalk.py` defines a KMS-signed registry for exact
provider + competition ID + source-season label mappings to canonical season
IDs. Each mapping binds evidence SHA-256 digests, reviewer, review timestamp,
validity interval and optional revocation timestamp. The registry signature is
verified only through explicitly injected out-of-band KMS clients. A key ARN
inside the signed registry cannot introduce a trust anchor.

The dataset adapter now requires this registry. For every target, it verifies
the registry at that fixture's own feature cutoff, resolves the exact
(provider, competition, source-season) identity, and resolves historical
candidates at the same cutoff. Only history mapped to the target's canonical
season can contribute to its features. Missing, expired, revoked, ambiguous,
out-of-scope or retrospectively issued mappings withhold the target. No
cross-season borrowing is allowed.

Each feature snapshot includes the original source-season label, canonical
season ID, registry digest, signer ARN, verification timestamp, reviewer and
review-evidence digests inside its immutable snapshot hash. The coverage
builder re-verifies this evidence against the signed registry at the snapshot's
own cutoff, rather than relying only on the report-wide evaluation timestamp.
A signed registry does not make the underlying evidence factually correct;
reviewer evidence still requires independent governance review.

Synthetic fake-KMS tests validate the contract only; no production season
crosswalk or signing key has been configured.

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

Defaults are 100 settlement-eligible fixtures per competition, 16 distinct teams per competition and 95% feature-cell coverage. The same default screening minima are applied independently to each canonical season: 100 fixtures, 16 canonical teams and 95% coverage for every catalogue feature. Per-season reporting also counts distinct kickoff dates in WAT (UTC+1). These are configurable screening thresholds only. They are not model-training sample-size guarantees, market certification criteria, or evidence of predictive performance. Competition and season results are reported separately; a large competition total cannot conceal an under-covered individual season.

Historical feature availability must separately be set by an evidence-backed pipeline proof. A retrospective download is not sufficient. The current pipeline deliberately reports it as unproven.

## Safety

The report never trains, calibrates, certifies, publishes, enables value betting, writes to a database, or sends Telegram messages. Even if coverage thresholds are met, `training_authorized`, `value_betting_enabled` and `publication_allowed` remain false.

Current real-source status: no production settlement source has been qualified, no real historical dataset has passed admission, and no season coverage is verified.
