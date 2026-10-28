# Veltrix Football

Football analytics and experimental prediction platform. The production fixture/result source is **5DollarFootballAPI**; bookmaker odds are enriched from 5DollarFootballAPI, **The Odds API**, and optionally the existing OddsPapi adapter. Historical records, model code, Telegram command centre, dashboard, and paper-tracking ledger are preserved.

## Active multi-source architecture

- **5DollarFootballAPI** — primary same-day fixtures and incremental recent results, normalized into Veltrix's existing fixture schema. The API is authenticated through the repository secret `FIVEDOLLARFOOTBALL_API_KEY`.
- **The Odds API** — supplemental bookmaker prices. The scheduled pipeline requests head-to-head and Over/Under markets only for relevant supported competitions, then checks event-specific BTTS markets for at most three events per report to control the monthly credit budget. The secret is `THE_ODDS_API_KEY`.
- **InferSports** — a keyless adapter is implemented for full-time totals and 1X2. Live connectivity and 200 same-day event records were verified, but three bounded event-odds probes returned no current quotes. It is therefore **disabled by default** (`VELTRIX_ENABLE_INFERSports=false`) until actual market coverage is demonstrated. It does not provide BTTS in its current API schema.
- **OddsPapi** — optional independent BTTS and Over/Under enrichment, still non-blocking and separate from the primary fixture source. Secret: `ODDSPAPI_API_KEY`.
- **Existing historical database and open match dataset** — retained as the long-term modelling foundation. Recent 5DollarFootballAPI results are merged into the resumable recent-results cache using date, competition and normalized home/away identity; provider fixture IDs are not assumed to match across providers.
- **Reconciliation** — market prices are attached only when normalized home/away names and the Africa/Lagos kickoff date match. Missing, incomplete or ambiguous prices are omitted; no odds are fabricated and no provider's market prices overwrite the model's forecast probabilities.
- **Quota safety** — fixture odds requests from 5DollarFootballAPI are capped per report, and The Odds API queries only report-relevant supported competitions with a hard cap on event-specific BTTS calls. Provider errors remain non-fatal for optional odds enrichment but primary fixture/result failure stops the live report rather than publishing invented fixtures.
- **Suspended provider** — API-Football/API-Sports is not an active runtime dependency. Its historical adapter code is retained for audit/compatibility, but the daily workflow, history refresh and Telegram odds commands do not call it or require `API_FOOTBALL_KEY`.

## Requirements and secrets

- Python 3.11+
- GitHub Actions secrets: `FIVEDOLLARFOOTBALL_API_KEY` and `THE_ODDS_API_KEY`
- Optional secrets: `ODDSPAPI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `TELEGRAM_WEBHOOK_SECRET`

Never put real keys in source code or commit them.

## Provider verification

- `scripts/verify_data_providers.py` checks both API credentials and basic response access without printing keys or consuming The Odds API odds credits.
- `scripts/verify_multi_source_integration.py` performs a bounded live fixture/market probe. It checks up to three 5Dollar fixture odds boards, up to three The Odds API sport odds endpoints, and at most one event-specific BTTS endpoint. Market availability can legitimately be empty for a given competition.
- Workflow: **Multi-Source Provider Verification** in GitHub Actions.
- `app/provider_adapters.py` owns provider authentication, schema normalization, local-date/team matching, quota-aware odds retrieval and source-level diagnostics.

## Prediction and publication safeguards

Predictions are experimental and not validated for betting. The current Elo and Poisson models have underperformed the market benchmark in historical comparisons. BTTS and Over/Under probabilities are research estimates, not betting tips. Keep value alerts disabled until chronological out-of-sample validation, calibration, and a suitable market comparison pass. No bookmaker actions are performed.

## Daily pipeline

The daily GitHub Actions workflow runs at 06:00 Africa/Lagos, fetches same-day fixtures, refreshes recent completed results using the resumable cache, generates the report, performs bounded odds enrichment, updates paper tracking, publishes command data, and optionally sends Telegram messages. If the primary fixture provider fails, no fallback fixtures or fabricated predictions are published. Optional odds-source failure does not block an otherwise valid report.

The Telegram `/odds` command reads saved BTTS/Over-Under market prices; `/oddsdiag` inspects the saved provider coverage summary without making new provider calls. The dashboard displays the published report and matched market-odds counts. These are report snapshots, not a real-time trading interface.

## Open historical dataset import (2020–present)
Veltrix can import completed match records from the public [Club-Football-Match-Data dataset](https://github.com/xgabora/Club-Football-Match-Data), whose repository identifies an MIT license. The raw dataset is **not** committed to this repository. Run:

```bash
python -m scripts.import_open_dataset --from 2020-01-01 --to 2026-10-23 --output data/open_historical_matches.csv
```

The importer discovers the source CSV path from the repository tree, validates required fields, normalizes scores, team names, date, available Elo/form/odds/statistics, skips malformed rows, and deduplicates by competition/date/home/away. Its summary reports match counts by competition code and calendar year so coverage gaps can be diagnosed. Optional odds and statistics remain empty when missing. A successful import on 2026-10-24 produced 70,444 completed matches across 38 competition codes from 2020-01-01 through 2026-10-24 (one malformed row skipped). The GitHub Actions workflow can run manually or weekly and uploads the generated CSV as an artifact for 30 days; this artifact is not a permanent database.

## Value screening safeguards
`app/value_bets.py` provides a conservative candidate filter, not a proven prediction model. It:
- removes the proportional bookmaker margin from a complete set of market odds before calculating probability edge;
- requires a minimum 4 percentage-point edge and 5% theoretical expected return by default, with an odds range of 1.50–4.00;
- returns no candidates by default unless the caller explicitly marks the model as validated;
- labels passing selections `CANDIDATE_NOT_GUARANTEED`.

The `model_validated` switch is a safety gate, not proof of validation. It must remain false until a chronological, out-of-sample backtest and calibration review have passed. The expected-return calculation is theoretical and does not account for odds movement, limits, execution, or bookmaker restrictions. Do not publish selections as "value bets" merely because this mathematical filter passes.

## Chronological model comparison (new)
Run a historical evaluation after importing the CSV:

```bash
python -m pytest -q
python -m scripts.run_backtest --input data/open_historical_matches.csv --output reports/backtest_summary.json
```

The backtest compares league-aware venue-specific Poisson and Elo baselines, the live recent-goals Poisson pipeline, competition-scoped Elo, and a separate recency-weighted Dixon-Coles candidate. The Dixon-Coles candidate uses exponentially weighted recent venue form and a low-score correction (initial rho = -0.05); rho is not yet fitted, so this model is explicitly experimental and is never promoted automatically. Daily reports promote competition Elo to the primary forecast only when the fixture maps to a supported historical division and has enough team history; otherwise Poisson remains primary. It uses walk-forward predictions made before same-day results are ingested, and reports multiclass Brier score, log loss, result accuracy, calibration diagnostics, a recent-date holdout, per-competition live-model metrics, and market comparisons on identical fixtures with usable odds. GitHub Actions uploads a report artifact.

**Latest live-model evaluation (historical snapshot through 2026-09-03):**
- **Recent-goals Poisson:** 67,544 forecasts; 45.02% accuracy, Brier 0.6441, log loss 1.0680. On 67,486 fixtures with odds, the model scored 44.99% / 0.6443 / 1.0684 versus the de-vigged market at 50.21% / 0.6003 / 1.0037.
- **Competition Elo alternative:** 66,620 forecasts; 48.22% accuracy, Brier 0.6191, log loss 1.0311. On 66,564 fixtures with odds, Elo scored 48.20% / 0.6192 / 1.0313 versus the market at 50.21% / 0.6002 / 1.0036.
- **Recent Elo holdout:** 11,445 fixtures with odds; Elo scored 48.98% accuracy, Brier 0.6137, log loss 1.0232 versus the market at 50.69% / 0.5980 / 1.0004.

**Advanced-model check (2026-10-25):** a recency-weighted Dixon-Coles candidate was tested on 67,544 walk-forward fixtures. It scored 44.82% accuracy, Brier 0.6450, and log loss 1.0700, worse than the existing recent-goals Poisson pipeline (45.02%, 0.6441, 1.0680). On the latest 20% date holdout (11,607 fixtures), Dixon-Coles scored 0.6441 Brier / 1.0688 log loss, again worse than Poisson at 0.6429 / 1.0664. It therefore remains a research-only alternative and is **not** promoted to primary. Its rho parameter is a fixed initial value, not calibrated.

Elo is materially better than the current Poisson model on these historical metrics, but still underperforms the market benchmark. In the full-period same-fixture comparison, neither live model beats the de-vigged market on both Brier score and log loss in any of the 38 evaluated divisions. Historical odds timestamps and closing-line quality have not been verified, so neither model is validated for betting. Keep betting slips and value alerts disabled; these metrics are not evidence of profitability.

The live report also includes an explicitly non-predictive rest/congestion context (days since the prior match and matches in the previous 14 days), calculated only from historical match dates. It is not used to change probabilities until its effect is independently tested. Confirmed injuries, suspensions, lineups, and true xG are not assumed when the selected feed does not supply verified data.

## Retrospective paper tracking

A saved daily report can be scored against the completed-fixture response for the same date without placing bets. The daily report uses competition-scoped Elo as the primary 1X2 estimate when the fixture maps to a supported historical division and both teams have enough prior competition matches. In that case, the recent-goals Poisson probabilities are shown as an alternative and its expected-goal/total estimates remain auxiliary. When the Elo history is unavailable, Poisson remains primary and a global-fallback Elo estimate is shown only if it meets the minimum-history gate. The report labels which model is primary and the Elo history scope. The scheduled/manual daily workflow attempts to evaluate the previous day's report, matches forecasts by fixture ID, excludes withheld/invalid predictions and unfinished fixtures, and updates a cumulative ledger with result accuracy, multiclass Brier score, and log loss, separated by model version so results from different algorithms are not mixed. Both model versions are tracked separately in the cumulative paper ledger, regardless of which is primary for a particular fixture. When a ledger is available, the Telegram report also shows cumulative paper metrics for each model version. The ledger is uploaded as a 90-day artifact; this is not a permanent database, and an evaluation is skipped if the previous report cannot be found or results cannot be fetched. This is a scoring tool, not a betting approval gate.

Example after saving the 5DollarFootballAPI results JSON for that date:

```bash
python scripts/evaluate_paper_predictions.py --report reports/daily_predictions.json --results reports/completed_fixtures.json --output reports/paper_evaluation.json
```

## Daily fixture-to-prediction pipeline (experimental)

The daily workflow is scheduled for 06:00 Africa/Lagos (05:00 UTC) and can also be started manually. It includes only fixtures whose kickoff date is the same calendar date in Africa/Lagos as the report date and whose kickoff time is still in the future; tomorrow/later fixtures and already-started fixtures are excluded even when the API returns UTC timestamps. Add `FIVEDOLLARFOOTBALL_API_KEY` and `THE_ODDS_API_KEY` under repository Settings → Secrets and variables → Actions → New repository secret. To enable Telegram delivery, also add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Never put these values in source code or commit them. The workflow imports historical scores, runs the unit tests, fetches fixtures for the requested Nigeria-time date, adds bounded real BTTS/Over-Under odds where safely matched, sends the explicitly experimental report to Telegram when delivery secrets are present, and uploads a JSON report artifact retained for 90 days. If Telegram secrets are absent, delivery is skipped without exposing credentials.

Run locally after importing historical data:

```bash
python scripts/import_open_dataset.py --from 2020-01-01 --to YYYY-MM-DD --output data/open_historical_matches.csv
python scripts/run_daily_predictions.py --date YYYY-MM-DD --history data/open_historical_matches.csv --output reports/daily_predictions.json
```

The daily job refreshes completed results after the open CSV's latest date through yesterday using 5DollarFootballAPI's date-filtered fixture endpoint, with bounded seven-day windows and one request per calendar day. Accessible results are retained and dates the provider cannot serve are recorded as history gaps rather than treated as covered. A versioned cache prevents records from the former Highlightly feed from being mixed into the new history. Current-day results are excluded to prevent leakage. Real bookmaker BTTS and Over/Under prices are enriched from 5DollarFootballAPI and The Odds API, with optional OddsPapi enrichment. Matching is restricted to normalized teams and the Africa/Lagos kickoff date; missing or ambiguous prices are omitted.

For 1X2 probabilities, competition-scoped Elo is selected as primary only when the fixture maps to a supported historical division and the competition/team history gates pass. Otherwise, the recent-goals Poisson model remains primary; a global-fallback Elo estimate is only shown as a labelled alternative when its history gate passes. Expected goals, BTTS, over/under 2.5 and likely scorelines remain Poisson-derived, including when Elo is primary. When exact team history is missing, the report may show close-name suggestions for diagnosis but never applies fuzzy matches automatically.

The system is **experimental and not validated for betting**. Historical walk-forward tests show that the current models still underperform the market benchmark. Multi-source odds retrieval, the Telegram command centre and the mobile dashboard are implemented; their live report coverage must still be monitored. The bot does not generate normal 10.00-odds slips or 50.00–100.00-odds value slips; both remain disabled until the model passes chronological out-of-sample validation and market comparison. Reports include model mix, history freshness, result-refresh coverage, and separate fixture counts for future kickoffs, past kickoffs and excluded dates/statuses. Unmapped competitions with insufficient exact team history are summarized separately as unsupported, rather than being mixed into the missing-history count. Long reports are split across multiple Telegram messages instead of dropping later fixtures.

## Model safety
Use only information available before kickoff as predictors. Full-time/half-time scores, shots and cards are post-match outcomes and must not be used as pre-match features. Never randomly split time-series match data; train on earlier matches and evaluate on later matches. Report Brier score/log loss, calibration, number of selections, ROI, yield, and drawdown alongside a market baseline. Historical odds coverage varies by league and season, and the open dataset does not cover every competition worldwide.

## Project status and remaining work
1. API connection and response validation: 5DollarFootballAPI is the primary provider; live smoke checks verify account access and fixture retrieval.
2. Historical fixture export and leakage-safe rolling features: implemented and covered by automated tests.
3. Open historical data import: implemented; CI successfully imported the available historical dataset.
4. Baseline modelling: Poisson attack/defence and Elo are implemented and evaluated chronologically.
5. Backtesting and calibration diagnostics: implemented; CI runs tests, imports data, produces full-period and recent-period reports, and uploads the report artifact.
6. Value screening: implemented but deliberately gated off. Current evidence shows the de-vigged historical market baseline outperforming both tested models on the same fixtures, so model-driven value alerts are not approved.
7. Experimental daily fixture-to-prediction flow: implemented with minimum-history suppression; a scheduled GitHub Actions workflow creates a report artifact at 06:00 Nigeria time when the API secret is configured. It is not a validated betting model. Optional Telegram delivery is wired into the workflow and a successful live send was verified on 2026-10-24; it requires the API and Telegram secrets. The next full post-migration delivery check remains pending.
8. Paper tracking: implemented with per-model cumulative metrics, pending-fixture retries, idempotent match-level deduplication, and Telegram summaries. Unit-tested, but the first real scheduled run using the new ledger and recent-results refresh still needs verification.
9. Remaining before a public MVP: verify repeated scheduled runs and API history-refresh coverage, build Telegram commands and a mobile-first dashboard, retrieve and audit live odds, and improve historical team-name/competition matching. Normal 10.00-odds slips and 50.00–100.00-odds value slips stay disabled until validation supports them.
