# VELTRIX FOOTBALL 2.0 — Mocked Provider Transport Envelope Contract

**Date:** 2026-11-13  
**Status:** Contract and mock-only response handling; no real HTTP implementation  
**Parent:** Phase 4.6 dispatch authorization guard

## Boundary

This component defines the exact request policy passed to a future transport and validates a raw response envelope returned by an injected transport. It does not implement sockets, HTTP clients, credential loading, retries or network access.

## Request policy

- GET only
- HTTPS endpoint already approved by the dispatch guard
- redirects disabled
- connect timeout: 5 seconds
- read timeout: 10 seconds
- maximum response body: 2,000,000 bytes
- no automatic retry
- API credential injection remains the responsibility of a future isolated secret-aware adapter and is not part of this module

## Response envelope

- preserve raw body bytes exactly
- compute SHA-256 over the exact raw bytes before parsing
- require timezone-aware retrieval timestamp
- preserve only exact raw strings for x-requests-used, x-requests-remaining and x-requests-last
- reject duplicate case-insensitive quota header names
- never convert missing/malformed quota headers to zero
- preserve HTTP status without interpreting provider errors as successful data
- reject oversized or non-byte response bodies
- never log or expose authorization headers, cookies or credentials

## Failure semantics

A transport exception after a request may have reached the provider is OUTCOME_UNCERTAIN. This module does not retry. The caller must retain the credit reservation until quota evidence reconciles the attempt.

The only supported transport in CI is an in-memory fake. Real transport implementation remains blocked until the account-specific provider Terms, scoped rights, quota evidence and explicit operator activation are verified.
