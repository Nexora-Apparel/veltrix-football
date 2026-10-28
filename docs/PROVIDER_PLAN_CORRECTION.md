# Provider Plan Correction — Suspended API-Football

**Binding project constraint (2026-10-28): API-Football / API-Sports is suspended. Do not treat `API_FOOTBALL_KEY` as an active provider, primary source, fallback, or required credential.**

The earlier multi-source architecture draft incorrectly described API-Football/API-Sports as the primary existing provider. This correction supersedes that part of the draft.

## Required provider plan from the project owner

| Provider / store | Intended responsibility | Current status |
|---|---|---|
| 5DollarFootballAPI | Candidate source for fixtures, results, bookmaker odds and supported match statistics | To verify and integrate |
| InferSports | Secondary odds and market information; price comparison | To verify and integrate |
| The Odds API | Supplemental bookmaker odds and market coverage | To verify access, quota and coverage |
| Open Matchday | Supplementary historical fixtures, results and match statistics | To verify dataset/API, coverage and license |
| Existing Veltrix historical database | Preserve existing records and use as the historical/model-feature foundation | Preserve; audit gaps and provenance |
| Highlightly | Existing integration in the repository; assess as an available provider only if its credential/service remains usable | Must be verified; do not assume it is sufficient or the requested replacement |

## Implementation rules

1. Remove API-Football/API-Sports from active runtime dependencies and scheduled requests while suspended. Do not delete historical records or useful adapter code until dependency impact is audited.
2. Do not require `API_FOOTBALL_KEY` for builds, tests, daily reports, historical refreshes or deployment.
3. Audit the actual scheduled workflow and Telegram/dashboard paths; code presence is not proof that a provider is active.
4. Verify each proposed provider's exact official product, endpoint documentation, authentication, quota, competition coverage, odds markets, timestamps and terms before enabling it.
5. Implement adapters behind a common interface. Preserve raw-source identifiers and provenance.
6. Reconcile fixtures conservatively using competition, normalized teams and kickoff time; quarantine ambiguous matches.
7. Keep odds quotes separate by bookmaker, market, selection, line and quote timestamp. Do not combine stale or non-equivalent quotes.
8. Preserve the existing report pipeline, Telegram command centre, dashboard, historical store and paper ledger.
9. If no verified source can provide required data, report a clear coverage/provider error and withhold affected outputs. Never fabricate data or silently substitute stale records.
10. Keep betting/value alerts disabled until chronological out-of-sample evaluation supports them.

## Corrected order of work

1. Audit active workflows, configuration and all API-Football references.
2. Confirm which current integration can still serve fixtures/results without API-Football.
3. Verify 5DollarFootballAPI and the exact InferSports product from official documentation.
4. Verify The Odds API and Open Matchday independently.
5. Build provider health diagnostics and canonical schemas.
6. Add one verified adapter at a time, with unit tests and fixture-level reconciliation tests.
7. Run a shadow/canary comparison against existing reports before switching scheduled production runs.
8. Update Telegram and dashboard diagnostics to show real source status and provenance.

## Acceptance criteria

- API-Football suspension does not break the scheduled workflow.
- No request is made with `API_FOOTBALL_KEY` as an active dependency.
- Existing historical records and paper-tracking entries remain intact.
- Every published fixture, result and odds quote has traceable source provenance.
- Unavailable or unverified providers are shown as unavailable/unverified rather than reported as healthy.
