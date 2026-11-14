# VELTRIX FOOTBALL 2.0 — Provider Quota Reconciliation Contract

**Date:** 2026-11-13  
**Status:** Offline-only; no provider calls or database writes  
**Parent:** Phase 4.3 transactional credit reservation ledger

## Purpose

Specify how authoritative post-request quota headers reconcile one reserved request attempt. Reconciliation is evidence accounting, not permission to call a provider. The future dispatcher must persist the exact raw response and allowlisted quota headers before invoking this pure validator.

## Required evidence

Each pre/post snapshot must bind:
- exact provider and opaque account reference
- exact billing period
- timezone-aware observation timestamp
- x-requests-used
- x-requests-remaining
- x-requests-last
- SHA-256 of the evidence record

All counters must be non-negative integers, not booleans or numeric strings at this layer. Header parsing is a separate boundary; missing or malformed values remain unknown.

## Reconciliation algorithm

1. Require both snapshots to match provider, account and billing period.
2. Require strictly increasing observation timestamps.
3. Require every quota counter and evidence hash.
4. Require used_after >= used_before and remaining_after <= remaining_before.
5. Compute used_delta = used_after - used_before and remaining_delta = remaining_before - remaining_after.
6. Require used_delta == remaining_delta == requests_last_after.
7. If counters disagree, external requests may have interleaved or evidence may be stale; return QUOTA_RECONCILIATION_UNKNOWN and retain the entire reservation.
8. If the reconciled last-request cost exceeds reserved credits, return CREDIT_OVERRUN; charge the observed cost and block subsequent reservations pending a fresh budget snapshot.
9. Otherwise return RECONCILED; actual usage is the observed last-request cost and only the evidenced unused reservation may be released.
10. Zero usage may be released only when the matching response evidence proves a zero-cost request.

No interpolation, assumed zero, counter reset, external-request apportionment or inference is permitted. The first implementation intentionally rejects intervals containing unexplained quota movement.

## Acceptance cases

- exact counter deltas equal x-requests-last
- missing or malformed counters
- provider/account/billing-period mismatch
- non-monotonic counters or timestamps
- external request interference
- actual usage below reservation
- exact usage equal to reservation
- actual usage above reservation
- explicit zero-cost evidence
- evidence-hash and timestamp validation

The module has no HTTP, secret, database, scheduling or prediction imports.
