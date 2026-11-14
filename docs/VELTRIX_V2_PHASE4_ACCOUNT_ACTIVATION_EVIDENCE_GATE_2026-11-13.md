# VELTRIX FOOTBALL 2.0 — Account-Specific Provider Activation Gate

**Date:** 2026-11-13  
**Status:** Pure offline evidence gate; no provider dispatch or staging writes

## Purpose

Combine three independent evidence domains immediately before any future Odds API request:
1. Account-specific accepted Terms evidence.
2. Source approval with exact competition, market, region and permitted-use scope.
3. Fresh provider quota/budget evidence with monthly, per-run and request-count headroom.

A successful result is a necessary precondition only. It does not itself reserve credits or authorize a network request; the transactional reservation and final dispatch guard remain separate gates.

## Required evidence

- Provider and source identity: `the_odds_api` / `odds_api_v4`.
- Opaque account reference shared by Terms, rights and budget evidence.
- Exact accepted Terms version and immutable evidence URI/hash.
- Explicit APPROVED rights event with matching Terms version, effective/recorded timestamps, validity and exact scope tuples. Wildcards and empty scopes are rejected.
- Budget snapshot for the same account and billing period, with positive monthly/per-run/request caps, non-negative provider remaining credits, evidence URI/hash and timezone-aware observation/expiry.
- Request scope, intended use, rights-evaluation time, dispatch time, estimated credits and already committed usage.

## Temporal rules

- Terms acceptance and its recorded evidence must both exist no later than rights evaluation.
- Rights approval must be effective and recorded no later than rights evaluation; rights evaluation must not occur after dispatch.
- Budget observation must be no later than dispatch; dispatch must be strictly before budget expiry.
- Billing period must contain the dispatch date.
- Missing, naive or invalid timestamps fail closed.

## Independent capacity calculations

- Monthly headroom = min(monthly allowance, monthly hard cap) − committed monthly credits.
- Per-run headroom = per-run hard cap − committed run credits.
- Provider headroom = provider-reported remaining credits − credits committed since that snapshot.
- Request-count headroom = request-count cap − requests already committed.

Estimated request cost must fit all three credit headrooms, and at least one request-count slot must remain. Unknown or malformed numbers are never converted to zero.

## Activation status

The currently documented manual evidence gaps remain:
- The account's exact accepted Terms version and acceptance evidence.
- A scoped, account-linked APPROVED rights record for the intended competitions/markets/regions/uses.
- Actual monthly allowance, remaining credits and explicit per-run/request-count caps.

Until those records are supplied and independently verified, this gate returns a blocked decision and the real provider transport remains disabled.
