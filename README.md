# Veltrix Football

Football analytics and prediction platform. Initial milestone: secure API-Football connectivity and fixture validation.

## Current scope
- Verify API-Football credentials without exposing the key.
- Fetch fixtures for a chosen date.
- Inspect accessible competitions.
- Validate API responses and report remaining request quota when headers are available.
- No fabricated predictions, no automatic betting, and no promise of profit.

## Requirements
- Python 3.11+
- API-Football API key from your API-Sports dashboard

## Configure
Set the environment variable `API_FOOTBALL_KEY`. Never commit a real key.

Linux/macOS:
```bash
export API_FOOTBALL_KEY="your_key_here"
python -m app.cli status
python -m app.cli fixtures --date 2026-10-23
python -m app.cli leagues
python -m app.cli history --from 2025-01-01 --to 2025-01-31 --output data/historical_features.csv
```

Windows PowerShell:
```powershell
$env:API_FOOTBALL_KEY="your_key_here"
python -m app.cli status
```

## API notes
The client uses `https://v3.football.api-sports.io/` and the `x-apisports-key` header.
An HTTP 200 response is not by itself proof of success: the API's JSON `errors` field is checked too.
The available leagues, seasons, statistics, odds, and request quota depend on the API plan.

## Historical data export
Use `python -m app.cli history --from YYYY-MM-DD --to YYYY-MM-DD --output data/historical_features.csv` to retrieve fixtures and export completed matches. Each row includes rolling team form features computed strictly from earlier completed matches; a match result is added to team history only after that match’s pre-match features are calculated. This avoids direct target leakage. The default rolling window is five matches and can be changed with `--window 8`. Keep date ranges to 366 calendar days or less per request. API plan coverage, quota and historical availability still apply. CSV files are local outputs and are not committed automatically.

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

The backtest compares two league-aware research baselines (venue-specific Poisson and Elo) and separately evaluates the exact live experimental Poisson pipeline using its own 2020-onward history, 10-match team windows, minimum-history gate and global scoring priors. Predictions are generated before same-day results are ingested. Reports include multiclass Brier score, log loss, result accuracy, calibration diagnostics, a recent 20%-of-dates holdout and market comparison on the same fixtures with usable odds. GitHub Actions uploads a report artifact.

**Latest direct live-pipeline evaluation (historical snapshot through 2026-09-03):** 67,544 forecasts scored; accuracy 45.02%, Brier 0.6441, log loss 1.0680. On 67,486 forecasts with historical odds, the live model scored 44.99% accuracy / 0.6443 Brier / 1.0684 log loss, while the de-vigged market benchmark scored 50.21% / 0.6003 / 1.0037. On the recent holdout odds subset, live scored 44.97% / 0.6429 / 1.0665 versus market 50.57% / 0.5985 / 1.0010. Historical odds timestamps and closing-line quality are not verified, but the gap is large enough that the live model is **not validated for betting**. Keep betting slips and value alerts disabled; do not interpret this evaluation as evidence of profitability.

## Retrospective paper tracking

A saved daily report can be scored against the completed-fixture response for the same date without placing bets. The daily report now includes the primary experimental Poisson estimate and, where sufficient history is available, a separate Elo alternative. Elo uses a competition-specific history when the API league ID maps to a historical division code; otherwise it is labelled as a global fallback. The scheduled/manual daily workflow attempts to evaluate the previous day's report, matches forecasts by fixture ID, excludes withheld/invalid predictions and unfinished fixtures, and updates a cumulative ledger with result accuracy, multiclass Brier score, and log loss, separated by model version so results from different algorithms are not mixed. The Elo alternative is not yet validated; its paper performance will be measured separately. When a ledger is available, the Telegram report also shows cumulative paper metrics for each model version. The ledger is uploaded as a 90-day artifact; this is not a permanent database, and an evaluation is skipped if the previous report cannot be found or results cannot be fetched. This is a scoring tool, not a betting approval gate.

Example after saving the API-Football results JSON for that date:

```bash
python scripts/evaluate_paper_predictions.py --report reports/daily_predictions.json --results reports/completed_fixtures.json --output reports/paper_evaluation.json
```

## Daily fixture-to-prediction pipeline (experimental)

The daily workflow is scheduled for 08:00 Africa/Lagos (07:00 UTC) and can also be started manually. It includes only fixtures whose kickoff date is the same calendar date in Africa/Lagos as the report date and whose kickoff time is still in the future; tomorrow/later fixtures and already-started fixtures are excluded even when the API returns UTC timestamps. Add `API_FOOTBALL_KEY` under repository Settings → Secrets and variables → Actions → New repository secret for the job to run. To enable the optional Telegram delivery step, also add `TELEGRAM_BOT_TOKEN` (from BotFather) and `TELEGRAM_CHAT_ID` (the destination chat ID) as repository Actions secrets. Never put these values in source code or commit them. The workflow imports historical scores, runs the unit tests, fetches fixtures for the requested Nigeria-time date, sends the explicitly experimental report to Telegram when all three secrets are present, and uploads a JSON report artifact retained for 90 days so reports can be reviewed during a paper-tracking period. If Telegram secrets are absent, delivery is skipped without exposing credentials.

Run locally after importing historical data:

```bash
python scripts/import_open_dataset.py --from 2020-01-01 --to YYYY-MM-DD --output data/open_historical_matches.csv
python scripts/run_daily_predictions.py --date YYYY-MM-DD --history data/open_historical_matches.csv --output reports/daily_predictions.json
```

The live fixture model uses recent team goals with venue-aware scoring/defending rates, shrinkage toward home/away scoring baselines, common explicit team-name aliases, and an independent Poisson calculation. When an exact team history is missing, it may show close-name suggestions for diagnosis but never applies fuzzy matches automatically. It is **experimental and not validated for betting**: competition-specific adjustment, live odds retrieval, independent recent-season validation, Telegram bot commands, and the mobile dashboard are not implemented. It suppresses probabilities for teams with fewer than five matching historical records. It does not generate normal 10.00-odds slips or 50.00–100.00-odds value slips; both remain disabled until the model beats a suitable market benchmark and odds can be checked. The daily workflow includes an optional Telegram report-delivery step. A live delivery was verified on 2026-10-24; the generated report contained 8 experimental forecasts and withheld 284 fixtures for insufficient team history. The report now counts possible team-name mismatches, includes conservative suggestions when similar historical names exist, and separates future fixtures, past kickoffs excluded, and fixtures excluded by date/status. The model remains unvalidated and betting slips remain disabled.

## Model safety
Use only information available before kickoff as predictors. Full-time/half-time scores, shots and cards are post-match outcomes and must not be used as pre-match features. Never randomly split time-series match data; train on earlier matches and evaluate on later matches. Report Brier score/log loss, calibration, number of selections, ROI, yield, and drawdown alongside a market baseline. Historical odds coverage varies by league and season, and the open dataset does not cover every competition worldwide.

## Project status and remaining work
1. API connection and response validation: implemented; live smoke checks are subject to API-Football quota/rate limits.
2. Historical fixture export and leakage-safe rolling features: implemented and covered by automated tests.
3. Open historical data import: implemented; CI successfully imported the available historical dataset.
4. Baseline modelling: Poisson attack/defence and Elo are implemented and evaluated chronologically.
5. Backtesting and calibration diagnostics: implemented; CI runs tests, imports data, produces full-period and recent-period reports, and uploads the report artifact.
6. Value screening: implemented but deliberately gated off. Current evidence shows the de-vigged historical market baseline outperforming both tested models on the same fixtures, so model-driven value alerts are not approved.
7. Experimental daily fixture-to-prediction flow: implemented with minimum-history suppression; a scheduled GitHub Actions workflow creates a report artifact at 08:00 Nigeria time when the API secret is configured. It is not a validated betting model. Optional Telegram delivery is wired into the workflow and a successful live send was verified on 2026-10-24; it requires the API and Telegram secrets.
8. Remaining before a public MVP: verify repeated scheduled runs, build Telegram commands and the mobile-first dashboard, retrieve and audit live odds, improve historical team-name/competition matching, and paper-track predictions with recent league-level evaluation. Normal 10.00-odds slips and 50.00–100.00-odds value slips stay disabled until validation supports them.
