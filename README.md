# Veltrix Football

Football analytics and prediction platform. The active fixture provider is Highlightly, with normalized fixture data and an experimental, explicitly unvalidated prediction model.

## Current scope
- Verify Highlightly credentials without exposing the key.
- Fetch fixtures for a chosen date.
- Inspect accessible competitions.
- Validate API responses and report remaining request quota when headers are available.
- No fabricated predictions, no automatic betting, and no promise of profit.

## Requirements
- Python 3.11+
- Highlightly Football API key from your Highlightly dashboard

## Configure
Set the environment variable `HIGHLIGHTLY_API_KEY`. Never commit a real key.

Linux/macOS:
```bash
export HIGHLIGHTLY_API_KEY="your_key_here"
python -m app.cli status
python -m app.cli fixtures --date 2026-10-23
python -m app.cli leagues
python -m app.cli history --from 2025-01-01 --to 2025-01-31 --output data/historical_features.csv
```

Windows PowerShell:
```powershell
$env:HIGHLIGHTLY_API_KEY="your_key_here"
python -m app.cli status
```

## API notes
The client calls `https://soccer.highlightly.net` and sends the key in the `x-rapidapi-key` header. It normalizes Highlightly's `data` envelope into the internal `response` shape. Request quota is reported from the provider's rate-limit headers when available. The free/basic plan does not provide bookmaker odds; the adapter returns an explicit unavailable status instead of fabricating them.

## Historical data export
Use `python -m app.cli history --from YYYY-MM-DD --to YYYY-MM-DD --output data/historical_features.csv` to retrieve fixtures and export completed matches. Each date is requested separately because Highlightly's matches endpoint uses a single `date` filter; long ranges therefore consume one API request per date and may exceed the free-tier quota. Keep ranges short. Each row includes rolling team form features computed strictly from earlier completed matches. CSV files are local outputs and are not committed automatically.

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

The backtest compares two league-aware research baselines (venue-specific Poisson and Elo), the live recent-goals Poisson pipeline, and the competition-scoped Elo model. Daily reports promote competition Elo to the primary forecast only when the fixture maps to a supported historical division and has enough team history; otherwise Poisson remains primary. It uses walk-forward predictions made before same-day results are ingested, and reports multiclass Brier score, log loss, result accuracy, calibration diagnostics, a recent-date holdout, per-competition live-model metrics, and market comparisons on identical fixtures with usable odds. GitHub Actions uploads a report artifact.

**Latest live-model evaluation (historical snapshot through 2026-09-03):**
- **Recent-goals Poisson:** 67,544 forecasts; 45.02% accuracy, Brier 0.6441, log loss 1.0680. On 67,486 fixtures with odds, the model scored 44.99% / 0.6443 / 1.0684 versus the de-vigged market at 50.21% / 0.6003 / 1.0037.
- **Competition Elo alternative:** 66,620 forecasts; 48.22% accuracy, Brier 0.6191, log loss 1.0311. On 66,564 fixtures with odds, Elo scored 48.20% / 0.6192 / 1.0313 versus the market at 50.21% / 0.6002 / 1.0036.
- **Recent Elo holdout:** 11,445 fixtures with odds; Elo scored 48.98% accuracy, Brier 0.6137, log loss 1.0232 versus the market at 50.69% / 0.5980 / 1.0004.

Elo is materially better than the current Poisson model on these historical metrics, but still underperforms the market benchmark. In the full-period same-fixture comparison, neither live model beats the de-vigged market on both Brier score and log loss in any of the 38 evaluated divisions. Historical odds timestamps and closing-line quality have not been verified, so neither model is validated for betting. Keep betting slips and value alerts disabled; these metrics are not evidence of profitability.

## Retrospective paper tracking

A saved daily report can be scored against the completed-fixture response for the same date without placing bets. The daily report uses competition-scoped Elo as the primary 1X2 estimate when the fixture maps to a supported historical division and both teams have enough prior competition matches. In that case, the recent-goals Poisson probabilities are shown as an alternative and its expected-goal/total estimates remain auxiliary. When the Elo history is unavailable, Poisson remains primary and a global-fallback Elo estimate is shown only if it meets the minimum-history gate. The report labels which model is primary and the Elo history scope. The scheduled/manual daily workflow attempts to evaluate the previous day's report, matches forecasts by fixture ID, excludes withheld/invalid predictions and unfinished fixtures, and updates a cumulative ledger with result accuracy, multiclass Brier score, and log loss, separated by model version so results from different algorithms are not mixed. Both model versions are tracked separately in the cumulative paper ledger, regardless of which is primary for a particular fixture. When a ledger is available, the Telegram report also shows cumulative paper metrics for each model version. The ledger is uploaded as a 90-day artifact; this is not a permanent database, and an evaluation is skipped if the previous report cannot be found or results cannot be fetched. This is a scoring tool, not a betting approval gate.

Example after saving the Highlightly results JSON for that date:

```bash
python scripts/evaluate_paper_predictions.py --report reports/daily_predictions.json --results reports/completed_fixtures.json --output reports/paper_evaluation.json
```

## Daily fixture-to-prediction pipeline (experimental)

The daily workflow is scheduled for 06:00 Africa/Lagos (05:00 UTC) and can also be started manually. It includes only fixtures whose kickoff date is the same calendar date in Africa/Lagos as the report date and whose kickoff time is still in the future; tomorrow/later fixtures and already-started fixtures are excluded even when the API returns UTC timestamps. Add `HIGHLIGHTLY_API_KEY` under repository Settings → Secrets and variables → Actions → New repository secret for the job to run. To enable the optional Telegram delivery step, also add `TELEGRAM_BOT_TOKEN` (from BotFather) and `TELEGRAM_CHAT_ID` (the destination chat ID) as repository Actions secrets. Never put these values in source code or commit them. The workflow imports historical scores, runs the unit tests, fetches fixtures for the requested Nigeria-time date, sends the explicitly experimental report to Telegram when all three secrets are present, and uploads a JSON report artifact retained for 90 days so reports can be reviewed during a paper-tracking period. If Telegram secrets are absent, delivery is skipped without exposing credentials.

Run locally after importing historical data:

```bash
python scripts/import_open_dataset.py --from 2020-01-01 --to YYYY-MM-DD --output data/open_historical_matches.csv
python scripts/run_daily_predictions.py --date YYYY-MM-DD --history data/open_historical_matches.csv --output reports/daily_predictions.json
```

The daily job refreshes completed results after the open CSV's latest date through yesterday using Highlightly's single-date matches endpoint. This uses one request per date in the range, so keep the historical CSV reasonably fresh and monitor the free-plan daily quota. Current-day results are excluded to prevent leakage. Bookmaker odds are marked unavailable on the free/basic plan; the system does not fabricate odds or claim value bets without verified market data.

For 1X2 probabilities, competition-scoped Elo is selected as primary only when the fixture maps to a supported historical division and the competition/team history gates pass. Otherwise, the recent-goals Poisson model remains primary; a global-fallback Elo estimate is only shown as a labelled alternative when its history gate passes. Expected goals, BTTS, over/under 2.5 and likely scorelines remain Poisson-derived, including when Elo is primary. When exact team history is missing, the report may show close-name suggestions for diagnosis but never applies fuzzy matches automatically.

The system is **experimental and not validated for betting**. Historical walk-forward tests show Elo is stronger than the current Poisson model, but both still underperform the market benchmark. Live odds retrieval, Telegram bot commands and the mobile dashboard are not implemented. The bot does not generate normal 10.00-odds slips or 50.00–100.00-odds value slips; both remain disabled until the model beats a suitable market benchmark and odds can be checked. Telegram delivery was verified on 2026-10-24; the report contained 8 experimental forecasts and withheld 284 fixtures for insufficient team history. Reports now include model mix, history freshness, result refresh coverage, and separate fixture counts for future kickoffs, past kickoffs and excluded dates/statuses. Unmapped competitions with insufficient exact team history are summarized separately as unsupported, rather than being mixed into the missing-history count. Long reports are split across multiple Telegram messages instead of dropping later fixtures.

## Model safety
Use only information available before kickoff as predictors. Full-time/half-time scores, shots and cards are post-match outcomes and must not be used as pre-match features. Never randomly split time-series match data; train on earlier matches and evaluate on later matches. Report Brier score/log loss, calibration, number of selections, ROI, yield, and drawdown alongside a market baseline. Historical odds coverage varies by league and season, and the open dataset does not cover every competition worldwide.

## Project status and remaining work
1. API connection and response validation: implemented; live smoke checks are subject to Highlightly quota/rate limits.
2. Historical fixture export and leakage-safe rolling features: implemented and covered by automated tests.
3. Open historical data import: implemented; CI successfully imported the available historical dataset.
4. Baseline modelling: Poisson attack/defence and Elo are implemented and evaluated chronologically.
5. Backtesting and calibration diagnostics: implemented; CI runs tests, imports data, produces full-period and recent-period reports, and uploads the report artifact.
6. Value screening: implemented but deliberately gated off. Current evidence shows the de-vigged historical market baseline outperforming both tested models on the same fixtures, so model-driven value alerts are not approved.
7. Experimental daily fixture-to-prediction flow: implemented with minimum-history suppression; a scheduled GitHub Actions workflow creates a report artifact at 08:00 Nigeria time when the API secret is configured. It is not a validated betting model. Optional Telegram delivery is wired into the workflow and a successful live send was verified on 2026-10-24; it requires the API and Telegram secrets.
8. Paper tracking: implemented with per-model cumulative metrics, pending-fixture retries, idempotent match-level deduplication, and Telegram summaries. Unit-tested, but the first real scheduled run using the new ledger and recent-results refresh still needs verification.
9. Remaining before a public MVP: verify repeated scheduled runs and API history-refresh coverage, build Telegram commands and a mobile-first dashboard, retrieve and audit live odds, and improve historical team-name/competition matching. Normal 10.00-odds slips and 50.00–100.00-odds value slips stay disabled until validation supports them.
