# VELTRIX FOOTBALL 2.0 — Controlled Capture Execution and Recovery Contract

**Date:** 2026-11-14  
**Status:** Design contract; no real provider transport or staging writes

## 1. Purpose

Define one auditable execution boundary for a single The Odds API v4 request. The runner must coordinate the existing manifest, preflight, account activation, credit reservation, dispatch authorization, raw response, quota reconciliation and append-only capture state components without weakening any gate.

This contract is not authorization to contact The Odds API. The only transport permitted during implementation and acceptance testing is an explicitly injected deterministic test double.

## 2. Preconditions

A production-capable attempt requires all of the following, independently verified at execution time:

1. A canonical, integrity-valid request manifest and approved preflight decision.
2. A persisted manifest and request identity in the non-production history store.
3. An account-specific Terms acceptance record with exact accepted version and immutable evidence.
4. An account-linked APPROVED rights event covering the exact provider, source, competitions, markets, regions and permitted use.
5. A fresh account/billing-period budget snapshot with evidenced monthly allowance, provider remaining credits, monthly hard cap, per-run hard cap and request-count cap.
6. A successful account activation gate bound to the exact request fingerprint and dispatch timestamp.
7. A committed transactional credit reservation for the same manifest, request, attempt and fingerprint.
8. A final dispatch guard decision with operator enablement true and emergency stop clear.
9. A before-request quota snapshot from the same account and billing period when the provider's quota counters are available.

Missing, stale, malformed, unscoped or conflicting evidence blocks dispatch. No caller-supplied boolean may replace source evidence.

## 3. Single-attempt execution sequence

The runner handles one manifest/request attempt only. It never batches unrelated requests, loops over retries or makes a second provider request automatically.

### A. Prepare and persist

1. Recompute and verify manifest fingerprint and SHA-256.
2. Persist the credential-free manifest using exact idempotent replay.
3. Append initial capture state PLANNED.
4. Evaluate preflight against rights, competition/event crosswalk and budget planner.
5. If preflight fails, append BLOCKED with a stable reason code and stop.
6. If it passes, append PREFLIGHT_APPROVED.
7. Persist the account/billing-period budget snapshot and Terms/rights evidence links.
8. Call the atomic reservation function. A successful reservation must be bound to the exact manifest ID, request key, attempt number, fingerprint, run key and budget snapshot.
9. Append the reservation lifecycle event RESERVED, then append capture state CREDIT_RESERVED.

The database transaction is the authority for shared credit capacity. Python-side validation is a pre-check only and must never be described as a reservation.

### B. Final authorization and dispatch

Immediately before the injected transport is called:

1. Re-evaluate the activation evidence against the exact dispatch timestamp.
2. Revalidate the request fingerprint, reservation identity and reservation commitment.
3. Revalidate budget expiry and all capacity caps.
4. Revalidate attempt count and prior-attempt reconciliation.
5. Require operator dispatch enablement and a clear emergency stop.
6. Append REQUEST_STARTED and reservation DISPATCH_CONFIRMED before invoking transport.
7. Invoke the injected transport exactly once with redirects disabled, fixed timeout limits and the bounded response size.

The real HTTP client, credential loader and environment access remain out of scope until a separate reviewed activation change after manual evidence is present.

### C. Capture and persist the response

- Preserve the exact response bytes before decoding or parsing.
- Compute SHA-256 over those exact bytes.
- Preserve retrieval time separately from provider publication/market timestamps.
- Retain only the documented x-requests-used, x-requests-remaining and x-requests-last headers as raw strings. Never store authorization headers or API keys.
- Missing or malformed quota counters remain unknown; they are never converted to zero.
- Persist the provider response and quota snapshot atomically, linked to the account, billing period and exact request.
- Persist the completed attempt with its actual outcome and response linkage.
- A non-200 response is still evidence and must not be silently discarded; provider rejection and quota evidence follow the explicit failure path.

### D. Parse and reconcile

1. Parse only after raw response persistence.
2. Preserve parser diagnostics and reject malformed or mismatched event/market payloads without discarding the raw response.
3. Append RESPONSE_RECEIVED, then either PARSED or PARSE_REJECTED; non-success provider status uses PROVIDER_REJECTED.
4. Persist the after-request quota snapshot.
5. Reconcile before/after counters only when account, billing period, timestamps, all counters and evidence hashes match.
6. Accept actual usage only when used-after minus used-before, remaining-before minus remaining-after and x-requests-last agree exactly.
7. If exact reconciliation succeeds, append reservation RECONCILED (or explicit OVERRUN when actual usage exceeds reserved amount), then capture state QUOTA_RECONCILED, followed by COMMITTED.
8. If evidence is incomplete, contaminated, non-monotonic or contradictory, retain the reservation and leave the capture in its recoverable uncertain/reconciliation-pending state. Do not fabricate a usage figure or commit the attempt.

A parse rejection does not erase the provider request cost. A successful HTTP response does not prove zero or exact credit consumption without quota reconciliation.

## 4. Failure and crash recovery matrix

| Failure point | Required durable treatment | Retry eligibility |
|---|---|---|
| Before manifest persistence | No attempt exists | Rebuild/replay manifest |
| After manifest, before reservation | Persisted manifest; no credits committed | Same attempt may resume idempotently |
| Reservation committed, request not started | Reservation remains held | Release only with proof transport was never invoked |
| Request started, transport times out or process crashes | OUTCOME_UNCERTAIN; reservation retained | Blocked until exact quota reconciliation |
| Response received, persistence incomplete | Recover raw response from durable transport evidence if available; otherwise uncertain | Blocked until response/quota recovery |
| Response persisted, parser rejects | Preserve raw response and diagnostics; reconcile quota | No retry before reconciliation |
| Quota counters missing or inconsistent | Mark reconciliation unknown; retain reservation | Blocked; operator evidence/reconciliation required |
| Reconciled and committed | Immutable terminal record | New attempt only if manifest policy allows and previous attempt is committed |

The system must assume a request may have reached the provider once REQUEST_STARTED is durable. A process exception is not proof that the provider received zero requests.

## 5. Reservation lifecycle invariants

- RESERVED is created atomically against the account/billing period and all independent caps.
- DISPATCH_CONFIRMED is appended before transport invocation.
- Any uncertain transport outcome retains the full reservation.
- RELEASED is permitted only with explicit provider-confirmed zero usage or proof that dispatch never started.
- RECONCILED actual credits must not exceed reserved credits.
- OVERRUN is explicit and freezes further account dispatch pending review.
- No reservation event is updated or deleted.
- A second attempt is forbidden until the previous attempt has terminal COMMITTED capture state and reconciled reservation evidence.

## 6. State machine alignment

The runner must use the existing append-only capture state machine and its transition validator. It must not invent alternate states or bypass hash-chain validation.

Current supported path:

PLANNED → PREFLIGHT_APPROVED → CREDIT_RESERVED → REQUEST_STARTED → RESPONSE_RECEIVED → PARSED/PARSE_REJECTED → QUOTA_RECONCILED → COMMITTED

Alternate provider/transport path:

REQUEST_STARTED → PROVIDER_REJECTED → QUOTA_RECONCILED → COMMITTED

Uncertain transport path:

REQUEST_STARTED → OUTCOME_UNCERTAIN → QUOTA_RECONCILED → COMMITTED

An attempt with unknown quota evidence remains pending in its last valid state; it is not marked COMMITTED.

## 7. Required acceptance tests

- Exact idempotent manifest and reservation replay.
- Concurrent reservation attempts cannot exceed monthly, provider, per-run or request-count caps.
- Dispatch denial causes zero transport calls.
- Activation evidence mismatch causes zero transport calls.
- Emergency stop and operator-disabled cases cause zero transport calls.
- Transport is invoked exactly once after all gates pass.
- Redirects are disabled and response-size limits are enforced.
- Raw bytes/hash/retrieval timestamp survive persistence exactly.
- Secret headers never appear in persisted quota evidence.
- Timeout and exception produce uncertainty, retain reservation and never auto-retry.
- Parser rejection still reconciles actual request cost.
- Exact quota delta reconciles; missing, malformed, contaminated or contradictory quota remains unknown.
- Reservation release requires proof of zero consumption.
- Concurrent event append is serialized and hash-chain continuity is preserved.
- PostgreSQL 16 and 18 pass the same acceptance suite.

## 8. Explicit non-goals

This phase does not build prediction models, train/calibrate models, select best bookmakers, calculate value bets, publish forecasts, activate Telegram, create schedules, apply staging/production migrations or deploy Vercel.

The historical import remains immutable and non-point-in-time-certifiable. No historical retrieval time may be repurposed as publication time.

## 9. Current activation blocker

The manual account evidence handoff remains incomplete:

- Exact accepted Terms version and account-linked acceptance evidence.
- Scoped account-linked APPROVED source-rights evidence.
- Actual monthly allowance, remaining balance, billing period and explicit monthly/per-run/request-count caps.

Until independently verified, the real provider transport remains disabled. The next implementation can use deterministic injected transport and isolated PostgreSQL test databases only.
