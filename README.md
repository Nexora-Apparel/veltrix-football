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
