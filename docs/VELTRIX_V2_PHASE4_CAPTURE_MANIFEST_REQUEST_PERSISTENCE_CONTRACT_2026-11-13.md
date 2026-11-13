# VELTRIX FOOTBALL 2.0 — Capture Manifest and Attempt Persistence

**Date:** 2026-11-13  
**Status:** Repository writer and PostgreSQL acceptance tests; no staging migration or dispatch  
**Parent:** Phase 4.8 request state persistence

## Manifest record

`PostgresHistoryStore.persist_capture_manifest` accepts only a `RequestManifest` whose canonical manifest hash and request fingerprint pass the pure orchestrator integrity validator. It persists the exact credential-free scope, manifest hash, stable manifest key, planned request count and original creation time. An exact replay returns the existing ID; any same-key scope/hash/time mismatch fails.

The stored scope includes provider/API version, endpoint class, sport and competition scope, fixture/event IDs, frozen prediction cutoffs and kickoffs, markets, regions, rights-evaluation timestamp, intended use, expected Terms version, attempt/timeout limits and request fingerprint. It contains no API key or secret.

## Completed attempt record

`PostgresHistoryStore.persist_capture_request` persists one final attempt outcome after the transport boundary has produced a response or an explicit uncertain/failure result.

- Request identity and fingerprint are inherited from the validated manifest.
- Endpoint must pass the exact Odds API HTTPS host/path/query allowlist.
- Attempt number must be within the manifest limit.
- Requested time must be timezone-aware and no earlier than manifest creation.
- RESPONSE requires an existing response row for the exact provider/source/request identity and a retrieval time no earlier than the request.
- Non-response outcomes cannot reference a response row.
- Same attempt identity is idempotent only when every stored field matches.
- Attempt N+1 is rejected until attempt N has an immutable terminal COMMITTED state event, which requires quota reconciliation.

## Ordering and recovery

The completed-attempt row is written after the transport outcome is known, while its `requested_at` retains the actual request-start time. Request state events preserve the original occurrence times and are append-only. A process interruption before final attempt persistence remains a recovery condition; it must not be converted into a fabricated success or retried request.

No provider network call is made by either persistence method. The existing explicit non-production database guard is mandatory.
