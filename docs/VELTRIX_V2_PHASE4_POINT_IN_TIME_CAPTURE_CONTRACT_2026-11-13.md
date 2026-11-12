# VELTRIX FOOTBALL 2.0 — Point-in-Time Feature Capture Contract

**Assessment date:** 2026-11-13  
**Status:** Architecture specification only — no migrations or ingestion jobs authorized by this document  
**Parent work:** Phase 4 provider qualification

## 1. Objective

Define a provider-neutral contract for collecting football observations without look-ahead leakage. The contract must support both prospective capture and independently evidenced historical snapshots.

The system must answer, for every feature used by a frozen prediction:

> What exact value was used, which source supplied it, when did the source make that value available, when did VELTRIX retrieve it, what version was it, and what evidence proves it was available by the prediction cutoff?

If any required answer is missing, the observation is not eligible for pre-match modelling.

## 2. Time semantics — never collapse these fields

| Timestamp | Meaning | Rule |
|---|---|---|
| `event_at` | Time the underlying football event occurred (e.g. kickoff, shot, injury) | Not automatically the time a model could know it |
| `source_published_at` | Time the provider says this exact value/version became available to customers | Required for retrospective point-in-time eligibility unless a documented provider guarantee supplies an equivalent |
| `source_effective_at` | Time interval the value describes (e.g. injury status effective from) | Does not prove publication/availability |
| `retrieved_at` | UTC time VELTRIX received the exact response bytes | Always recorded by VELTRIX; never substituted for source publication time |
| `prediction_cutoff_at` | Frozen UTC information cutoff for a fixture/prediction | Immutable after prediction creation |
| `recorded_at` | Time the observation/version was committed to VELTRIX's evidence store | Internal audit time; append-only |

All timestamps are UTC, timezone-aware and stored at the highest precision the source provides. Preserve the original timestamp string and timezone offset in raw evidence. Do not silently convert date-only values into midnight timestamps.

## 3. Logical data model

The following is a logical contract, not a migration request. Physical table names may be adapted after inspecting the Phase 3 schema, but the semantics and constraints are mandatory.

### 3.1 `provider_request`

One row per outbound provider request:
- `request_id` — immutable internal UUID.
- `provider_id`, `product_id`, `endpoint`, `http_method`.
- `request_parameters_redacted` — canonical parameters with keys/tokens/secrets removed.
- `request_fingerprint_sha256` — hash of canonical redacted request identity.
- `requested_at`, `retrieved_at`, `http_status`, `response_content_type`.
- `raw_response_sha256`, `raw_response_byte_length`.
- `capture_run_id`, `rate_limit_metadata_redacted`.
- `error_class`, `error_detail_redacted` for failed requests.

No credential, authorization header, signed URL or secret query parameter may be persisted in request metadata or logs.

### 3.2 `raw_payload`

Immutable response-byte archive:
- `raw_response_sha256` primary key.
- Exact unmodified response bytes (or immutable object-store key plus verified byte length).
- `content_encoding`, `content_type`, `byte_length`, `stored_at`.
- Optional decoded text is a convenience copy only; hash is calculated from original response bytes.

A repeated response with identical bytes may reference the same content hash, but each request remains a separate request record. Never hash normalized JSON in place of raw bytes.

### 3.3 `source_observation`

One row per provider entity/version/field observation:
- `observation_id` immutable UUID.
- `provider_id`, `product_id`, `endpoint`, `request_id`, `raw_response_sha256`.
- `provider_entity_type`, `provider_entity_id`, `field_path`.
- `value_type`, `value_json`, `unit`, `currency` where relevant.
- `event_at`, `source_effective_at`, `source_published_at`.
- `retrieved_at`, `recorded_at`.
- `source_revision_id`, `supersedes_observation_id`.
- `availability_basis`: `provider_timestamp`, `archival_snapshot_timestamp`, `documented_guarantee`, or `unknown`.
- `availability_evidence_ref`, `rights_approval_id`.
- `is_tombstone` for an explicit provider withdrawal/deletion signal.

Every correction creates a new observation and points to the superseded version. No UPDATE-in-place of a historical value. Unknown publication time stays NULL with `availability_basis='unknown'`.

### 3.4 `entity_crosswalk_version`

Append-only mapping between provider IDs and VELTRIX canonical IDs:
- `provider_id`, `entity_type`, `provider_entity_id`, `canonical_entity_id`.
- `valid_from`, `valid_to` if supplied by the source.
- `recorded_at`, `mapping_method`, `confidence`, `evidence_ref`.
- `supersedes_mapping_id`, `review_status`.

Do not map teams by name alone. Ambiguous, merged, renamed, gender/age-category-confused or reserve-team identities are quarantined until manually evidenced. Preserve prior mappings.

### 3.5 `rights_approval`

Use-scoped approval record:
- Provider/product, endpoint, field family, competition and season scope.
- Permitted purposes: collection, retention, internal analysis, model training, derived outputs, public display, attribution and redistribution — each separately recorded.
- Terms version/hash, accepted-at date, evidence file/hash, expiry/review date.
- Approval state: pending, approved, suspended, revoked.
- Revocation is append-only; ingestion and downstream use must fail closed when approval is absent or revoked.

### 3.6 `prediction_snapshot` and `prediction_feature_link`

A frozen prediction snapshot records:
- Fixture canonical ID and provider fixture crosswalk version.
- `prediction_cutoff_at`, model/build identifier, feature-spec version.
- Exact input feature-set hash and creation timestamp.
- Frozen output and market probabilities, if/when model work is authorized.

Each feature link references the exact `observation_id` and records the eligibility decision/reason. Recomputing a prediction must create a new snapshot; never mutate the original.

## 4. Eligibility decision

An observation is eligible for a pre-match feature only if all conditions hold:

1. The provider/product/endpoint/field/competition/season is covered by an active rights approval for model training.
2. Provider entity identity is deterministically mapped to the target fixture/team/player; ambiguous joins are quarantined.
3. The observation has a trustworthy `source_published_at`, archival snapshot timestamp, or documented provider guarantee that proves the exact value/version was available.
4. Proven source availability is less than or equal to the frozen `prediction_cutoff_at`.
5. The observation's value is semantically valid for the feature and its event/effective interval does not introduce post-cutoff information.
6. No later correction/revision known by the cutoff supersedes the selected version.
7. Raw response bytes, hash, request record and source rights evidence are all resolvable.

`retrieved_at <= prediction_cutoff_at` is sufficient evidence for a prospective capture only when the response was actually captured before cutoff. If a historical archive is acquired later, a later `retrieved_at` does not automatically disqualify it, but it must have a trustworthy source publication/snapshot timestamp proving availability before cutoff and preserved revision history. A provider's undocumented claim that a field is historical is insufficient.

The selector must choose the latest eligible version known by the cutoff, not the latest version currently in the database. A current corrected value must never leak backwards into earlier folds.

### Fail-closed reason codes

- `RIGHTS_NOT_APPROVED`
- `SOURCE_TIMESTAMP_MISSING`
- `SOURCE_TIMESTAMP_UNTRUSTED`
- `PUBLISHED_AFTER_CUTOFF`
- `RETRIEVED_AFTER_CUTOFF_WITHOUT_ARCHIVE_PROOF`
- `ENTITY_MAPPING_AMBIGUOUS`
- `REVISION_HISTORY_INCOMPLETE`
- `RAW_EVIDENCE_MISSING`
- `FIELD_SEMANTICS_UNVERIFIED`
- `COMPETITION_OR_SEASON_OUT_OF_SCOPE`

No generic fallback, imputed timestamp or guessed value may turn a rejected observation into an eligible one.

## 5. Odds-specific contract

Every odds observation must include:
- bookmaker/provider bookmaker ID and canonical bookmaker mapping;
- event ID and canonical fixture ID;
- market key, period, selection, handicap/total line and selection parameters;
- decimal price, suspended/active state and currency/locale where applicable;
- exact source quote/snapshot timestamp and availability basis;
- raw response hash, retrieval timestamp and source revision.

Opening, closing and intermediate quotes are separate observations. A closing price is not automatically available at the 06:00 prediction cutoff. Do not substitute `last_update`, local fetch time or match kickoff for a quote timestamp unless the provider's documentation explicitly defines that field as the quote's availability timestamp.

The 98% timestamped odds gate denominator is all eligible fixture × selected bookmaker × market observations in the declared evaluation universe. Report missing quotes, missing timestamps and unavailable markets separately; do not drop missing rows from the denominator.

## 6. Prospective capture protocol

When a provider is approved:
1. Freeze the fixture universe and canonical IDs for the capture run.
2. Record a UTC cutoff for each fixture; for the daily 06:00 WAT report, store both local schedule time and resolved UTC instant.
3. Capture each selected provider endpoint before cutoff with bounded request budgets and rate-limit-aware pacing.
4. Archive exact response bytes and request metadata before parsing.
5. Parse to append-only observations; preserve nulls, unknown timestamps and provider revisions.
6. Run schema, identity, rights and timestamp validation.
7. Generate a signed/hash-bound capture manifest listing included, rejected and missing observations.
8. Freeze feature links and prediction inputs; do not mutate after publication.
9. Later, ingest final results into a separate label lane and settle snapshots without changing their original feature inputs.

A capture failure must produce an explicit missing-data record, not a synthetic feature value.

## 7. Validation tests required before implementation is accepted

- Raw-response SHA-256 recomputation matches stored bytes.
- Every observation resolves to exactly one request and raw payload.
- No credential or secret appears in request metadata, artifacts or logs.
- Timestamp parser preserves offsets and rejects invalid/date-only timestamps for cutoff use.
- A synthetic post-cutoff publication is always rejected.
- A historical snapshot with a valid pre-cutoff publication timestamp but later retrieval is accepted only under the documented archive proof rule.
- A later correction does not alter an earlier cutoff's selected value.
- A missing publication timestamp fails closed.
- Ambiguous team/fixture mapping is quarantined.
- Revoked rights approval blocks future selection and publication.
- Odds quote timestamp is distinct from retrieval and kickoff timestamps.
- Feature-set hash is stable for identical ordered observations and changes on any input/version change.
- Chronological walk-forward query cannot select any observation published after its fold cutoff.

## 8. Explicit non-goals

This contract does not:
- build or reuse any prediction model;
- turn the 2,496 Phase 3 results into pre-match features;
- assert any unqualified provider has acceptable rights or timestamps;
- enable production ingestion, paid subscriptions, model training, Telegram publication or scheduling;
- authorize value betting.

Implementation starts only after provider qualification identifies the exact approved endpoints and use rights. Physical database design must be reconciled against the existing Phase 3 staging schema before migrations are proposed.
