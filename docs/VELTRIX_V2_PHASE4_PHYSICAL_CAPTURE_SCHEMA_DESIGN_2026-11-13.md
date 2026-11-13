# VELTRIX FOOTBALL 2.0 — Phase 4 Physical Capture Schema Design

**Date:** 2026-11-13  
**Status:** Reviewed schema contract with candidate migration `0004_point_in_time_feature_capture.sql`; not yet approved or applied  
**Branch:** `phase4/provider-qualification-20261113`  
**Target PR:** #67  
**Depends on:** Phase 3 PR #66 being merged before this branch is rebased or its migration is considered for application

## 1. Decision summary

The Phase 3 schema already contains the core provenance primitives. Phase 4 must extend them rather than create parallel copies.

| Requirement | Existing Phase 3 object | Phase 4 decision |
|---|---|---|
| Immutable raw provider response bytes and SHA-256 | `provider_responses` | Reuse. Do not create a second raw-payload table. |
| Parsed source observations and response linkage | `source_observations` | Reuse. It already carries source/data type, event/availability times, rights approval, schema version, response FK and the fail-closed `point_in_time_certifiable=false` default. |
| Rights evidence and scope | `source_approvals` | Reuse. Do not duplicate approval records. |
| Rights approval/revocation history | `source_approval_status_events` | Reuse. Evaluate effective status at explicit downstream-use time (`rights_evaluated_at`), separately from the prediction cutoff; never mutate the original approval. |
| Existing fixture/team/competition identities | `fixtures`, `teams`, `competitions` | Reuse as canonical history identities, but do not treat provider IDs as cross-provider identity proof. |
| Import execution and checkpointing | `import_runs`, `import_checkpoints`, `sync_watermarks` | Reuse for ingestion progress. Do not overload them as model feature snapshots. |
| Provider request attempt ledger | No dedicated request-attempt relation | Add `provider_capture_requests`. It links request intent, exact response, and capture batch. |
| Versioned provider-to-canonical entity mapping | No versioned crosswalk relation | Add `entity_crosswalk_versions`; retain ambiguous/unresolved mappings without allowing them into eligible features. |
| Frozen prediction cutoff and feature provenance | No dedicated snapshot relations | Add `feature_snapshots` and `feature_snapshot_links`. |
| Capture batch manifest | Existing `import_runs.manifest_sha256` is import-run scoped | Add `capture_manifests` for prospective capture batches and immutable coverage accounting; import-run manifest remains separate. |

**Important boundary:** the 2,496 Phase 3 records are traceable settled-result labels, not a point-in-time feature archive. This design does not upgrade them, infer missing publication timestamps, or authorize historical feature reconstruction.

## 2. Existing migration audit

Inspected the exact Phase 3 base commit `1bc80cf96526dc4d328af869c16c9a15cdc57306` and these files:

- `db/migrations/0001_persistent_foundation.sql` — base entities, fixtures/results, `source_observations`, import runs/checkpoints, reconciliation audits and schema migration history.
- `db/migrations/0002_historical_provenance.sql` — immutable `provider_responses` raw bytes + response hash; `source_approvals`; source-observation metadata; fixture result versions; ingestion quarantine; append-only triggers.
- `db/migrations/0003_source_approval_status_events.sql` — append-only approval/revocation events with effective and recorded timestamps.
- `scripts/db_migrate.py` — lexically sorted `NNNN_name.sql` manifest; SHA-256 is calculated over exact file bytes; previously applied checksum drift and migrations absent from the current manifest fail closed; each migration and history insert execute in one transaction.
- `tests/test_db_migrations.py` — existing migration filename, checksum, additive-DDL and append-only checks.

The Phase 3 objects are not interchangeable, and the current `source_observations` table is not yet temporally complete:
- `provider_responses.fetched_at` is retrieval time, not provider publication time.
- `source_observations.source_event_time` is not a substitute for source publication time.
- `source_observations.available_at` is only usable when its `availability_basis` is independently trusted and semantically appropriate.
- Migration 0002 does **not** currently provide dedicated `source_published_at`, `source_effective_at` or `recorded_at` columns, nor a preserved original timestamp string. The proposed 0004 must add these columns explicitly; do not infer publication time from `available_at`, `source_event_time` or `retrieved_at`.
- `source_observations.point_in_time_certifiable` remains false unless a future, explicit validation process proves every eligibility condition.
- `source_approvals.status` is the original approval record; later changes are represented by `source_approval_status_events`.

## 3. Proposed additive migration boundary

Proposed future filename: `0004_point_in_time_feature_capture.sql`.

The candidate SQL now exists at `db/migrations/0004_point_in_time_feature_capture.sql`. It is unmerged and unapproved for staging or production application. PostgreSQL 16/18 ephemeral CI acceptance is required before any staging consideration.

### 3.0 Required extension to existing `source_observations`

Because migration 0002 lacks dedicated source-publication/effective/recorded timestamp columns, the future 0004 must include:

- `source_published_at TIMESTAMPTZ` — nullable; null means the observation cannot pass retrospective point-in-time eligibility unless a documented archive/guarantee path is independently proven.
- `source_effective_at TIMESTAMPTZ` — nullable; semantic effective time, never a substitute for publication time.
- `recorded_at TIMESTAMPTZ` — database evidence-store commit time. Add nullable first; do not fabricate historical commit times for existing rows. Enforce non-null for new writes with a `CHECK (recorded_at IS NOT NULL) NOT VALID` constraint plus writer validation, or a separately reviewed equivalent.
- `source_timestamp_raw TEXT` — exact original source timestamp string, including original offset/precision; null only when no source timestamp was supplied.
- `source_timestamp_basis TEXT NOT NULL DEFAULT 'unknown'` with controlled values `provider_timestamp`, `archival_snapshot_timestamp`, `documented_guarantee`, `unknown`.

No backfill from `retrieved_at`, `source_event_time`, `available_at`, kickoff, or inferred date boundaries is permitted. Existing Phase 3 rows retain null publication/effective timestamps and null historical `recorded_at`; they remain ineligible. Do not backfill `recorded_at` with migration time. Existing append-only triggers continue to apply.

### 3.1 `capture_manifests`

Purpose: immutable batch-level record for a scheduled or manually initiated prospective capture window.

Proposed columns:
- `capture_manifest_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `manifest_key TEXT NOT NULL UNIQUE` — caller-generated stable idempotency key
- `manifest_sha256 CHAR(64) NOT NULL` — lowercase SHA-256 of canonical manifest bytes
- `capture_scope JSONB NOT NULL` — provider, endpoint family, competition and time-window scope; no credentials
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `requests_planned INTEGER NOT NULL CHECK (requests_planned >= 0)`

Manifest metadata is insert-only. Lifecycle state and timestamps are derived from a separate append-only `capture_manifest_events` relation; never update a manifest row to mark it complete. Checks: manifest hash format; request outcome counts and coverage are calculated from immutable request rows and captured in the terminal event.

#### Capture manifest lifecycle events

Add `capture_manifest_events`:
- `capture_manifest_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `capture_manifest_id BIGINT NOT NULL REFERENCES capture_manifests(capture_manifest_id) ON DELETE RESTRICT`
- `status TEXT NOT NULL CHECK (status IN ('PLANNED','RUNNING','COMPLETED','FAILED','PARTIAL'))`
- `event_at TIMESTAMPTZ NOT NULL`
- `reason_code TEXT NOT NULL`
- `evidence_sha256 CHAR(64)`
- `coverage_summary JSONB NOT NULL DEFAULT '{}'::jsonb`
- `recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Append-only trigger; index `(capture_manifest_id, event_at DESC, capture_manifest_event_id DESC)`. The latest event is the current state. Enforce legal transitions in a transactionally locked writer and tests (PLANNED → RUNNING → terminal; RUNNING may also end PARTIAL/FAILED). A terminal state cannot be reopened.

### 3.2 `provider_capture_requests`

Purpose: one row per outbound request attempt, including failures and retries. This is distinct from `provider_responses`, which stores only a received HTTP response.

Proposed columns:
- `capture_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `capture_manifest_id BIGINT NOT NULL REFERENCES capture_manifests(capture_manifest_id) ON DELETE RESTRICT`
- `provider TEXT NOT NULL`, `source_id TEXT NOT NULL`, `endpoint TEXT NOT NULL`
- `request_key TEXT NOT NULL` — stable, non-secret logical request identity
- `request_fingerprint CHAR(64) NOT NULL` — SHA-256 of canonical method/path/query/body excluding secrets
- `attempt_number INTEGER NOT NULL CHECK (attempt_number > 0)`
- `requested_at TIMESTAMPTZ NOT NULL`
- `response_id BIGINT REFERENCES provider_responses(id) ON DELETE RESTRICT`
- `outcome TEXT NOT NULL CHECK (outcome IN ('RESPONSE','TIMEOUT','NETWORK_ERROR','RATE_LIMITED','CANCELLED'))`
- `error_code TEXT`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Constraints/indexes:
- unique `(capture_manifest_id, request_key, attempt_number)`
- index `(provider, source_id, requested_at DESC)`
- index `(capture_manifest_id, outcome)`
- response linkage must verify provider/source consistency in the writer; if enforced in SQL, add a unique key on `provider_responses(id, provider, source_id)` and a composite FK.
- `RESPONSE` requires a non-null response FK; non-response outcomes require it null.
- Do not store authorization headers, API keys, cookies, signed URLs, or raw secrets in request parameters or fingerprints.

The referenced `provider_responses.raw_body` and `response_sha256` remain the canonical immutable raw payload evidence. No duplicate BYTEA payload table is proposed.

### 3.3 `entity_crosswalk_versions`

Purpose: append-only, versioned mapping from a provider entity identity to a canonical Veltrix identity.

Proposed columns:
- `crosswalk_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `entity_type TEXT NOT NULL CHECK (entity_type IN ('TEAM','COMPETITION','FIXTURE','PLAYER','VENUE'))`
- `provider TEXT NOT NULL`, `source_id TEXT NOT NULL`
- `provider_entity_id TEXT NOT NULL`
- `canonical_entity_key TEXT NOT NULL` — namespaced canonical key, not a display name
- `mapping_version INTEGER NOT NULL CHECK (mapping_version > 0)`
- `mapping_status TEXT NOT NULL CHECK (mapping_status IN ('PENDING','RESOLVED','REJECTED','SUPERSEDED'))`
- `valid_from TIMESTAMPTZ NOT NULL`, `valid_until TIMESTAMPTZ`
- `evidence_observation_id BIGINT REFERENCES source_observations(id) ON DELETE RESTRICT`
- `mapping_method TEXT NOT NULL` — exact provider ID, reviewed alias, authoritative cross-reference, etc.
- `confidence NUMERIC(5,4)` with range check 0–1; informational only and never a substitute for review.
- `reviewer_id TEXT` — required for RESOLVED mappings unless an explicitly approved deterministic exact-ID rule applies.
- `decision_reason TEXT NOT NULL`
- `recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Constraints/indexes:
- unique `(provider, source_id, entity_type, provider_entity_id, mapping_version)`
- index `(entity_type, canonical_entity_key, recorded_at DESC)`
- index `(provider, source_id, entity_type, provider_entity_id, mapping_version DESC)`
- valid interval check; a database trigger serializes inserts per provider identity with `pg_advisory_xact_lock` and rejects overlapping RESOLVED validity intervals, including concurrent insert attempts.
- A RESOLVED mapping must have an evidence observation and reason. Pending/rejected mappings may be stored for audit but cannot satisfy feature-link eligibility.
- Team/competition/fixture mapping must preserve gender, age group, reserve/youth status, country/competition context, home-away order and fixture time. Name similarity alone is insufficient.
- The polymorphic canonical key intentionally avoids false foreign keys across four different canonical tables. A future typed identity registry may replace it only after a separately reviewed migration.

### 3.4 `feature_snapshots`

Purpose: immutable record of a fixture-specific prediction cutoff and the exact feature-set contract used to construct a feature vector.

Proposed columns:
- `feature_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `snapshot_key TEXT NOT NULL UNIQUE` — deterministic idempotency key
- `fixture_id BIGINT NOT NULL REFERENCES fixtures(id) ON DELETE RESTRICT`
- `prediction_cutoff_at TIMESTAMPTZ NOT NULL` — frozen before feature selection
- `feature_schema_version TEXT NOT NULL`
- `model_build_id TEXT NOT NULL` — immutable model/artifact identifier; model may remain a non-production research build.
- `feature_set_sha256 CHAR(64) NOT NULL`
- `selector_version TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Constraints/indexes:
- hash format; unique `(fixture_id, prediction_cutoff_at, feature_schema_version, model_build_id, selector_version, feature_set_sha256)`; distinct model builds or exact feature payloads remain independently auditable
- index `(fixture_id, prediction_cutoff_at DESC)`
- snapshot is inserted once with frozen cutoff and schema/selector identity. Eligibility is derived from an append-only `feature_snapshot_eligibility_events` relation (defined below); never rewrite the frozen feature definition or cutoff.

#### Snapshot eligibility events

Add `feature_snapshot_eligibility_events`:
- `eligibility_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `feature_snapshot_id BIGINT NOT NULL REFERENCES feature_snapshots(feature_snapshot_id) ON DELETE RESTRICT`
- `eligibility_status TEXT NOT NULL CHECK (eligibility_status IN ('PENDING','ELIGIBLE','INELIGIBLE'))`
- `reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(reason_codes) = 'array')`
- `evidence_sha256 CHAR(64) NOT NULL`
- `recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Append-only trigger; index `(feature_snapshot_id, recorded_at DESC, eligibility_event_id DESC)`. The latest event is the current decision. An ELIGIBLE event must be emitted only after every feature link has passed validation and the complete snapshot hash has been recomputed. A later revocation or discovered integrity defect is represented by a new INELIGIBLE event, never by editing prior evidence.

### 3.5 `feature_snapshot_links`

Purpose: one row per feature key selected (or explicitly missing) in one frozen snapshot. This is the auditable join from feature value to source observation and rights evidence.

Proposed columns:
- `feature_snapshot_link_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`
- `feature_snapshot_id BIGINT NOT NULL REFERENCES feature_snapshots(feature_snapshot_id) ON DELETE RESTRICT`
- `feature_key TEXT NOT NULL` — taxonomy key, e.g. F01/F02 subfeature identifier
- `feature_status TEXT NOT NULL CHECK (feature_status IN ('PRESENT','MISSING','REJECTED'))`
- `feature_value JSONB` — canonical typed scalar/object; null for MISSING/REJECTED
- `source_observation_id BIGINT REFERENCES source_observations(id) ON DELETE RESTRICT`
- `crosswalk_version_id BIGINT REFERENCES entity_crosswalk_versions(crosswalk_version_id) ON DELETE RESTRICT`
- `source_published_at TIMESTAMPTZ`
- `source_effective_at TIMESTAMPTZ`
- `retrieved_at TIMESTAMPTZ`
- `rights_approval_id TEXT REFERENCES source_approvals(approval_id) ON DELETE RESTRICT`
- `eligibility_reason_code TEXT NOT NULL`
- `value_sha256 CHAR(64)`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Constraints/indexes:
- unique `(feature_snapshot_id, feature_key)` — a missing feature is represented explicitly, never silently omitted or encoded as zero.
- `PRESENT` requires value, source observation, crosswalk version where entity-bound, all three timestamps, rights approval and value hash.
- `MISSING`/ `REJECTED` requires null value; no synthetic zero/default value.
- index `(source_observation_id)`, `(rights_approval_id)`, `(feature_snapshot_id, feature_status)`.
- eligibility validator must verify that source publication time is trusted and <= frozen cutoff, source effective time is valid for the feature semantics, retrieval time is recorded honestly, approval is active for the use/scope at `rights_evaluated_at`, mapping is RESOLVED at cutoff, raw response hash linkage is intact, and the observation is not post-match.
- Store timestamp copies on the link as immutable selection evidence, but compare them against the referenced immutable source observation and provider response during validation. A copied timestamp alone is never proof.

## 4. Append-only and integrity policy

The eventual migration must add BEFORE UPDATE OR DELETE append-only triggers, reusing the existing `reject_immutable_history_mutation()` function, for:
- `provider_capture_requests` (if rows are inserted only after request outcome is known; otherwise use append-only request events to model lifecycle);
- `entity_crosswalk_versions`;
- `feature_snapshots`;
- `feature_snapshot_links`;
- terminal `capture_manifests` (or append-only manifest events if mutable in-progress state is required).

Use insert-only lifecycle: insert immutable manifest metadata, append PLANNED/RUNNING/terminal manifest events, insert each request attempt only after its outcome is known, insert the frozen feature snapshot and its links, then append the eligibility decision event. Derive current state from the latest event. No evidence row is updated.

All foreign keys use `ON DELETE RESTRICT`; no cascading deletion of provenance. Hashes use lowercase SHA-256 hex checks. All timestamps are timezone-aware PostgreSQL `TIMESTAMPTZ`. No feature-selection query may use `NOW()` as its cutoff; it must use the frozen snapshot cutoff supplied by the prediction orchestration layer.

## 5. Migration and rollback policy

- Migration numbering is sequential after 0003; candidate name `0004_point_in_time_feature_capture.sql`.
- The migration runner hashes exact UTF-8 file bytes and rejects checksum drift. Once applied anywhere, never edit 0004; corrections require a new forward-only migration.
- DDL is transactional under the existing runner. No destructive down migration is defined. Rollback means disable new writers/readers and leave additive evidence tables intact; schema removal is not an accepted rollback strategy.
- Before staging application: Phase 3 PR #66 must be merged; Phase 4 branch must be rebased onto the merged Phase 3 commit; migration SQL must be reviewed, linted and tested against a fresh PostgreSQL 16 database and a copy of the Phase 3 schema.
- Staging apply must use the exact dedicated staging database allowlist, direct connection string from GitHub secret, and a dry-run manifest first. Never use production credentials or production target.
- **Do not rerun the Phase 3 importer.** It is clean-database-only and the staging dataset is already populated.
- No migration application is authorized by this document. The candidate SQL is for code review and ephemeral CI only until Phase 3 is merged, Phase 4 is rebased, and a separately reviewed staging change is approved.

## 6. Required tests before any migration application

1. Exact migration manifest ordering, filename validity, byte-level SHA-256 and checksum-drift refusal.
2. Fresh PostgreSQL 16 install of 0001–0004; then upgrade from a database already at 0003.
3. FK restrict behavior and no cascade deletes.
4. Append-only UPDATE/DELETE rejection for all evidence tables.
5. Request retry identity, timeout/rate-limit/network failure rows, and response-to-provider/source mismatch rejection.
6. Raw response byte hash recomputation and request/response lineage verification.
7. Crosswalk version uniqueness, database-enforced non-overlapping RESOLVED validity intervals under concurrent inserts, ambiguous mapping exclusion, team gender/age/reserve separation, rename/merge, fixture collision, home/away order and effective-time boundary cases.
8. Frozen cutoff immutability; source publication at cutoff accepted; one millisecond after cutoff rejected; missing/naive/untrusted timestamps rejected.
9. Retrieval time never substituted for source publication time; event/effective time never substituted for publication time.
10. Rights scope and effective revocation evaluated at `rights_evaluated_at`; expired/revoked/unapproved use rejected independently of the frozen prediction cutoff.
11. Explicit missing feature remains missing and is never coerced to zero.
12. Adding a post-cutoff observation or later correction cannot alter an earlier snapshot; replay produces identical feature-set hash.
13. Snapshot hash changes when any selected feature value, observation, crosswalk version, rights evidence, schema version or selector version changes.
14. Credentials, authorization headers, cookies, API keys and secrets absent from request metadata, raw logs and artifacts.

## 7. Explicit non-goals and release gates

This design does not:
- qualify Sportmonks, Goalserve, StrikerAPI or any other provider;
- approve any feature family for training;
- create provider adapters or run paid probes;
- authorize historical point-in-time reconstruction from Phase 3 labels;
- build, train, calibrate or publish prediction models;
- unlock value bets, schedule the daily report, send Telegram messages or deploy the website;
- alter production or staging data.

Provider/field/competition rights, source publication timestamps, raw provenance, deterministic identity, and feature semantics must all be qualified before a capture adapter can write model-eligible features. Every feature remains ineligible by default. The value-betting certification gates remain unchanged.
