# VELTRIX FOOTBALL 2.0 — Prospective Odds Capture Orchestration Contract

**Date:** 2026-11-13  
**Status:** Design only; disabled; no provider requests or database writes  
**Parent:** Phase 4 provider qualification and point-in-time capture  
**Related:** Phase 4.1 offline Odds API v4 parser and credit planner

## 1. Purpose and non-goals

Define a fail-closed boundary for future prospective odds capture: rights checks, immutable request planning, credit reservation, provider attempt, raw-response preservation, offline parsing, quota reconciliation and evidence persistence.

This contract does **not** authorize The Odds API requests, credential loading, historical odds retrieval, polling, scheduling, prediction generation, model training, price selection, value-bet decisions, publication or Telegram delivery. The parser and planner remain pure offline components. The orchestrator must not import legacy prediction or odds-selection code.

## 2. Activation gates

A request is ineligible unless every gate is satisfied by recorded evidence:

1. Exact account-accepted Terms version and acceptance evidence. Public current Terms alone are insufficient.
2. Append-only scoped approval for provider, data class, competition/sport, markets, regions, storage, retention, derived use, display and training use as applicable.
3. Rights resolved at explicit `rights_evaluated_at`, distinct from prediction cutoff.
4. Allowance, provider-reported remaining balance, monthly hard cap, per-run cap and request-count cap configured and consistent.
5. Market/region/bookmaker coverage measured; unsupported totals or BTTS is recorded unavailable, never inferred.
6. Provider event IDs linked through approved versioned crosswalk; unresolved/overlapping mappings block capture.
7. Prediction cutoff, kickoff, provider publication timestamp and retrieval timestamp remain separate.
8. Concurrency, timeout, retry and emergency-disable controls configured and tested.

Missing, provisional, expired, ambiguous or contradictory evidence blocks the request. No manual override exists in the orchestrator.

## 3. Immutable request manifest

Before network activity, construct and persist a canonical manifest containing capture run/request IDs; provider/API version; endpoint class; sport key; exact event IDs; regions and unique markets; intended fixture IDs and crosswalk version; credential-free request fingerprint; frozen fixture cutoffs; rights evaluation time and approval evidence IDs; budget snapshot, estimated/reserved credits and request-count reservation; creation time; code/parser versions; manifest hash; maximum attempts and timeout policy.

Canonical serialization must be deterministic. Hash canonical manifest bytes. A retry is a new attempt under the same immutable request identity only when policy permits. Any change to market, region, event, endpoint or rights scope requires a new manifest.

## 4. Capture state machine

Normal transitions:

`PLANNED -> PREFLIGHT_APPROVED -> CREDIT_RESERVED -> REQUEST_STARTED -> RESPONSE_RECEIVED -> PARSED -> QUOTA_RECONCILED -> COMMITTED`

A failed gate transitions `PLANNED -> BLOCKED`. A timeout/disconnect/process interruption after dispatch transitions to `OUTCOME_UNCERTAIN`. Invalid payload transitions to `PARSE_REJECTED`. Definitive provider rejection is recorded as `PROVIDER_REJECTED` only with status and quota evidence.

Transitions are append-only events with actor, timestamp, previous/next state, reason code and evidence hash. Invalid transitions fail closed; no in-place state rewriting.

## 5. Preflight and reservation ordering

1. Validate manifest schema and canonical hash.
2. Resolve scoped rights at `rights_evaluated_at`.
3. Validate fixture/event crosswalk and requested scope.
4. Validate each fixture cutoff and kickoff boundary.
5. Run the pure budget planner against a frozen budget snapshot.
6. Atomically reserve estimated credits and request-count capacity under a lock/transaction that prevents concurrent overspend.
7. Persist `REQUEST_STARTED` immediately before dispatch.
8. Only then may the HTTP adapter issue the exact manifest-defined request.

No network call may occur before all eight steps complete. Failed reservation means zero provider calls. Every retry repeats preflight against refreshed budget/quota evidence.

## 6. HTTP adapter constraints

- Load the API key only inside the future adapter from the approved secret store; never pass it to parser/planner, persist it, log it or include it in fingerprints.
- Prefer `x-api-key`; never put credentials in query strings.
- Fixed allowlisted HTTPS host and documented API v4 paths only; no redirects to unapproved hosts.
- Explicit connect/read timeout and response-size limit.
- No automatic retry for authentication, entitlement, invalid-request or exhausted-credit responses.
- Retry only explicitly classified transient failures, within manifest attempt limits and after fresh budget/quota preflight.
- Timeout or connection loss after dispatch becomes `OUTCOME_UNCERTAIN`; reserve estimated credits until reconciled.
- Discovery endpoints have zero odds-credit estimate only; request-count/rate-limit capacity is still reserved.
- No hidden polling, unbounded fan-out or unbounded retries.

## 7. Response evidence and parsing

Preserve exact raw bytes in immutable storage; SHA-256 over those bytes; HTTP status; allowlisted non-secret metadata; timezone-aware retrieval time; only documented quota headers (`x-requests-used`, `x-requests-remaining`, `x-requests-last`); request/manifest and attempt IDs; provider correlation IDs where supplied.

Pass exact bytes to the offline parser. Never decode and reserialize before hashing. Preserve market-level `last_update`; bookmaker timestamps and retrieval time are not publication-time substitutes. Missing/untrusted market timestamps remain ineligible. Do not infer missing outcomes, lines, bookmaker coverage or BTTS availability.

Validate parsed quotes against frozen fixture cutoff and rights scope. Quotes published after cutoff may remain raw evidence but are excluded from eligible features. Retrieval time never proves publication time.

## 8. Quota reconciliation and uncertain consumption

Compare preflight estimate, reservation and provider-reported usage. Reconcile only from documented quota headers or authoritative account evidence.

- Missing/malformed quota headers remain unknown, never zero.
- If actual consumption exceeds estimate, record the overrun and block subsequent requests until ledger reconciliation.
- If consumption is uncertain, retain the full reservation.
- Never release a reservation merely because a request timed out or returned an error.
- Inconsistent used/remaining/last values fail reconciliation.
- Every reservation receives one immutable disposition: reconciled, conservatively retained or evidence-backed administrative resolution.

## 9. Idempotency, concurrency and persistence

- Unique constraints protect request fingerprint + attempt number and provider response hash + request ID.
- Duplicate delivery cannot create duplicate quote observations.
- Distinct lines, bookmakers, event IDs and publication revisions remain distinct.
- Concurrent workers reserve credits under serializable transaction or equivalent row/advisory lock.
- Raw response, manifest, state events, quota evidence and normalized quotes link through immutable IDs.
- Evidence records are append-only; corrections are new versions, never in-place edits; no cascade deletion.
- Commit normalized quotes only after raw-response durability, parse result and quota evidence. Unknown reconciliation is quarantined/uncertain, not clean committed capture.

## 10. Failure matrix

| Failure | Required outcome |
|---|---|
| Terms acceptance/version missing | Block before network |
| Rights absent, provisional or revoked | Block before network |
| Unknown competition/market/region scope | Block before network |
| Event crosswalk ambiguous/overlapping | Block before network |
| Budget missing, zero-cap or inconsistent | Block before network |
| Reservation exceeds cap | Block before network |
| Authentication/entitlement rejection | Record; no automatic retry |
| 429/exhausted quota | Stop; reconcile before new request |
| Timeout after dispatch | Mark uncertain; retain reservation |
| Invalid JSON/shape | Preserve raw bytes; quarantine parse |
| Missing market timestamp | Preserve as timestamp-ineligible |
| Quota headers missing | Reconciliation unknown; do not release |
| Duplicate response | Idempotent no-op plus audit event |
| Database unavailable after response | Preserve durable raw evidence; retry persistence only, never blindly re-request |

## 11. Offline acceptance test plan

Using mocked transport and archived fixtures only, prove:

- each activation gate independently blocks absent, provisional, expired or mismatched evidence
- rights are evaluated at `rights_evaluated_at`, not cutoff
- canonical manifest and SHA-256 are deterministic
- fingerprints never contain credentials
- no HTTP call occurs if any preflight gate fails
- dispatch scope exactly matches endpoint/event/region/market manifest
- every attempt re-runs credit and request-count preflight
- concurrent reservations cannot exceed caps
- timeouts retain reservations and become uncertain
- auth, entitlement and 429 failures do not auto-retry
- only approved transient failures retry within bounded attempts
- raw response bytes are stored and hashed exactly
- unknown/mismatched quota blocks reconciliation and further capture
- duplicate responses are idempotent
- no prediction, legacy odds-selection, publication or Telegram imports occur

Tests monkeypatch transport and prove zero real network access. First integration acceptance is a dry-run that emits a manifest and reservation decision only; it does not dispatch HTTP.

## 12. Release boundary

The adapter remains disabled until account-specific Terms evidence, scoped rights approval, actual allowance, hard caps, request-count limits and observed soccer market coverage are recorded. Initial activation, if later approved, must be manual, limited to a small allowlisted sample and independently audited before expansion.

No scheduled daily capture is included. The existing report schedule remains disabled.
