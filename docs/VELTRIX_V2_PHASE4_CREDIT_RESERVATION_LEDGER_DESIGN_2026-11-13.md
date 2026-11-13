# VELTRIX FOOTBALL 2.0 — Transactional Provider Credit Reservation Ledger

**Date:** 2026-11-13  
**Status:** Design only; no migration, database writes, provider calls or credit reservation  
**Parent:** Phase 4.2 offline odds capture orchestration  
**Depends on:** PR #72 request manifest/preflight and PR #73 append-only capture state machine

## 1. Purpose and boundary

Define the PostgreSQL-backed reservation ledger that will prevent concurrent capture workers from overspending a provider allowance, monthly hard cap, per-run cap or request-count cap.

This document is a design contract, not an authorization to call The Odds API. Implementation must remain offline and staging-only until the provider account's exact accepted Terms, scoped rights, actual allowance, quota evidence and operator-defined caps are independently recorded. No production writes, provider HTTP, credentials, schedule, prediction generation, training, publication, Telegram delivery or value betting are in scope.

## 2. Accounting invariants

1. Unknown is not zero. An absent or malformed allowance, provider remaining balance, quota usage or request count is represented as NULL/unknown and blocks a new reservation.
2. A reservation is durable before dispatch. No request may start unless its reservation transaction committed and a matching immutable `CREDIT_RESERVED` state event exists.
3. Reservations are idempotent. A stable reservation key identifies one manifest request attempt. Replaying the same key returns the original reservation; a conflicting payload under that key fails.
4. Reservations are serialized per provider account and billing period. Concurrent workers cannot independently observe the same remaining capacity and overspend it.
5. A timeout or disconnect after dispatch is uncertain consumption. The full reservation remains held until authoritative evidence reconciles it.
6. A reservation is never released on local error, process death, timeout, parse failure or missing quota headers.
7. Provider-reported usage is evidence, not a value to silently normalize. Inconsistent used/remaining/last values block further reservations.
8. Actual consumption above estimate is recorded as an overrun and freezes new reservations until reconciled.
9. Monthly allowance, configured monthly hard cap, per-run cap and request-count limits are separate constraints; passing one never implies passing another.
10. All state changes are append-only events. No UPDATE/DELETE of financial/quota evidence.
11. A reservation cannot be reused across provider accounts, billing periods, manifests, event/market/region scopes or attempt numbers.
12. No database transaction remains open during network activity.

## 3. Data model

### 3.1 Provider account budget snapshots

A versioned, append-only budget snapshot records:
- provider and provider account reference (non-secret opaque ID)
- billing period start/end
- confirmed monthly allowance
- operator-configured monthly hard cap
- operator-configured per-run credit cap
- operator-configured request-count cap
- provider-reported remaining credits (nullable until observed)
- provider-reported used credits and last-request cost (nullable)
- evidence source, evidence URI/hash, observed timestamp and recorded timestamp
- exact account Terms version reference and scoped approval IDs

No API key, token, password, connection string or other credential is stored.

A new snapshot supersedes no prior evidence. The resolver selects a snapshot only when its period, account, evidence and freshness requirements match the proposed reservation. Missing or stale values fail closed.

### 3.2 Reservation event ledger

Append-only events include:
- `RESERVED`: estimated credits and one request-count unit committed before dispatch
- `DISPATCH_CONFIRMED`: matching attempt entered provider dispatch
- `OUTCOME_UNCERTAIN`: provider consumption cannot yet be determined
- `RECONCILED`: authoritative usage evidence fixes actual consumed credits
- `RETAINED`: reservation remains held because evidence is insufficient
- `RELEASED`: only evidence-backed proof of zero provider consumption; never inferred from local failure
- `OVERRUN`: actual consumption exceeds the reserved estimate
- `ADMIN_RESOLVED`: exceptional, evidence-backed resolution requiring two distinct authorized reviewers

Each event contains reservation ID/key, provider/account, billing period, manifest/request fingerprint, attempt number, event timestamp, actor, reason code, reserved/actual amounts where applicable, provider quota evidence hash and prior-event hash. The event chain is deterministic and verifiable.

### 3.3 Idempotency constraints

Unique identities:
- reservation key
- (provider account, billing period, manifest request key, attempt number)
- (reservation ID, event sequence)
- provider response hash + request attempt identity

A duplicate reservation key with identical immutable inputs is an idempotent read. The same key with different amount, scope, account, period or manifest fingerprint is a hard conflict.

## 4. Atomic reservation algorithm

All capacity decisions run in one short PostgreSQL transaction:

1. Validate the manifest hash and preflight evidence references.
2. Lock the provider-account/billing-period budget row using `SELECT ... FOR UPDATE` (or a transaction-scoped advisory lock keyed by immutable account and period).
3. Re-read the latest eligible budget snapshot under the lock; reject stale, missing, contradictory or unknown evidence.
4. Resolve the latest reservation event for every reservation in the period.
5. Compute:
   - reconciled actual consumption for the period;
   - outstanding held credits for RESERVED, DISPATCH_CONFIRMED, OUTCOME_UNCERTAIN and RETAINED reservations;
   - current request-count consumption and outstanding request reservations;
   - this run's consumed and outstanding credits.
6. Calculate available capacity as the minimum of independently evidenced constraints:
   - confirmed provider remaining credits;
   - monthly hard cap less reconciled and outstanding usage;
   - monthly allowance less reconciled and outstanding usage;
   - per-run cap less run usage;
   - request-count cap less period request count.
7. If any required input is unknown or the proposed reservation exceeds any constraint, rollback with a stable rejection code.
8. Insert the immutable `RESERVED` event and idempotency identity; commit.
9. Only after commit may the dispatcher transition to `REQUEST_STARTED` and make the exact manifest-bound request.

The transaction must not call a provider, access secrets, perform HTTP, wait for external evidence or sleep. Serializable isolation is acceptable; row locking with unique constraints and a retry-on-serialization policy is also acceptable. Deadlocks/serialization failures retry the database transaction only, never the provider request.

## 5. Reconciliation rules

Quota headers are parsed as non-negative integers only. Missing, malformed, negative, boolean-like or mutually inconsistent values remain unknown/invalid.

For The Odds API evidence:
- `x-requests-used`
- `x-requests-remaining`
- `x-requests-last`

The adapter records exact header values and response hash. The reconciler validates documented relationships against the frozen budget snapshot and previous quota evidence; it does not assume that a single header proves the full account balance.

Disposition:
- Known usage equal to or below reservation: append RECONCILED with actual usage; release only the evidenced unused portion.
- Known usage above reservation: append OVERRUN; charge actual usage and freeze new reservations pending budget refresh.
- Timeout, lost response, missing headers or conflicting evidence: append OUTCOME_UNCERTAIN/RETAINED; hold the full reservation.
- Zero usage: release only when provider evidence explicitly proves zero consumption for that request.
- Administrative resolution: requires explicit evidence URI/hash, reason, two distinct reviewers and append-only event; never a general override.

A fresh budget snapshot is required after a quota inconsistency or overrun before capture can resume.

## 6. Concurrency and failure recovery

- Two workers reserving simultaneously for the same account/period serialize on the same lock.
- Different provider accounts or periods may reserve independently.
- A worker crash before transaction commit leaves no reservation.
- A crash after commit but before dispatch leaves a held reservation; recovery may release only after proving no dispatch occurred.
- A crash after dispatch but before response is OUTCOME_UNCERTAIN; do not retry provider request.
- A crash after response but before persistence requires durable raw response evidence to be retried through persistence only; do not repeat provider request.
- Duplicate queue delivery returns the existing reservation and cannot create another credit hold.
- Database transaction retries never replay network operations.

## 7. Security and authorization

- Credentials are loaded only by a future HTTP adapter from an approved secret store and never enter SQL parameters, manifests, hashes, logs or evidence rows.
- Provider account references are opaque identifiers, not usernames or secrets.
- Reservation requires exact account Terms evidence, scoped rights approval and matching manifest scope.
- Administrative resolution uses two distinct principals; the initiating actor cannot approve their own resolution.
- Least-privilege database role: execute approved reservation/reconciliation functions and insert evidence; no UPDATE/DELETE rights on append-only evidence.
- Production role and production database are out of scope.

## 8. Acceptance tests

Use PostgreSQL 16 and 18 with isolated disposable databases and mocked evidence. No provider HTTP or secret access.

Required tests:
1. Single reservation succeeds when every budget and rights input is evidenced.
2. Unknown allowance, remaining balance, hard cap or request cap blocks.
3. Monthly, per-run and request-count caps independently block.
4. Concurrent reservations cannot exceed any cap.
5. Same idempotency key and same payload returns original reservation.
6. Same key with changed scope or amount fails.
7. Distinct attempts require distinct reservation identities and fresh preflight.
8. Timeout and missing quota evidence retain the full hold.
9. Explicit authoritative zero-consumption evidence is required to release.
10. Overrun freezes further reservations.
11. Inconsistent quota headers block reconciliation and new reservations.
12. Budget snapshot from wrong account or billing period is rejected.
13. Crash recovery does not replay provider HTTP.
14. Event hash-chain tampering is detected.
15. Append-only triggers reject UPDATE and DELETE.
16. No credential material can be persisted or included in fingerprints.
17. Foundation import guard confirms no legacy prediction or odds-selection imports.

## 9. Staging rollout sequence

1. Merge and validate PR #72, then PR #73 in stack order.
2. Implement the migration and pure reservation service on the merged Phase 4.2 baseline.
3. Run PostgreSQL 16/18 migration, idempotency, rollback and concurrency tests in CI.
4. Review the migration and SQL functions before staging application.
5. Apply only to Neon staging branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`, after exact host/database/role guards.
6. Verify no Phase 3 imported rows changed and no reservation exists unless created by a dedicated synthetic test transaction that is rolled back or isolated.
7. Do not connect the reservation service to HTTP dispatch until all provider activation gates are satisfied.

## 10. Explicit non-authorization

This design does not authorize live or test provider requests, API-key loading, credit reservation against a real account, historical odds purchase, automatic scheduling, model training, prediction publication, Telegram activation or value-bet unlock. All remain disabled.
