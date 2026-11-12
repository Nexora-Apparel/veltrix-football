# VELTRIX FOOTBALL 2.0 — Phase 3: Traceable Data Pipeline

**Status:** IN PROGRESS — provenance contracts, append-only source evidence, entitlement gates, explicit competition scoping, immutable approval revocation, monotonic checkpoints and PostgreSQL 16/18 acceptance are implemented in this branch. No Neon migration or historical import has been executed.

## 1. Pipeline invariants

1. Every provider request is represented by a ProviderResponse with exact response bytes, SHA-256, endpoint, request ID, sanitized request parameters/headers, HTTP status and provider fetch timestamp.
2. Every parsed fixture/result is linked to its provider response and source approval. The canonicalized fixture payload hash is distinct from the exact full-response hash.
3. Provider entitlement is observed from a successful, timestamped provider response. Imports are limited to competition IDs returned by the active entitlement snapshot.
4. Source rights are explicit, purpose-scoped and competition-scoped. Wildcard competition approvals are rejected by the import evaluator.
5. Provider observations and result versions are append-only. Conflicting fixture identity or settled scores are quarantined; prior canonical results are not overwritten.
6. Every import run records a bounded request budget, counts, manifest hash, status and timestamps. Checkpoint counters cannot regress, and terminal checkpoints cannot be rewritten.
7. Sync watermarks use optimistic version checks; stale writers cannot move a cursor backwards.
8. No raw provider key, authorization header, cookie, token or secret-bearing request parameter may be persisted.
9. A historical result's availability timestamp must carry its evidence basis. The 5Dollar four-day post-kickoff proxy is explicitly point_in_time_certifiable=false; it is not a historical publication timestamp and cannot be used as a feature-availability claim.

## 2. Current implementation

### 2.1 Source-rights and provider entitlement

- The 5Dollar approval is now scoped to the exact seven verified competition IDs: 3118717965, 522514093, 4160026622, 3614399544, 686337048, 3405541143, 4212821298.
- competition_scope="*" and any wildcard-containing scope are rejected. The approval's comma-separated scope is checked against each fixture's provider competition ID.
- Entitlement snapshots are linked to the exact successful provider response from which the plan, rate limit and competition catalogue were observed.
- Migration 0003_source_approval_status_events.sql adds append-only APPROVED / REVOKED events with evidence URI, SHA-256, effective timestamp and reason code. A revocation does not mutate or erase the original approval. The writer checks the effective status as of the provider response's fetch time and quarantines records acquired after a revocation becomes effective.
- Reusing an approval ID with any changed rights field is rejected; idempotency now compares the complete approval record, not only a subset of columns.

### 2.2 Raw responses, observations and results

- Migration 0002_historical_provenance.sql stores exact provider response bytes and a full-response SHA-256.
- Parsed fixture payloads are stored as canonical JSON with a separate payload SHA-256 and a foreign key to the raw provider response.
- Every result observation creates an immutable result-version record. A different score for an existing canonical result is quarantined for reconciliation rather than silently overwriting the prior score.
- Request parameters and response headers are recursively checked for secret-bearing keys before any database connection is opened.
- Only successful HTTP 200 responses are accepted by the response contract; failed provider responses are not treated as valid source evidence.

### 2.3 Import accounting and recovery

- Import runs enforce request budgets and terminal record accounting.
- Checkpoints enforce nonnegative, fully accounted counts; counters and request usage may not decrease on replay.
- A checkpoint in COMPLETED or FAILED state is terminal and cannot be rewritten.
- Sync watermarks use an expected-version compare-and-swap operation.
- The PostgreSQL acceptance harness covers idempotent page replay, changed-score quarantine, unentitled competition quarantine, suspended entitlement, altered approval replay, approval revocation, append-only mutation rejection, checkpoint terminal rewrite rejection and stale watermark rejection.

## 3. Migration state and database safety

The migration set is additive:
- 0001_persistent_foundation.sql — existing persistent foundation.
- 0002_historical_provenance.sql — source approvals, exact provider responses, entitlement observations, provenance columns, result versions, run/checkpoint accounting, sync watermarks and quarantine.
- 0003_source_approval_status_events.sql — append-only approval status and revocation evidence.

The production Neon database has not been migrated to 0002 or 0003. The Phase 2 database audit found only migration 0001 applied and no fixture/result/source-observation/import rows. Do not apply these migrations to the production branch as part of this phase.

The PostgreSQL 16 and 18 acceptance workflow uses an ephemeral veltrix_football_test database only. It applies migrations twice to prove idempotency, runs the schema acceptance and exercises the writer. It must not use a Neon production connection string.

## 4. Current acquisition limits

5Dollar Community access is bounded to 300 requests/hour, a 20/minute burst and the seven verified competition IDs. The one-year read-only acquisition run returned 2,496 finished fixtures over 26 pages using 28 of 40 requests. Its report hash and artifact are documented in the Phase 2 provider register.

That read-only report contains aggregate counts and hashes; it is not a substitute for the exact raw response archive. The PostgreSQL writer is the approved persistence path for raw bytes, entitlement snapshots and per-fixture provenance. Do not promote the dry-run report's aggregate rows into source observations.

The existing 4-day availability proxy is not true point-in-time data. All imported 5Dollar historical results remain excluded from point-in-time feature construction unless an independently evidenced publication timestamp is obtained. Settled scores may be used as labels only with the stated limitations.

## 5. Phase 3 validation gates

Phase 3 is not complete until all of the following are true:

1. The Phase 3 branch passes unit tests, compile checks and legacy-import isolation checks.
2. PostgreSQL 16 and 18 ephemeral acceptance passes all three migrations, schema checks and writer acceptance, including revocation and terminal checkpoint tests.
3. A sanitized run manifest can reconcile every requested provider page and every fixture ID into imported, rejected or quarantined outcomes without missing or duplicated records.
4. The provider-response archive and parsed observations have verifiable hashes and linked source approval/entitlement records.
5. A separate non-production Neon child branch is positively identified and migration 0002/0003 dry-run checksums are verified before any persistent staging import. Production remains untouched.
6. A bounded staging import is reconciled end-to-end; no missing page, fixture, result, quarantine, request or checkpoint accounting is accepted.
7. The historical feature availability limitation remains explicit and enforced.

**No production migration, Neon write, live import, model training, prediction workflow, Telegram activation, schedule or deployment is authorized by this phase.**
