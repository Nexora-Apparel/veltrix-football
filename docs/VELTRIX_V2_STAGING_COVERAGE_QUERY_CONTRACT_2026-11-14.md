# VELTRIX 2.0 — Read-only staging coverage query contract

Date: 2026-11-14
Database: dedicated Neon staging branch only

## Exact schema alignment

The coverage SQL is based on the inspected PostgreSQL schema, not assumed column names.

- `fixtures.id` and `fixtures.competition_id` are BIGINT; the query casts them to text for stable canonical identity transport.
- `fixtures.source_observation_id` links the imported fixture to its source observation.
- `source_observations` contains provider, source_id, data_type, payload hash, available_at, recorded_at, rights_approval_id, payload JSONB, point_in_time_certifiable, source_published_at and source_effective_at.
- `recorded_at` and `source_published_at` are nullable and must remain missing when absent.
- The observation's payload retains the provider's original response fields. Imported 5Dollar rows do not contain the new capture-manifest rights decision fields.

## Query contract

The fixture query returns:
- fixture_id
- competition_id
- kickoff_at

The observation query inner-joins through the exact `fixtures.source_observation_id = source_observations.id` relationship and returns:
- canonical fixture_id and competition_id from the fixture row
- fixture_kickoff_at
- provider, source_id, data_type and payload_sha256
- available_at and recorded_at
- rights_approval_id and immutable payload
- point_in_time_certifiable
- source_published_at, source_effective_at and availability_basis

Both SQL templates are SELECT-only and include a guard against mutating SQL. The caller must use a read-only DB role. The Python adapter opens no connection and does not execute SQL.

## Current staging result

The exact fixture query returned 2,496 rows. The exact observation join returned 2,496 linked rows.

The inspected imported records show:
- all 2,496 have `available_at`;
- zero have `recorded_at`;
- zero have `source_published_at`;
- zero have point-in-time certification;
- all 2,496 have a rights approval ID, but none has the newer capture-time rights decision fields in its immutable payload.

Consequently the adapter must reject all 2,496 historical rows for strict coverage. A non-null approval ID is not proof that rights were approved for collection, storage and model training at the required use time. The four-day availability proxy is not provider publication time or a per-record source availability timestamp.

## Safety

No staging data was changed. No provider request, credential read, credit use, schema migration, production write, deployment, schedule activation, Telegram activation or publication occurred.


## Prospective capture selection update (2026-11-14)

The observation query now uses a read-only `LEFT JOIN LATERAL` selector. For each canonical fixture it considers:
- The original `fixtures.source_observation_id` link.
- New manifest-linked `fixture_result` observations whose payload `fixture_id` equals the canonical fixture ID.

Manifest-linked observations are preferred, then the newest `recorded_at`, then the highest observation ID. This exposes newly captured evidence to the coverage auditor without mutating the fixture's original source-observation link. It does not promote first-observed results to PIT-certified history; the point-in-time and rights checks remain unchanged.
