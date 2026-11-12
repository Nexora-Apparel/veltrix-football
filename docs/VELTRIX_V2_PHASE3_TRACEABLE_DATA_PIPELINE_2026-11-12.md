# VELTRIX FOOTBALL 2.0 — Phase 3: Traceable Data Pipeline

**Status:** IN PROGRESS — provenance contracts, append-only source evidence, entitlement gates, explicit competition scoping, immutable approval revocation, monotonic checkpoints and PostgreSQL 16/18 acceptance are implemented and CI-verified. Migrations 0001–0003 are applied and checksum-verified in the isolated Neon staging database. The live provider import is prepared but has not run.

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
- The PostgreSQL acceptance harness covers idempotent page replay, changed-score quarantine, duplicate fixture quarantine across pages, unentitled competition quarantine, suspended entitlement, altered approval replay, approval revocation, append-only mutation rejection, checkpoint terminal rewrite rejection and stale watermark rejection.
- The writer verifies that every parsed fixture row is present unchanged in the exact raw provider response, that its canonical payload SHA-256 matches the payload, and that fixture retrieval time equals the response fetch time. Mutation after parsing is rejected before a database connection is opened.

## 3. Migration state and database safety

The migration set is additive:
- 0001_persistent_foundation.sql — existing persistent foundation.
- 0002_historical_provenance.sql — source approvals, exact provider responses, entitlement observations, provenance columns, result versions, run/checkpoint accounting, sync watermarks and quarantine.
- 0003_source_approval_status_events.sql — append-only approval status and revocation evidence.

The production Neon database remains on migration 0001 and has no fixture/result/source-observation/import rows. Do not apply migrations 0002 or 0003 to the production branch as part of this phase.

A separate database named veltrix_football_staging was created inside the non-default Neon child branch veltrix-phase3-import-dry-run (branch ID br-silent-violet-bc5de88s; project ID withered-sky-75161174). All three migrations were applied there and their SHA-256 checksums match the repository migration files exactly. Read-only verification returned 18 expected public tables, six append-only evidence triggers, and zero fixture, result, source-observation, provider-response or approval-event rows. The original veltrix-football database on that child branch remains on migration 0001 and unchanged.

The PostgreSQL 16 and 18 acceptance workflow uses an ephemeral veltrix_football_test database only. It applies migrations twice to prove idempotency, runs the schema acceptance and exercises the writer. Both versions passed the latest Phase 3 CI run: 30 focused data-foundation tests, 18 tables, 42 indexes, three migrations, writer acceptance and append-only checks. It must not use a Neon production connection string.

## 4. Current acquisition limits

5Dollar Community access is bounded to 300 requests/hour, a 20/minute burst and the seven verified competition IDs. The one-year read-only acquisition run returned 2,496 finished fixtures over 26 pages using 28 of 40 requests. Its report hash and artifact are documented in the Phase 2 provider register.

That read-only report contains aggregate counts and hashes; it is not a substitute for the exact raw response archive. The PostgreSQL writer is the approved persistence path for raw bytes, entitlement snapshots and per-fixture provenance. A guarded importer is implemented at scripts/phase3_import_fivedollar_history.py. Its manual-only workflow is .github/workflows/phase3-staging-import.yml; it enforces the exact staging database name, requires an explicit YES flag, checks all three migration checksums, enforces the seven-competition entitlement, archives raw response bytes and finalizes run/checkpoint/watermark accounting only after a complete import. Do not promote the dry-run report's aggregate rows into source observations.

The existing 4-day availability proxy is not true point-in-time data. All imported 5Dollar historical results remain excluded from point-in-time feature construction unless an independently evidenced publication timestamp is obtained. Settled scores may be used as labels only with the stated limitations.

## 5. Phase 3 validation gates

Phase 3 is not complete until all of the following are true:

1. The Phase 3 branch passes unit tests, compile checks and legacy-import isolation checks.
2. PostgreSQL 16 and 18 ephemeral acceptance passes all three migrations, schema checks and writer acceptance, including revocation and terminal checkpoint tests.
3. A sanitized run manifest can reconcile every requested provider page and every fixture ID into imported, rejected or quarantined outcomes without missing or duplicated records.
4. The provider-response archive and parsed observations have verifiable hashes and linked source approval/entitlement records.
5. A separate non-production Neon child branch and dedicated staging database are positively identified; migration 0001–0003 checksums and schema are verified. Production remains untouched. COMPLETE.
6. A bounded live staging import is reconciled end-to-end; no missing page, fixture, result, quarantine, request or checkpoint accounting is accepted. PENDING: GitHub Actions needs the VELTRIX_STAGING_DATABASE_URL secret for the dedicated staging database.
7. The historical feature availability limitation remains explicit and enforced.

**No production migration, Neon write, live import, model training, prediction workflow, Telegram activation, schedule or deployment is authorized by this phase.**


## 6. Staging import handoff

The repository workflow expects one additional GitHub Actions secret:

- Name: VELTRIX_STAGING_DATABASE_URL
- Target: Neon project withered-sky-75161174, child branch br-silent-violet-bc5de88s, database veltrix_football_staging, role neondb_owner.
- Value: the connection string copied from Neon for that exact branch/database. Keep it in GitHub Actions Secrets; never place it in repository files, workflow YAML, logs or chat.
- Existing provider secret: FIVEDOLLARFOOTBALL_API_KEY.

After the secret is set, run the manual workflow Phase 3 — Bounded 5Dollar Staging Import from branch phase3/traceable-data-pipeline-20261112. It is capped at 40 requests, paced at four seconds, and defaults to 365 days. It is not scheduled and cannot run from main. The importer will write only to veltrix_football_staging.

### Current staging state

- Dedicated staging database exists and contains only schema/migration metadata.
- Migration checksums: 0001 b5f6f1b5dbe6d7587c4876578f50d8327711f7fd26d03410f31a04db659d267c; 0002 619c556674e409ad5cd3a9ddc9ae578455207545d3435b9ece4e91a953fef49a; 0003 8c70a8a1a060949a4fca924b1b0854d94e125b2cbf6f677049e7e70b4a836a19.
- Original production branch and the original veltrix-football database on the child branch were not modified.
- No live provider response or fixture data has yet been imported into the new staging database.
