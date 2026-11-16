# Provider Plan Correction — Suspended API-Football

**Binding project constraint (2026-10-28): API-Football / API-Sports is suspended. Do not treat `API_FOOTBALL_KEY` as an active provider, primary source, fallback, or required credential.**

The earlier multi-source architecture draft incorrectly described API-Football/API-Sports as the primary existing provider. This correction supersedes that part of the draft.

## Required provider plan from the project owner

| Provider / store | Intended responsibility | Current status |
|---|---|---|
| 5DollarFootballAPI | **Primary** fixtures, recent results and eligible football observations; first-choice acquisition source | Integrated; entitlement and competition coverage must be rechecked against the current account response before each expansion |
| The Odds API | **Supplementary** bookmaker prices, market availability, quote timestamps and market benchmarks where the odds materially improve prediction research | Integrated adapter; use selectively. Do not make it the default fixture/results source or run it when no analytical question justifies the request. The one-event UK market probe measures actual bookmaker/market coverage and timestamp quality |
| OddsPapi | Optional separate BTTS and Over/Under enrichment | Existing adapter retained; non-blocking |
| InferSports | Optional full-time totals and 1X2 odds | Keyless events endpoint verified (200 same-day events), but three bounded odds probes returned no current quotes; adapter is feature-flagged off pending market evidence. No BTTS market in current schema |
| Open Matchday | Research-only current-season fixtures/results/statistics | Not ingested into production; evaluate the documented non-commercial license against the project's personal-use scope and preserve attribution/other license conditions |
| Existing Veltrix historical database | Preserve existing records and use only where provenance and temporal eligibility support the intended analysis | Preserved; source provenance is recorded for new rows and unknown legacy provenance is labelled |
| Highlightly | Existing legacy integration in the repository | Not a production dependency; do not assume its feed is active or mix it into the new provider path |

## Implementation rules

1. Remove API-Football/API-Sports from active runtime dependencies and scheduled requests while suspended. Do not delete historical records or useful adapter code until dependency impact is audited.
2. Do not require `API_FOOTBALL_KEY` for builds, tests, daily reports, historical refreshes or deployment.
3. Use 5DollarFootballAPI as the primary acquisition source. Verify each endpoint, competition and data domain against actual account entitlement; do not infer coverage from a successful unrelated endpoint.
4. Use The Odds API only for a defined analytical purpose: bookmaker coverage, market availability, timestamped odds baselines, closing-line research or out-of-sample model comparison. Record whether the data changes a feature, benchmark, evaluation or conclusion. If it adds no measurable value, do not spend requests/credits on it.
5. Provider usage controls (terms, entitlement, quotas, request caps and bounded spend) are operational safeguards. They are separate from model-quality and publication-integrity criteria.
6. The project is personal-use, not a commercial monetisation product. Do not require business registration, invoices, commercial subscription proof, billing documents or monetisation plans for model development, data collection, evaluation or release. Personal use does not waive provider terms, data rights or usage limits.
7. Audit the actual scheduled workflow and Telegram/dashboard paths; code presence is not proof that a provider is active.
8. Verify each proposed provider's exact official product, endpoint documentation, authentication, quota, competition coverage, odds markets, timestamps and terms before enabling it.
9. Implement adapters behind a common interface. Preserve raw-source identifiers and provenance.
10. Reconcile fixtures conservatively using competition, normalized teams and kickoff time; quarantine ambiguous matches.
11. Keep odds quotes separate by bookmaker, market, selection, line and quote timestamp. Do not combine stale or non-equivalent quotes.
12. Preserve the existing report pipeline, Telegram command centre, dashboard, historical store and paper ledger.
13. If no verified source can provide required data, report a clear coverage/provider error and withhold affected outputs. Never fabricate data or silently substitute stale records.
14. Keep betting/value alerts disabled until chronological out-of-sample evaluation supports them.

## Corrected order of work

1. **Completed:** remove API-Football/API-Sports from active daily workflow, CLI and Telegram odds requests.
2. **Completed:** integrate 5DollarFootballAPI as the primary fixture/results source and preserve the recent-results cache.
3. **Integrated, selective use:** The Odds API adapter supports h2h/totals and event-specific BTTS research; actual per-event bookmaker coverage and timestamp quality remain to be measured with the bounded one-event UK probe.
4. **Completed:** add normalization, conservative team/local-date joins, provider diagnostics and unit tests.
5. **Completed:** run GitHub Actions unit tests and bounded provider/market endpoint checks.
6. **Pending:** enable InferSports only after a live quote-bearing fixture is confirmed; keyless event access alone is not enough.
7. **Research-only:** use Open Matchday only where its non-commercial license is compatible with personal use and all attribution/other terms; do not ingest without rights approval.
8. **Ongoing:** monitor historical gaps and market coverage; keep value alerts disabled until chronological out-of-sample validation.

## Acceptance criteria

- API-Football suspension does not break the scheduled workflow.
- No request is made with `API_FOOTBALL_KEY` as an active dependency.
- 5DollarFootballAPI remains the primary source and its endpoint-level entitlement is verified.
- The Odds API is used only when its odds observations have a defined, measurable research purpose.
- Existing historical records and paper-tracking entries remain intact.
- Every published fixture, result and odds quote has traceable source provenance.
- Unavailable or unverified providers are shown as unavailable/unverified rather than reported as healthy.
