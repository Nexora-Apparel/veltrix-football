# Legacy prediction quarantine

## Purpose

VELTRIX FOOTBALL 2.0 is a clean rebuild. Legacy prediction probabilities, model heads, fallback priors, calibration, feature engineering and prediction decision rules are not part of the new model portfolio.

## Runtime boundaries

- `scripts/run_daily_predictions.py` exits immediately with `LEGACY_PREDICTION_PIPELINE_DISABLED`; it cannot fetch fixtures, build a report, publish artifacts or send Telegram messages.
- `app/live_predictions.py`, `app/prediction.py`, `app/advanced_models.py`, `app/poisson_dc_head.py` and `app/team_form.py` now expose only disabled compatibility stubs; their former model implementations are removed.
- `app/backtest_engine.py` and `scripts/run_backtest.py` are disabled. The independent multi-origin walk-forward evaluator is the only active model-evaluation path.
- Shared team-name and league-division utilities were moved to `app/fixture_history_utils.py`, so provider result ingestion and report filtering no longer import the legacy prediction module.
- The existing `daily-fixture-predictions.yml` job remains paused with `if: false`. The schedule is not restarted by this change.
- `app/independent_prediction_service.py` uses only the independent market models and independent Poisson/Dixon-Coles implementation. It does not import the legacy predictor.
- The dashboard API suppresses reports unless they satisfy `VELTRIX_INDEPENDENT_PREDICTION_REPORT_V1`, identify the independent portfolio, explicitly deny legacy dependencies, and carry a release certificate marked certified, publication-authorized and signature-verified with a valid digest.
- Telegram prediction commands use the same report contract. Legacy or uncertified reports return no fixtures or forecasts.
- Legacy paper ledgers, model-validation summaries, value screens and value certificates are not surfaced by the dashboard while no authorized independent report exists. Their source artifacts remain archived; they are not deleted.

## Publication contract

A report is publishable only when all of the following hold:

1. `report_schema == VELTRIX_INDEPENDENT_PREDICTION_REPORT_V1`.
2. `model_portfolio_id == veltrix-independent-market-portfolio-v1`.
3. `legacy_model_dependency == false`.
4. `publication_allowed == true`.
5. `release_certificate.status == CERTIFIED`.
6. `release_certificate.publication_authorized == true`.
7. `release_certificate.signature_verified == true`.
8. The certificate digest is a valid lowercase SHA-256 digest and binds the same model portfolio.

The independent certification runner currently returns publication authorization as false. In addition, the code-level switches `INDEPENDENT_REPORT_PUBLICATION_ENABLED` and `VALUE_BETTING_AUTHORIZATION_ENABLED` are both hard-coded false. Therefore no report or value certificate can currently pass, even if an artifact claims authorization. This is intentional until real-data qualification, formal certification and explicit release approval are complete.

## Non-goals

This quarantine does not delete historical match results, source payloads, provider credentials, the website, APIs, Telegram infrastructure or archived reports. It does not authorize model training, report publication, value betting, Telegram delivery or scheduling.
