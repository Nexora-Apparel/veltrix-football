# Provider Plan Correction — Suspended API-Football

**Binding project constraint (2026-10-28): API-Football / API-Sports is suspended. Do not treat `API_FOOTBALL_KEY` as an active provider, primary source, fallback, or required credential.**

The earlier multi-source architecture draft incorrectly described API-Football/API-Sports as the primary existing provider. This correction supersedes that part of the draft.

## Required provider plan from the project owner

| Provider / store | Intended responsibility | Current status |
|---|---|---|
| 5DollarFootballAPI | Primary fixtures, recent results, and fixture-level bookmaker odds | Integrated and live-verified for fixtures/results. The odds endpoint returns market keys but the latest live report found no usable matched 5Dollar prices; The Odds API currently supplies the matched market quotes. |
| The Odds API | Supplemental bookmaker prices, h2h/totals and event-specific BTTS | Integrated and live-verified; soccer sports and target market endpoints passed. |
| OddsPapi | Optional separate BTTS and Over/Under enrichment | Existing adapter retained; non-blocking. |
| InferSports | Optional full-time totals and 1X2 odds | Keyless events endpoint verified (200 same-day events), but three bounded odds probes returned no current quotes; adapter is feature-flagged off pending market evidence. No BTTS market in current schema. |
| Open Matchday | Research-only current-season fixtures/results/statistics | Not ingested into production because the dataset README limits use to non-commercial purposes and only documents the current 2026/27 season. |
| Existing Veltrix historical database | Preserve existing records and use as the historical/model-feature foundation | Preserved; source provenance is recorded for new rows and unknown legacy provenance is labelled. |
| Highlightly | Existing legacy integration in the repository | Not a production dependency; do not assume its feed is active or mix it into the new provider path. |

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

1. **Completed:** remove API-Football/API-Sports from active daily workflow, CLI and Telegram odds requests.
2. **Completed:** integrate 5DollarFootballAPI as the primary fixture/results source and preserve the recent-results cache.
3. **Completed:** integrate The Odds API for bounded h2h/totals and event-specific BTTS prices; keep OddsPapi optional.
4. **Completed:** add normalization, conservative team/local-date joins, provider diagnostics, and unit tests.
5. **Completed:** run GitHub Actions unit tests and live provider/market endpoint checks.
6. **Pending:** enable InferSports only after a live quote-bearing fixture is confirmed; keyless event access alone is not enough.
7. **Research-only:** use Open Matchday only where its non-commercial license is compatible; do not ingest into production without license approval.
8. **Ongoing:** monitor historical gaps and market coverage; keep value alerts disabled until chronological out-of-sample validation.

## Acceptance criteria

- API-Football suspension does not break the scheduled workflow.
- No request is made with `API_FOOTBALL_KEY` as an active dependency.
- Existing historical records and paper-tracking entries remain intact.
- Every published fixture, result and odds quote has traceable source provenance.
- Unavailable or unverified providers are shown as unavailable/unverified rather than reported as healthy.
