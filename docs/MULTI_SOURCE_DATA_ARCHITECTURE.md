# Veltrix Football — Multi-Source Data Architecture

**Status (2026-10-28):** Phase 1 multi-source fixture and odds adapters are integrated and live-verified. InferSports and Open Matchday remain unverified candidates.  
**Primary active provider:** 5DollarFootballAPI via `FIVEDOLLARFOOTBALL_API_KEY`.  
**Supplemental odds:** The Odds API via `THE_ODDS_API_KEY`, with optional OddsPapi enrichment.  
**Suspended provider:** API-Football / API-Sports v3 is disabled in production.  
**Prediction status:** Experimental; no validated betting claims and no automatic bookmaker actions.

## Goals

1. Preserve the existing daily report, Telegram command centre, dashboard, historical cache, and paper-tracking ledger.
2. Separate fixture/results ingestion, historical features, odds collection, and prediction generation.
3. Add sources only after confirming the exact provider product, API base URL, authentication method, quota, competition coverage, market coverage, and permitted use.
4. Keep a full provenance trail so every normalized record can be traced to its provider and retrieval time.
5. Fail closed on ambiguous fixture matches, stale odds, invalid payloads, and unsupported market definitions.

## Proposed provider roles (candidate roles, not verified guarantees)

| Provider | Responsibility | Current evidence / gate |
|---|---|---|
| 5DollarFootballAPI | Primary same-day fixtures, incremental recent results, and fixture-level BTTS/goal-line odds | Live auth and fixture access passed; actual odds endpoint returned 1X2, BTTS, goal-line and fixed goal-line markets. Partial history failures are retained as retryable gaps. |
| The Odds API | Supplemental bookmaker h2h and totals prices; event-specific BTTS | Live auth, active soccer sports, h2h/totals endpoint and BTTS event endpoint passed. The integration check used three odds credits; daily requests are bounded. |
| OddsPapi | Optional secondary BTTS and Over/Under enrichment | Existing adapter retained and included in the combined market-coverage count; keep non-blocking. |
| InferSports | Candidate secondary odds/market source | Not integrated or verified; requires exact product/auth/market review and a credential before enabling. |
| Open Matchday | Candidate supplementary historical fixtures/results/statistics | Not integrated or verified; repository/API delivery, coverage and license must be checked before ingestion. |
| Existing Veltrix historical store and open-dataset import | Long-term historical baseline and derived features | Preserved. Recent results are merged with source provenance and provider IDs remain source-local. |

Do not treat similarly named services as interchangeable. Do not add a provider merely because its name appears in a plan; verify the exact official documentation and API identity first.

## Canonical data contracts

### Fixture
- `fixture_key`: deterministic Veltrix identity derived from normalized competition, home/away teams and kickoff timestamp; retain all source IDs separately.
- `provider_ids`: provider name → source fixture ID.
- `competition`, `season`, `home_team`, `away_team`.
- `kickoff_utc`, `kickoff_local_date`, `status`.
- `first_seen_at`, `last_seen_at`, `source_provider`, `source_updated_at`.

### Result
- Canonical fixture key, full-time home/away goals, result status, source provider and retrieval timestamp.
- Only completed and valid results enter historical model features.

### Odds quote
- Canonical fixture key, provider fixture ID, bookmaker, market key, selection key, line/handicap, decimal price, currency/settlement metadata when available.
- `quoted_at`, `retrieved_at`, `source_provider`, source market/selection labels, and freshness status.
- Never merge quotes across different lines, settlement definitions, or incompatible market periods.

### Prediction
- Canonical fixture key, model/version, feature cutoff timestamp, probabilities, sample/data-quality indicators, generation timestamp and validation status.
- Predictions must be generated without using information that became available after the feature cutoff.

## Reconciliation and quality rules

1. Preserve raw provider payloads or a safe, reproducible raw-data reference; never discard provenance during normalization.
2. Prefer provider IDs for source-local updates. Cross-provider fixture matching uses competition, normalized team names, kickoff proximity and timezone-aware dates; ambiguous matches are quarantined, not guessed.
3. Store source records separately from canonical entities. Deduplicate canonical fixtures without erasing distinct bookmaker quotes.
4. Treat team aliases as explicit mappings; never fuzzy-match teams silently when the match is uncertain.
5. Track freshness and source health per endpoint, competition and market.
6. A failed provider can trigger a configured fallback only for the same data type. A fixture provider cannot silently replace an odds provider or prediction model.
7. Do not publish odds without bookmaker, market, selection, line (where relevant), timestamp and a safe fixture match.
8. Empty data, authentication failure, quota exhaustion and unsupported coverage must remain distinct statuses.

## Odds intelligence

- Normalize market and selection labels into canonical keys such as `BTTS_YES`, `BTTS_NO`, `TOTAL_GOALS_OVER_2_5`, and `TOTAL_GOALS_UNDER_2_5`.
- Compare prices only for the same fixture, market, line, settlement rules and compatible quote time.
- Calculate implied probabilities and remove overround only when a complete, mutually exclusive market is available.
- Best-price discovery is descriptive, not a recommendation. Model probability and expected-value screening remain separate.
- Keep value alerts disabled until chronological out-of-sample evaluation, calibration and paper tracking support them.

## Prediction evaluation

Primary target markets: BTTS Yes/No and full-time Over/Under 1.5, 2.5 and 3.5 goals.

- Establish a baseline before adding new provider features.
- Use chronological walk-forward splits; prevent future-data leakage.
- Report Brier score, log loss, calibration, coverage, freshness, and performance by competition and date window.
- Compare models on identical fixtures with complete inputs.
- Do not count duplicated or correlated provider data as independent evidence.
- New models/providers cannot replace the production path automatically; require a measured holdout improvement and regression tests.

## Implementation sequence

1. **Completed:** remove API-Football/API-Sports from active workflows, CLI and Telegram odds calls.
2. **Completed:** use 5DollarFootballAPI for primary fixtures/results and preserve the existing history/cache with source provenance.
3. **Completed:** integrate The Odds API h2h/totals and bounded event-specific BTTS enrichment; retain optional OddsPapi.
4. **Completed:** add provider smoke checks, bounded live market probes, fixture normalization and local-date/team reconciliation tests.
5. **Completed:** run unit tests and a live integration probe; see `scripts/verify_multi_source_integration.py` and the GitHub Actions workflow.
6. **Pending:** verify InferSports product/auth/markets and Open Matchday dataset/API/license before any integration.
7. **Pending:** expand canonical odds persistence to a durable quote table if the existing report artifact is no longer sufficient.
8. **Pending:** monitor daily provider coverage and historical gaps; do not infer provider health from code presence alone.
9. **Separate model gate:** evaluate any prediction changes on chronological holdout data before enabling value alerts.

## Current known risks to audit

- Legacy Highlightly configuration may remain in `app/config.py` even though the daily pipeline has moved to API-Football.
- Multiple odds integrations may be present and must be clearly isolated by provider and responsibility.
- API-Football free-tier quota and competition coverage are limited; daily workflows must avoid wasteful requests.
- Historical refresh may have date gaps. Imported open data and live API data must not be assumed to be interchangeable without schema and provenance checks.
- Existing backtest results show the market benchmark outperforming current model baselines in reported samples. The system must keep experimental labeling and betting/value alerts disabled.

## Definition of done

- Provider adapters have deterministic normalized output and isolated tests.
- Reconciliation is idempotent and ambiguous matches are rejected.
- Provider failure and quota exhaustion do not corrupt saved reports or paper ledgers.
- Each report can explain which providers supplied each fixture, result, and odds quote.
- Full automated tests pass; live verification is separately recorded.
- No claim of improved accuracy until holdout metrics demonstrate it.
