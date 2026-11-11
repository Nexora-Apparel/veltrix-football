# VELTRIX 2.0 — independent Dixon-Coles scoreline head — 2026-11-11

## Added
- `veltrix_v2/models/dixon_coles.py`
- `tests/veltrix_v2/test_dixon_coles.py`

## Scope
- Independent bivariate Poisson scoreline grid with Dixon-Coles low-score tau adjustment.
- Inputs are expected home goals, expected away goals and rho. Parameters are not fitted here.
- Derives all market probabilities from the same joint scoreline distribution through the existing V2 scoreline contract.
- Uses an explicit maximum-goal support expansion and records retained/tail mass.
- Conditional normalization is performed only after tail mass falls below the configured tolerance; the normalization method and omitted tail are exposed on the forecast object.
- Fails closed if the tail cannot meet tolerance, if low-score tau mass is non-positive, or if parameters are invalid.
- Integer O/U lines remain withheld by the scoreline market contract until push settlement is implemented.

## Release boundary
This is an unfitted research model component. It does not use legacy priors/models, fit parameters, calibrate, backtest, produce a forecast for a real fixture, write to Neon, deploy or publish to Telegram. Expected-goal inputs and rho must be estimated only from accepted training windows after the data gate passes.
