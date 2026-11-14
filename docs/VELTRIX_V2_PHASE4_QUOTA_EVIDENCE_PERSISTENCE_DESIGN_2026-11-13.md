# VELTRIX FOOTBALL 2.0 — Durable Quota Evidence Persistence

**Date:** 2026-11-13  
**Status:** Design only; migration not applied; no provider capture  
**Parent:** Phase 4.4 quota reconciliation and Phase 4.3 credit reservation

## 1. Purpose

Persist provider quota evidence as immutable records linked to the exact provider response, source, account, billing period and credit reservation attempt. This closes the evidence chain between raw response bytes already stored in provider_responses, allowlisted quota headers, the pre-request quota snapshot, the post-request snapshot and the resulting reconciliation decision.

## 2. Existing evidence reuse

- Reuse provider_responses.raw_body and response_sha256 as the authoritative raw response bytes and content hash.
- Reuse provider_responses.provider/source_id identity and its composite uniqueness for response linkage.
- Do not duplicate raw response payloads or reserialize them before hashing.
- Persist only the three documented quota headers: x-requests-used, x-requests-remaining and x-requests-last.
- Preserve raw header strings exactly; parsed integer columns remain nullable when parsing fails.

## 3. Snapshot model

Each quota snapshot records provider, source, opaque provider account reference, billing period, provider_response_id, observed_at, exact allowlisted raw header values, parsed counters, evidence SHA-256 and recorded_at.

Composite foreign keys enforce that the linked provider response has the same provider and source. One response can create at most one quota snapshot. Snapshot rows are append-only.

## 4. Reconciliation event model

Each reconciliation event binds:
- one reservation attempt's initial RESERVED ledger event
- one pre-request quota snapshot
- one post-request quota snapshot
- provider/account/billing period identity
- sequence number and previous event hash
- status UNKNOWN, RECONCILED or OVERRUN
- actual and releasable credit values when proven
- reason code, evidence hash, event hash, actor and event time

Composite foreign keys prevent snapshots from another account, provider or billing period being attached. A trigger verifies that both snapshots share the same scope, the post snapshot is later, and the reservation belongs to that provider/account/period.

UNKNOWN events may be followed by later evidence-backed reconciliation events. RECONCILED and OVERRUN are terminal. Corrections append new evidence; they never update or delete prior rows.

## 5. Database invariants

- Snapshot and reconciliation tables reject UPDATE and DELETE.
- Provider response references use ON DELETE RESTRICT.
- Reservation references use ON DELETE RESTRICT.
- Snapshot counters are nullable but never negative.
- Raw header JSON may contain only the three allowlisted keys.
- RECONCILED requires exact counter-delta agreement and actual credits no greater than reserved credits.
- OVERRUN requires actual credits greater than reserved credits and zero releasable credits.
- UNKNOWN stores no inferred actual or releasable credit value.
- Event sequence is unique per reservation; hash links must match the preceding event.
- No automatic release, retry or provider request is performed by persistence.

## 6. Acceptance

Run migration and tests against PostgreSQL 16 and 18 using disposable CI databases. Prove:
- exact response/provider/source linkage
- raw header preservation and allowlist rejection
- account and billing-period cross-link rejection
- before/after ordering
- exact reconciliation and overrun constraints
- UNKNOWN followed by later reconciliation
- terminal-state protection
- event hash-chain integrity
- append-only triggers
- no changes to Phase 3 historical records

No staging or production migration is authorized by this design.
