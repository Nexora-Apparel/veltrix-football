# VELTRIX FOOTBALL 2.0 — Account-Specific Provider Activation and Usage Guard

**Policy correction:** 2026-11-15  
**Status:** Offline activation decision; no provider dispatch or staging writes

## Purpose

Keep three independent checks separate before a credit-consuming Odds API request:

1. Account Terms and provider endpoint entitlement.
2. Source rights for the exact competition, market, region and intended research use.
3. Fresh observable quota plus a bounded local usage guard.

This gate protects provider access and the user's quota. It is not a model-quality gate and it is not a commercial billing verification workflow.

## Required evidence

- Provider/source identity: `the_odds_api` / `odds_api_v4`.
- Account reference consistent across Terms, rights and quota evidence.
- Accepted Terms version and immutable evidence URI/hash, where required by the provider's account/terms flow.
- Explicit APPROVED rights event with matching Terms version, effective/recorded timestamps, validity and exact competition/market/region/permitted-use scopes. Wildcards and empty scopes are rejected.
- Fresh provider quota observation with complete, valid quota headers, retrieval time, raw response hash and enough observed remaining credits for the proposed request.
- Local per-run credit cap, request-count cap, current run commitments, request fingerprint and dispatch time.
- For the VELTRIX one-event research probe: one future EPL event, UK region, `h2h`, `totals`, `btts`; maximum estimated cost 3 credits; exactly one credit-consuming request; no retries; staging-only persistence.

## Explicitly not required

- Invoice, receipt or payment evidence.
- Business registration or proof of commercial status.
- Commercial subscription or monetisation evidence.
- Billing-period start/end records or a declared monthly allowance.
- Monthly hard-cap calculations or a monthly headroom calculation.

Do not infer monthly allowance or billing-period boundaries from `x-requests-used`, `x-requests-remaining` or `x-requests-last`. Provider terms and actual endpoint entitlement remain binding regardless of personal use.

## Temporal and quota rules

- Terms acceptance and rights evidence must be available by the rights-evaluation time.
- Rights evaluation must precede dispatch; approval must be effective and not expired at evaluation.
- Quota observation must be no later than dispatch and must remain within its explicit freshness window.
- Remaining provider quota minus credits already committed since the snapshot must cover the estimated request cost.
- Remaining per-run credit cap must cover the estimate.
- Remaining request-count cap must permit exactly one request for this probe.
- Missing, malformed, stale or insufficient quota evidence fails closed for this Odds API request only. It does not block independent authorized 5DollarFootballAPI capture or model research.

## Model-quality separation

The activation gate must not decide whether a model is accurate or certified. Model-quality evaluation is handled by independent chronological walk-forward and prospective-settlement gates. A successful provider activation only means the bounded request may proceed; it does not certify bookmaker coverage, quote freshness, prediction value or publication eligibility.

## Current one-event probe status

The runbook is `docs/VELTRIX_V2_ODDS_API_ONE_EVENT_MARKET_PROBE_RUNBOOK_2026-11-15.md`. It is ready for a fresh no-credit quota preflight and a single capped request. The latest stored sports-catalogue quota observation is historical and cannot substitute for a fresh preflight. The connected GitHub integration does not expose workflow dispatch, so no credit-consuming event-odds request has been sent from this session.

## Decision outcomes

- `ALLOW_BOUNDED_REQUEST`: all Terms/rights/scope/time/quota/per-run/request-count checks pass.
- `DEFER_PROVIDER_REQUEST`: any required provider access, rights or quota evidence is missing, stale or insufficient. No retry; continue independent data/model work.
- `REJECT_REQUEST_SCOPE`: requested competition, market, region or intended use is outside approved scope.

Neither outcome authorizes public prediction publication, Telegram delivery, schedule activation or value betting.
