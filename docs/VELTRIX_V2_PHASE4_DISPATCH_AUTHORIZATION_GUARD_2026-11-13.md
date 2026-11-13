# VELTRIX FOOTBALL 2.0 — Final Provider Dispatch Authorization Guard

**Date:** 2026-11-13  
**Status:** Offline-only guard; dispatch remains disabled  
**Parent:** Phase 4.5 durable quota evidence persistence

## Purpose

Define the final fail-closed decision immediately before a future provider HTTP adapter is allowed to dispatch one exact manifest-bound request. This guard does not perform HTTP, load secrets, reserve credits or change capture state.

## Required gates

A request is dispatchable only when all are true:
- provider is the explicitly supported The Odds API v4 provider
- endpoint URL uses HTTPS, exact approved host, documented v4 path and no credential-bearing query parameter
- manifest SHA-256 and request fingerprint are valid
- request fingerprint exactly matches the committed reservation fingerprint
- offline preflight is approved
- exact account Terms acceptance evidence is verified
- scoped source-rights approval is approved
- budget evidence is fresh and has not expired
- atomic credit reservation is committed for the same request
- capture state is CREDIT_RESERVED
- operator dispatch switch is explicitly enabled
- emergency stop is not active
- attempt is within the hard maximum of two
- retry attempts require authoritative reconciliation of the previous attempt

Any missing, malformed, mismatched or unknown input blocks dispatch. No override or inferred approval exists.

## URL boundary

Only api.the-odds-api.com over HTTPS is allowed. Only documented v4 discovery and odds endpoint path shapes are accepted. Credentials in URL userinfo or query parameters are rejected; the future adapter must use the x-api-key header and disable redirects.

## Safety boundary

The module returns a decision only. It has no network, secret, environment, database, scheduler or prediction imports. This guard is not a live capture authorization until the separate account-specific activation evidence is present and the operator explicitly enables dispatch.
