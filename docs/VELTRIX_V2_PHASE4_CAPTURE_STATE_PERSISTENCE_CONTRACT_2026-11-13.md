# VELTRIX FOOTBALL 2.0 — Capture Request State Event Ledger

**Date:** 2026-11-13  
**Status:** Additive migration and guarded repository writer; no staging migration applied  
**Parent:** Phase 4.7 transport and quota evidence persistence

## Purpose

Persist the pure capture state machine's immutable transition events. The database ledger is keyed to the existing provider capture request row, so a state history cannot be attached to a different provider request or attempt.

## State model

Allowed transitions mirror `veltrix_v2.providers.odds_api_v4.state_machine`:
- PLANNED → BLOCKED or PREFLIGHT_APPROVED
- PREFLIGHT_APPROVED → BLOCKED or CREDIT_RESERVED
- CREDIT_RESERVED → BLOCKED or REQUEST_STARTED
- REQUEST_STARTED → RESPONSE_RECEIVED, OUTCOME_UNCERTAIN or PROVIDER_REJECTED
- OUTCOME_UNCERTAIN → QUOTA_RECONCILED
- RESPONSE_RECEIVED → PARSED, PARSE_REJECTED or PROVIDER_REJECTED
- PROVIDER_REJECTED / PARSED / PARSE_REJECTED → QUOTA_RECONCILED
- QUOTA_RECONCILED → COMMITTED

BLOCKED and COMMITTED are terminal. There is no direct transition from an uncertain outcome to a retry; quota reconciliation must happen first, and a retry is a distinct capture attempt.

## Database invariants

- Each event references one `provider_capture_requests.capture_request_id` with ON DELETE RESTRICT.
- Sequence is unique per request and must start at 1 from PLANNED.
- Every subsequent event must continue the previous state, sequence, event hash and non-decreasing timestamp.
- PostgreSQL advisory transaction locks serialize concurrent event appends per capture request.
- Transition legality is rechecked in a BEFORE INSERT trigger; caller-side validation is not trusted as the only control.
- Event rows reject UPDATE and DELETE.
- Application-generated SHA-256 hashes are verified by the Python state-machine validator before insertion; the database enforces hash format and previous-hash continuity but does not independently recompute the canonical JSON hash.

## Repository writer

`PostgresHistoryStore.append_capture_state_event`:
1. Requires the existing explicit non-production database write guard.
2. Verifies the event's canonical hash using the pure state machine.
3. Confirms event request ID matches the database capture request key.
4. Inserts one event; an exact replay returns the existing event ID.
5. Rejects any same-sequence replay with differing event content.
6. Commits each append transactionally; database trigger enforces the transition chain.

No network call, provider credential, retry, reservation mutation, prediction or publication is performed.
