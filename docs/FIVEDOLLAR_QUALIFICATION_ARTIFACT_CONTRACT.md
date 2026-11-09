# 5DollarFootballAPI Qualification Artifact Contract

Status: REQUIRED — provider-specific evidence design. This contract does not authorize provider calls, production imports, Neon writes, prediction publication, schedule changes, or PR merges.

## 1. Existing evidence and gap

The bounded 5DollarFootballAPI preflight verified read-only access to five competitions and 488 settled results in its measured 90-day window. However, the inspected GitHub Actions run `42504992170` has no retained Actions artifact. Its workflow emitted console summaries only.

That run is useful engineering evidence, but it cannot be admitted to the qualification registry because an offline reviewer cannot independently download and hash a machine-readable report from that run. Its event was also `push`, while the qualification policy requires an explicitly approved manual dispatch.

## 2. Required future workflow

The provider qualification workflow must be manual-dispatch only for live provider requests. Push and pull-request events may run secret-free unit tests, but must never spend provider quota.

Expected workflow:
- File: `.github/workflows/verify-data-providers.yml`
- Provider: `5DollarFootballAPI`
- Credential: existing `FIVEDOLLARFOOTBALL_API_KEY` Actions secret
- Maximum request budget: explicit and enforced before the first request
- Scope: only competitions returned by the authenticated account catalog
- Date window: exact UTC start/end timestamps recorded in the report
- Read-only: no database connection, import, checkpoint, canonical merge, or prediction publication

The workflow must stop and report incomplete coverage when pagination exceeds its configured cap. It must not silently qualify a truncated competition.

## 3. Sanitized report schema

The verifier must write exactly one JSON report with:
- `schema_version`
- `mode = read_only_5dollar_competition_qualification`
- `provider = 5DollarFootballAPI`
- `retrieved_at` in UTC
- `window_start_utc` and `window_end_utc`
- `request_budget`: maximum requests, actual requests, and per-endpoint accounting
- `competition_count` and exact provider competition IDs/names
- Per-competition result checks: page count, source rows, accepted rows, invalid rows, duplicate IDs, missing team IDs, pagination-complete flag
- Aggregate counters that exactly equal the per-competition sums
- Explicit zero-valued side-effect counters for database writes, imports, checkpoints, canonical merges and prediction publications
- `acceptance_pass`, recomputed by the reviewer rather than trusted as proof

The report must not contain API keys, authorization headers, request URLs containing credentials, unrestricted raw provider payloads, or personally identifying account details.

## 4. Artifact requirements

The workflow must upload exactly one named artifact, for example `fivedollar-competition-qualification`, containing exactly one report. Retention should be short and explicit (7 days is sufficient for review).

The reviewer must obtain run and artifact metadata directly from the authenticated GitHub API and verify:
1. Exact repository, workflow path, workflow_dispatch event, successful completion, branch and head SHA.
2. Exactly one expected artifact attached to that run; artifact is not expired.
3. GitHub artifact digest equals the locally computed SHA-256 of downloaded archive bytes.
4. Exactly one expected report exists inside the archive; size and archive-entry limits are enforced.
5. The report's exact competition scope matches the provider catalogue observed by that run.
6. All competition pages are complete; no invalid rows, duplicate IDs, unresolved team IDs or accounting discrepancies exist.
7. Each qualified competition has actual accepted final-result observations in the measured window.
8. The report's measured scope is not widened beyond the observed evidence.
9. All prohibited side-effect counters are zero.

The reviewer then emits a registry entry signed with the existing `VELTRIX_QUALIFICATION_ATTESTATION_KEY` HMAC scheme. The signature must bind repository, workflow run, branch, commit, artifact ID/digest, local report hash, reviewer identity/time, and exact competition/date scope.

## 5. Qualification boundary

Qualification applies only to the measured 5DollarFootballAPI fixture/results product and exact competition IDs, names, and UTC date window. It does not qualify lineups, events, xG, odds, player data, future seasons, or other providers.

A successful bounded 90-day preflight is not proof of full-season history or continuous availability. Empty or inaccessible competitions remain unqualified. The current five-league Free-plan access must not be generalized to competitions not returned by the account catalogue.

## 6. Current status

- Historical preflight: bounded 488-result read-only sample reported successful, but its push-triggered run has no artifact and is not admissible qualification evidence.
- The manual-only qualification workflow, bounded request ledger, sanitized report, artifact upload, offline reviewer, HMAC registry builder, and provider-specific daily-selector admission checks are implemented on PR #43.
- Secret-free CI validates report schema, UTC window, catalogue completeness, fixture/team identity, per-row accounting, request-to-page accounting, budget exhaustion, artifact integrity, signature scope, and zero side effects.
- The latest changes add fail-closed checks for malformed catalogue rows, missing/empty/colliding team IDs, fixture identity, and exact endpoint/page reconciliation.
- A request-budget-exhausted run may still produce a valid but non-qualifying report for audit; it cannot create qualified registry entries.
- The manual qualification workflow has not been dispatched. No provider credits have been consumed by this pipeline.
- Registry admission remains blocked until a successful manual run produces a complete report/artifact and the offline reviewer verifies it. The protected HMAC signing secret must also be configured in the execution environment.
- Qualification is restricted to the exact competitions and results window returned by the authenticated account catalogue. It does not imply access to other leagues, xG, lineups, events, odds, or future seasons.

No provider request, production import, Neon write, prediction publication, Telegram delivery, schedule restart, or PR merge is authorized by this contract.
