# VELTRIX FOOTBALL 2.0 — Odds API Response and Quota Evidence Persistence

**Date:** 2026-11-13  
**Status:** Staging-testable repository writer; no live provider dispatch  
**Parent:** Phase 4 quota ledger, quota evidence schema, authorization guard and mock transport

## Transaction boundary

`PostgresHistoryStore.persist_odds_api_quota_evidence` accepts an already validated `ProviderResponse` and mock/transport `ResponseEnvelope`. It does not make HTTP requests. It uses the existing explicit database write guard and commits the raw response and its quota snapshot in one database transaction.

## Preconditions

- Provider/source must be exactly `the_odds_api` / `odds_api_v4`.
- Both response status and envelope status must be HTTP 200.
- Envelope body bytes and SHA-256 must match the ProviderResponse exactly.
- Retrieval timestamps must match exactly and remain timezone-aware through the ProviderResponse contract.
- The envelope's raw quota headers must equal the parser-produced quota evidence.
- Account reference and billing-period boundaries are explicit, non-empty and valid.
- Only the three documented `x-requests-*` headers are persisted. Authorization, cookies, API keys and unrelated headers are not copied to the response row.

## Atomic write

1. Revalidate envelope and quota evidence bindings before opening a write connection.
2. Enforce the store's explicit non-production database target guard.
3. Persist the exact response bytes through the existing provider-response idempotency path.
4. Insert one append-only quota snapshot linked by provider response ID, provider and source.
5. If the response already exists, compare every quota snapshot identity and evidence field. A mismatch is an idempotency conflict, not a silent overwrite.
6. Commit response and snapshot together. Any exception rolls back both.

## Safety

- Missing or malformed quota counters remain SQL NULL.
- No quota reservation is released or reconciled by this method.
- No retries, scheduler, credential access, HTTP client, prediction code or legacy odds selection are imported.
- The existing Neon staging database remains untouched until the upstream PR chain is reviewed and a separately guarded staging migration is explicitly run.
