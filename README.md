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

## Project roadmap
1. API connection and response validation (verified)
2. Historical fixture export and leakage-safe rolling features (implemented; CI verification pending)
3. Store fixtures and results in PostgreSQL
4. Estimate team strengths and expected goals from historical data
5. Backtest chronologically with no future-data leakage
6. Compare probabilities with timestamped odds and filter for value
7. Telegram alerts, mobile-first dashboard, paper tracking and calibration


## Open historical dataset import (2024–present)
Veltrix can import completed match records from the public [Club-Football-Match-Data dataset](https://github.com/xgabora/Club-Football-Match-Data), whose repository identifies an MIT license. The raw dataset is **not** committed to this repository. Run:

```bash
python -m scripts.import_open_dataset --from 2024-01-01 --to 2026-10-23 --output data/open_historical_matches.csv
```

The importer discovers the source CSV path from the repository tree, validates required fields, normalizes scores, team names, date, available Elo/form/odds/statistics, skips malformed rows, and deduplicates by competition/date/home/away. Optional odds and statistics remain empty when missing. The GitHub Actions workflow can run manually or weekly and uploads the generated CSV as an artifact for 30 days; this artifact is not a permanent database.

**Model safety:** use only pre-match fields (for example Elo and form) as predictors. Full-time/half-time scores, shots and cards are outcome fields and must not be used as pre-match features. Validate time ordering and source coverage before backtesting; historical odds availability varies by league/season. This dataset does not cover every competition worldwide.
