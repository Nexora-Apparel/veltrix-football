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

## Open historical dataset import (2024–present)
Veltrix can import completed match records from the public [Club-Football-Match-Data dataset](https://github.com/xgabora/Club-Football-Match-Data), whose repository identifies an MIT license. The raw dataset is **not** committed to this repository. Run:

```bash
python -m scripts.import_open_dataset --from 2024-01-01 --to 2026-10-23 --output data/open_historical_matches.csv
```

The importer discovers the source CSV path from the repository tree, validates required fields, normalizes scores, team names, date, available Elo/form/odds/statistics, skips malformed rows, and deduplicates by competition/date/home/away. Optional odds and statistics remain empty when missing. The GitHub Actions workflow can run manually or weekly and uploads the generated CSV as an artifact for 30 days; this artifact is not a permanent database.

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

The backtest compares two separate baselines: a venue-specific Poisson attack/defence estimate with shrinkage toward league averages, and an Elo-based 1X2 estimate. It predicts all matches on a date before ingesting results from that date, then reports multiclass Brier score, log loss, result accuracy and one-vs-rest reliability diagnostics. It also reports a recent-period evaluation using the latest 20% of unique forecast dates, plus a market comparison on the same fixtures with usable odds. GitHub Actions runs tests, imports the dataset and uploads a compact report artifact. The report is an evaluation snapshot, not evidence of profitability; compare against market probabilities and audit odds timestamps before enabling value alerts.

## Model safety
Use only information available before kickoff as predictors. Full-time/half-time scores, shots and cards are post-match outcomes and must not be used as pre-match features. Never randomly split time-series match data; train on earlier matches and evaluate on later matches. Report Brier score/log loss, calibration, number of selections, ROI, yield, and drawdown alongside a market baseline. Historical odds coverage varies by league and season, and the open dataset does not cover every competition worldwide.

## Project status and remaining work
1. API connection and response validation: implemented; live smoke checks are subject to API-Football quota/rate limits.
2. Historical fixture export and leakage-safe rolling features: implemented and covered by automated tests.
3. Open historical data import: implemented; CI successfully imported the available historical dataset.
4. Baseline modelling: Poisson attack/defence and Elo are implemented and evaluated chronologically.
5. Backtesting and calibration diagnostics: implemented; CI runs tests, imports data, produces full-period and recent-period reports, and uploads the report artifact.
6. Value screening: implemented but deliberately gated off. Current evidence shows the de-vigged historical market baseline outperforming both tested models on the same fixtures, so model-driven value alerts are not approved.
7. Remaining before a public MVP: build the mobile-first web dashboard and live fixture-to-prediction flow, audit per-league/recent-season performance and odds timestamps, and paper-track predictions before considering any value-alert gate.
