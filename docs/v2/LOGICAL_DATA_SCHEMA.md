# V2 Logical Data Schema and Transaction Boundaries

**Status:** Logical design only; no database engine or production storage target selected.  
**Scope:** Storage-neutral relational model plus immutable blob storage.  
**Non-goal:** This document does not authorize creating a Neon project, changing production storage or migrating V1 records.

## 1. Storage principles

1. Preserve provider source records and provider IDs permanently as provenance. Canonical identity is a separate, versioned decision layer.
2. Store exact provider response bytes in immutable, content-addressed blob storage. Persist SHA-256, byte length, media type, source reference and retention/rights metadata in the database.
3. A source record becomes visible only after the raw blob is durable and a database transaction commits its source envelope, rights evidence and ingestion-run linkage.
4. Use idempotency keys on every ingestion request, source-record insert, report publication and delivery.
5. Store timestamps as timezone-aware UTC. Keep provider-supplied timestamps separate from fetched and ingested timestamps.
6. Store canonical IDs separately from provider IDs. Do not overwrite provider IDs after a merge or redirect.
7. Keep model artifacts, training snapshots, calibration versions, forecast records, validation certificates and reports immutable and versioned.
8. Never persist API credentials in application tables. Use the hosting secret store; store only secret reference names and verification metadata.
9. Apply source-rights purpose checks before historical import, caching, training, inference and public display. A source record may be retained for audit while its use for a particular purpose remains denied.
10. Website and Telegram read the same committed report manifest. Delivery cannot precede report publication.

## 2. Logical entities

### Source and ingestion

| Entity | Key fields | Constraints / purpose |
|---|---|---|
| `source_registry` | `source_id`, provider name, source type, active state | Stable source identity; no secret values |
| `source_rights_evidence` | `source_id`, rights status, commercial flag, permitted purposes, terms URL/version, verified time, evidence SHA-256 | Append-only evidence revisions; deny by default |
| `provider_account_capability` | provider, account plan, supported competitions/data classes, history floor, verified time, evidence ref | Account-specific; marketing plan descriptions are not sufficient |
| `provider_quota_snapshot` | provider, quota scope/unit, limit, used, reserved, measured time, reset time, snapshot ID | Immutable measurements; stale snapshots cannot authorize calls |
| `provider_quota_reservation` | reservation ID, provider, scope, units, idempotency key, state, reserved/settled time | Unique idempotency key; reserve atomically before transport |
| `ingestion_run` | run ID, provider, data class, request ID, started/finished, counts, quota consumed, status | Auditable run lifecycle |
| `raw_payload_blob` | SHA-256, byte length, media type, object URI, created time | Content-addressed immutable bytes; unique digest |
| `provider_source_record` | source record ID, provider, source ID, provider record/fixture/competition/home-team/away-team IDs, data class, raw digest/ref, fetched/ingested/source-updated times | Preserve all original IDs; unique provider/source/record/revision tuple |
| `provider_record_rights_decision` | source record ID, purpose, allowed, reason code, rights evidence version, evaluated time | Immutable per-purpose decision |
| `sync_watermark` | provider, data class, scope, cursor, version, updated time | Unique provider/data-class/scope; compare-and-set advance only |

### Identity and history

| Entity | Key fields | Constraints / purpose |
|---|---|---|
| `canonical_competition` | canonical ID, name, country, squad category, active state | V2-owned canonical competition |
| `canonical_team` | canonical ID, display name, squad category, gender/age classification | Senior/women/youth/e-football separation is mandatory |
| `provider_competition_link` | provider, source, original provider competition ID, canonical competition ID, decision/version | Preserve retired IDs and redirect lineage |
| `provider_team_link` | provider, source, provider team ID, canonical team ID, squad category, decision/version | Explicitly verified mapping only |
| `canonical_fixture` | canonical fixture ID, competition/team IDs, kickoff UTC, status, identity version | Canonical fixture record |
| `provider_fixture_link` | provider, source, original provider fixture ID, canonical fixture ID, match decision, evidence | Many source records can link to one confirmed canonical fixture |
| `fixture_identity_decision` | decision ID, candidate source IDs, decision state, reason, evidence, reviewer/algorithm version | Ambiguous/unresolved records are quarantined, never silently dropped |
| `historical_match` | canonical fixture ID, completed score, kickoff UTC, squad category, source record IDs | Only completed, identity-verified, rights-cleared matches |
| `history_evidence_snapshot` | team ID, cutoff UTC, requested window, competition scope, returned match IDs, state, evidence IDs | Point-in-time history; future rows excluded |

### Features, models and forecasts

| Entity | Key fields | Constraints / purpose |
|---|---|---|
| `feature_snapshot` | fixture ID, cutoff UTC, feature schema/version, source-history IDs, content hash | Immutable; point-in-time only |
| `training_dataset_version` | dataset ID, row count, date range, source rights manifest, split definition, content hash | Frozen chronological dataset |
| `model_artifact` | model ID/version, market, algorithm, training dataset ID, training cutoff, code revision, artifact hash | No V1 model imports or V1 output-derived targets |
| `calibration_artifact` | calibration ID/version, market, model version, fit window, data hash, method | Market/model-specific; no shared default distribution |
| `forecast_candidate` | fixture, market, probabilities, model/calibration version, feature snapshot, generated time | Candidate only until market gate passes |
| `forecast_eligibility_decision` | candidate ID, allowed/withheld, reason, evidence IDs, rule version | Fail-closed and market-specific |
| `forecast_record` | forecast ID, fixture, market, probabilities, source candidate ID, release state | Immutable; no generic/global fallback |
| `market_validation_certificate` | market/model/calibration versions, walk-forward counts, prospective counts, date coverage, odds coverage, ROI/confidence bound, Brier/log loss, status | Release certificate binds exact artifacts and evidence |
| `paper_selection` | forecast ID, market, odds snapshot/bookmaker, selection timestamp, settlement/outcome, P&L | Append-only prospective evidence |

### Reports and delivery

| Entity | Key fields | Constraints / purpose |
|---|---|---|
| `report_manifest` | report ID, as-of date/timezone, content hash, schema version, created time, publication state | The single public pointer to a complete immutable report |
| `report_blob` | report ID, immutable URI, byte length, SHA-256 | Exact published report bytes |
| `report_fixture_entry` | report ID, canonical fixture ID, display state, forecast IDs, withheld reasons | Includes fixture records even when predictions are withheld |
| `delivery_outbox` | outbox ID, report ID/hash, channel, payload ref, idempotency key, created time | Created only after report manifest commit |
| `delivery_attempt` | outbox ID, attempt, channel, status, external message ID, error code, timestamps | Retryable and auditable; never mutates report |
| `publication_audit_event` | actor/process, action, report ID/hash, result, timestamp | Append-only publication trace |

## 3. Critical transaction protocols

### 3.1 Quota reservation

One database transaction must:
1. Lock or compare-and-set the current provider/scope quota snapshot.
2. Confirm the snapshot is fresh and the requested cost plus protected reserve fits.
3. Insert the reservation using a unique idempotency key.
4. Increment reserved units and commit.

On successful provider response, settle the observed actual cost and release unused reserved units. If the request may have reached the provider but consumption is unknown, conservatively settle the full reservation. Authentication/plan failures are not retried. No provider request is dispatched if reservation fails.

### 3.2 Raw source record acceptance

1. Verify source rights for the requested purpose and CACHE.
2. Validate provider/request identity, data class, provider IDs, exact-byte SHA-256 and timestamps.
3. Write raw bytes to content-addressed immutable storage and verify the stored digest.
4. In one database transaction, insert the provider source record, source-rights decisions, blob reference and ingestion-run linkage with a deterministic idempotency key.
5. Only committed source records are visible to identity/history services. Unreferenced staged blobs can be garbage-collected after a conservative grace period.

### 3.3 Identity and history

- Identity decisions are separate from raw source records and versioned.
- A provider ID redirect creates a new mapping/decision while retaining the original provider ID.
- Duplicate source records are attached as provenance to one canonical fixture only after competition, squad, home/away and kickoff evidence agrees.
- Ambiguous identities remain quarantined.
- Historical queries require canonical team ID, squad category, competition scope, date window and a strict UTC cutoff. The query must exclude kickoff timestamps greater than or equal to the cutoff.

### 3.4 Immutable report publication

1. Generate a complete report with every fixture entry and market-specific withheld reason.
2. Serialize deterministically; calculate SHA-256 and schema version.
3. Write immutable report blob and verify its digest.
4. In one transaction, commit the manifest and all report fixture references.
5. Insert website/Telegram delivery outbox events in that same transaction.
6. Consumers fetch only the manifest's report ID and verify content hash. Telegram delivery begins only after manifest commit. Retry uses the same report ID/hash and idempotency key.

This removes the V1 race where Telegram could send before website/command-data publication.

## 4. Indexes and uniqueness

- `provider_source_record(provider, source_id, provider_record_id, raw_payload_sha256)` unique.
- `provider_fixture_link(provider, source_id, provider_fixture_id, mapping_version)` unique.
- `provider_team_link(provider, source_id, provider_team_id, mapping_version)` unique.
- `sync_watermark(provider, data_class, scope)` unique.
- `provider_quota_reservation(provider, quota_scope, idempotency_key)` unique.
- `feature_snapshot(fixture_id, cutoff_utc, feature_schema_version)` unique.
- `forecast_record(fixture_id, market, model_version, feature_snapshot_id, calibration_version)` unique.
- `report_manifest(report_id)` and `report_blob(report_id)` unique; content hash indexed.
- `delivery_outbox(report_id, content_hash, channel, idempotency_key)` unique.

## 5. Storage selection gate

No engine is selected yet. Selection requires:
- Phase 1 V1 source/artifact reconciliation and independently verified backup/restore.
- Verified provider data rights, account plan, history depth, rate/credit limits and attribution.
- Forecast/report data volume estimate and retention policy.
- Hosting connection limits, serverless transaction behavior, object-storage availability and total cost.
- Isolated V2 credentials, branch/schema and restore test.
- Proof that the storage adapter can satisfy atomic quota reservation, source-record idempotency, watermark compare-and-set and report-manifest publication.

The existing inspected Neon projects are not V2 football storage and remain excluded.
