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

## Project roadmap
1. API connection and response validation (this scaffold)
2. Store fixtures and results in PostgreSQL
3. Build transparent baseline goal probabilities
4. Backtest using time-correct historical data
5. Compare probabilities with timestamped odds and filter for value
6. Telegram alerts and mobile-first dashboard
7. Paper-tracking, calibration, and performance reporting
