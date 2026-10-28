# Veltrix Football — Multi-Source Data Architecture

**Status:** Architecture baseline; provider integrations are not approved for production until individually verified.  
**Primary existing provider:** API-Football / API-Sports v3 via `API_FOOTBALL_KEY`.  
**Prediction status:** Experimental; no validated betting claims and no automatic bookmaker actions.

## Goals

1. Preserve the existing daily report, Telegram command centre, dashboard, historical cache, and paper-tracking ledger.
2. Separate fixture/results ingestion, historical features, odds collection, and prediction generation.
3. Add sources only after confirming the exact provider product, API base URL, authentication method, quota, competition coverage, market coverage, and permitted use.
4. Keep a full provenance trail so every normalized record can be traced to its provider and retrieval time.
5. Fail closed on ambiguous fixture matches, stale odds, invalid payloads, and unsupported market definitions.

## Proposed provider roles (candidate roles, not verified guarantees)

| Provider | Candidate responsibility | Approval gate |
|---|---|---|
| API-Football / API-Sports v3 | Primary fixtures, completed results, supported statistics, historical refresh, optional odds | Existing integration; audit all workflows and confirm live behavior |
| 5DollarFootballAPI | Candidate fixtures/results/odds source | Verify exact service/API documentation, endpoint behavior, pricing and coverage |
| InferSports | Candidate secondary odds/market source | Verify exact product identity, market schema, timestamps, quotas and access |
| The Odds API | Supplemental bookmaker prices | Verify available sports/markets, bookmaker coverage, quota and fixture matching |
| Open Matchday | Candidate open historical source | Verify canonical dataset/API, license, fields, update cadence and duplicate overlap |
| Existing Veltrix historical store and open-dataset import | Historical baseline and derived features | Audit freshness, gaps, identifiers, licensing and reproducibility |

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

1. **Audit current state:** map API clients, workflows, environment variables, historical data paths, report artifacts, Telegram commands, dashboard routes and paper ledger.
2. **Stabilize the primary path:** confirm `API_FOOTBALL_KEY` is the source used for fixtures/results/history and document any remaining legacy adapters.
3. **Add source registry and health diagnostics:** endpoint-level status, quota, coverage, freshness and safe error categories.
4. **Define canonical contracts and reconciliation tests:** fixtures, results and odds quotes.
5. **Integrate one secondary provider at a time:** verify documentation and test with fixtures before enabling it in scheduled runs.
6. **Build multi-source odds reconciliation:** quote freshness, bookmaker/market identity and best-price/consensus calculations.
7. **Evaluate prediction changes:** chronological tests against the current baseline.
8. **Connect health and provenance to reports, Telegram and dashboard.**
9. **Canary rollout:** compare output with the existing pipeline; retain a rollback path.

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
