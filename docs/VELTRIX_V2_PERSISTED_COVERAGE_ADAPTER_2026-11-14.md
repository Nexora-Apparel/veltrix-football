# VELTRIX 2.0 — Persisted coverage adapter

Date: 2026-11-14

## Purpose

The read-only adapter converts normalized fixture rows and persisted source-observation rows into the typed inputs consumed by the competition coverage auditor. It performs no database connection, SQL execution, provider request, rights lookup or timestamp inference.

## Required query aliases

Fixture rows:
- fixture_id
- competition_id
- kickoff_at

Observation rows:
- provider
- source_id
- data_type
- payload_sha256
- available_at
- recorded_at
- rights_approval_id
- payload (JSONB mapping or JSON text)

The JSON payload must explicitly contain:
- canonical fixture_id and competition_id
- rights_approved as a real boolean
- rights_evaluated_at as a timezone-aware timestamp
- rights_evidence_sha256
- point_in_time_certifiable as a real boolean

No rights status is inferred from the aggregate point-in-time flag. Legacy persisted rows without explicit rights decision evidence are rejected from coverage eligibility.

## Supported data-type mapping

- fixture_result / result → RESULTS
- fixture → FIXTURES
- expected_goals → EXPECTED_GOALS
- lineup → LINEUPS
- injury → INJURIES
- player_stat → PLAYER_STATS
- odds_1x2 → ODDS_1X2
- odds_totals → ODDS_TOTALS
- odds_btts → ODDS_BTTS

Unknown types are reported separately, never coerced into a nearby domain.

## Rights provenance

Provider evidence capture now records the explicit rights decision and evaluation timestamp alongside the approval identity and evidence hash. The rights flag is true only if collection, storage and model-training use checks pass and approval identity/scope/evidence checks are clean. The evaluation timestamp is the exact capture-recording instant at which those checks are executed.

The append-only persistence writer stores these fields inside the immutable observation payload. Existing staging PostgreSQL integration tests assert that the rights decision and evidence survive persistence.

## Safety

- The adapter is pure and read-only.
- Missing or malformed fields are rejected.
- No inference from retrieval time, provider identity, registry state or point-in-time flag.
- No production writes, migrations, provider calls, credit consumption, deployment or publication.
