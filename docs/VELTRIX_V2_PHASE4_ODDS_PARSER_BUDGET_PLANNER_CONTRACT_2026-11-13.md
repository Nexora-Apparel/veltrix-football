# VELTRIX FOOTBALL 2.0 — Odds Parser and Credit Planner Contract

**Date:** 2026-11-13  
**Status:** Offline implementation contract; no provider calls or database writes  
**Parent:** Phase 4.1 The Odds API prospective capture design  
**Branch:** `phase4/odds-parser-budget-planner-20261113`

## 1. Scope

Implement two isolated, pure components before enabling any provider adapter:

1. A strict parser that converts archived The Odds API v4 response bytes into normalized quote observations.
2. A deterministic credit planner that decides whether a proposed request is within a preconfigured run and monthly budget.

The components must not import, call, or share code with legacy prediction, probability, feature engineering, odds selection, calibration, or fallback modules. They must not perform HTTP, read credentials, write to PostgreSQL, schedule work, or publish predictions.

This contract does not authorize live provider requests. Account-specific Terms acceptance, scoped rights approval, actual allowance, current remaining balance and an explicit run cap remain external activation gates.

## 2. Module boundaries

Proposed package boundary (final paths must be reconciled with the repository's current package conventions before implementation):

- `veltrix_v2/providers/odds_api_v4/parser.py`
- `veltrix_v2/providers/odds_api_v4/budget.py`
- `veltrix_v2/providers/odds_api_v4/types.py`
- `tests/providers/odds_api_v4/test_parser.py`
- `tests/providers/odds_api_v4/test_budget.py`

Pure functions only:

- `parse_bulk_odds(raw_body: bytes, *, sport_key: str, retrieved_at: datetime) -> ParsedCapture`
- `parse_event_odds(raw_body: bytes, *, sport_key: str, event_id: str, retrieved_at: datetime) -> ParsedCapture`
- `plan_request(request: PlannedRequest, budget: CreditBudget) -> BudgetDecision`
- `reconcile_quota_headers(headers: Mapping[str, str]) -> QuotaEvidence`

No function accepts an API key. The parser receives exact archived bytes, not a decoded-and-reserialized object, so the caller can hash the original bytes before parsing.

## 3. Normalized observation contract

Every parsed observation contains:

- provider = `the_odds_api`
- provider_event_id
- sport_key
- bookmaker_key and bookmaker_title
- market_key (`h2h`, `totals`, or `btts`)
- selection_name exactly as supplied
- selection_key normalized without changing the original label
- decimal_price as a finite positive decimal
- point/total line when supplied by the provider
- source_published_at from the **market-level** `last_update`
- source_timestamp_raw preserving the exact timestamp string
- source_timestamp_basis = `provider_timestamp`
- retrieved_at supplied independently by the caller
- response_sha256 computed over the original response bytes
- request fingerprint supplied by the capture orchestrator, never containing credentials

Preserve bookmaker and market identity. Do not merge prices across bookmakers, lines, event IDs, or market versions.

## 4. Market parsing rules

### 4.1 Soccer 1X2 — `h2h`

- Preserve every outcome row and its original `name`.
- Soccer's draw selection is a normal outcome; do not discard it.
- Do not infer home/draw/away by array position.
- Team-to-canonical-side resolution belongs to the separately reviewed fixture/event crosswalk and must not use team-name-only matching.
- Missing or ambiguous selections remain explicit parse/identity exceptions; never synthesize a missing draw or side.

### 4.2 Totals — `totals`

- Preserve Over and Under as separate selections.
- Preserve the numeric `point` for each outcome.
- Different points are different market lines and must never be collapsed.
- Missing, non-finite, or malformed points are rejected from normalized quote output and retained in parse diagnostics.

### 4.3 Both Teams To Score — `btts`

- Parse only event-specific responses.
- Preserve Yes and No as distinct selections.
- Do not infer BTTS availability from endpoint success or another bookmaker's response.
- Do not fabricate a BTTS quote when the market is absent.

## 5. Timestamp and data-integrity rules

- Use market-level `last_update` only. Ignore deprecated bookmaker-level `last_update`.
- Parse only timezone-aware timestamps. Preserve the raw provider string.
- Missing, malformed, or naive market timestamps produce an ineligible observation with a stable diagnostic reason; they must not be assigned retrieval time.
- The parser does not decide whether a quote was published before a fixture cutoff. The downstream temporal eligibility validator performs that comparison against a frozen cutoff.
- Do not sort or select a "best" bookmaker price in the parser.
- Duplicate payload rows are reported deterministically; do not silently deduplicate distinct market lines or quote revisions.
- Raw response hash is SHA-256 of exact input bytes. JSON reserialization must never be used as the hash input.

## 6. Credit planner contract

The planner must operate before network I/O and fail closed.

Inputs:
- monthly allowance (integer credits)
- provider-reported remaining credits (integer, when available)
- configured monthly hard cap (integer)
- configured per-run hard cap (integer)
- credits already committed in the current month
- credits already committed in the current run
- request shape: endpoint class, sport key, region count, requested markets, or event-specific request

Rules:
1. Reject missing, zero, negative, non-integer, or internally inconsistent budget values.
2. Bulk current-odds request estimate = number of requested unique markets × number of regions, per sport request.
3. Event-specific odds estimate = number of unique markets returned per region; because the response is not known before the request, use a conservative preflight upper bound based on requested markets × regions. Reconcile actual provider usage after the response.
4. Discovery endpoints `/sports` and `/events` have zero odds-credit estimate, but still require rate and request-count controls in the orchestrator.
5. Reject before I/O if the request would exceed any of: available allowance, monthly cap, remaining monthly cap, per-run cap, or provider-reported remaining balance.
6. Never assume that a 429, authentication failure, entitlement failure, timeout, or exhausted-credit response consumed zero credits. Reconcile from provider headers where available; uncertain consumption is reserved against the budget until reconciled.
7. Retries require a new preflight decision and a bounded retry policy. No automatic retry for authentication, entitlement, or exhausted-credit errors.
8. The planner never reads environment variables, secrets, current time, or provider state. All budget inputs are explicit immutable values.

A decision returns `allowed`, `estimated_credits`, `remaining_run_credits`, `remaining_monthly_credits`, and a stable reason code. Rejections must not mutate the supplied budget.

## 7. Quota evidence

Read and preserve only safe quota headers:

- `x-requests-used`
- `x-requests-remaining`
- `x-requests-last`

Header parsing is case-insensitive. Missing or malformed values remain unknown and trigger reconciliation failure; never replace unknown values with zero. Do not persist arbitrary response headers because they may contain sensitive or irrelevant data.

## 8. Required offline test matrix

### Parser
- Valid soccer `h2h` with Home, Draw, Away in varying order.
- Missing draw is not silently synthesized.
- Valid `totals` with multiple lines preserves every line and both selections.
- Valid event `btts` preserves Yes and No.
- Missing market returns an explicit absent-market diagnostic.
- Market timestamp wins even when bookmaker timestamp differs.
- Missing, malformed, and timezone-naive market timestamps are ineligible.
- Invalid prices (zero, negative, NaN, infinity, non-numeric) are rejected.
- Missing bookmaker identity is diagnosed.
- Exact raw-byte SHA-256 is stable and differs when any byte changes.
- Duplicate identical rows are diagnosed without collapsing different lines or timestamps.
- Malformed JSON and unexpected response shapes fail with stable parser errors.

### Budget
- Bulk request estimate matches markets × regions.
- Event-specific estimate uses the conservative requested-market upper bound.
- Discovery request estimates zero credits.
- Exact cap boundary is allowed; one credit over is rejected.
- Monthly cap, allowance, provider remaining, and run cap are independently enforced.
- Missing or inconsistent budget inputs fail closed.
- Unknown quota headers remain unknown, never zero.
- Retry preflight is required for every attempt.
- Rejected request leaves input budget unchanged.

### Isolation and safety
- Tests monkeypatch/guard network access and prove no HTTP client is imported or invoked.
- Tests prove no environment variable or API key is read.
- Tests prove no legacy prediction/odds-selection modules are imported.
- No tests require database credentials or a Neon connection.
- No workflow schedules or provider-ingestion workflows are added in this component.

## 9. Completion criteria

The implementation is eligible for code review only when:
- parser and planner are pure and deterministic;
- the full offline test matrix passes on the repository's supported Python versions;
- lint/type checks pass;
- the diff contains no secrets, network calls, DB writes, workflow schedules, prediction logic, or legacy imports;
- no The Odds API request has been made.

Passing these tests does not satisfy provider-rights approval, point-in-time coverage, model certification, or value-bet release gates.
