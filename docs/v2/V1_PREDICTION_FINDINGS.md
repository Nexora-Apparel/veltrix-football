# VELTRIX FOOTBALL V1 — Prediction Pipeline Findings

Read-only source inspection: 2026-11-06. Findings apply to the inspected `main` branch and are used to define the V2 replacement boundary.

## Confirmed fallback path

File: `app/live_predictions.py`
Function: `predict_fixtures(...)`

The function has an explicit early branch when the usable historical-match collection is empty:

- It assigns both teams `NEUTRAL_GOALS_PER_TEAM` (1.225).
- It calls `match_probabilities(home_xg, away_xg)`.
- It appends a forecast record with model `adaptive_poisson_neutral_prior`.
- It marks the record `LOW_HISTORY_FORECAST` and `model_validated=False`.
- It still includes public probability fields for 1X2, BTTS and totals.
- It describes the evidence scope as `GLOBAL_NEUTRAL_PRIOR` or `CATEGORY_NEUTRAL_PRIOR`.

This is a direct code-level explanation for why fixtures with no usable history can still receive nearly identical market probabilities from this legacy path. It is not merely a Telegram formatting issue.

The same function also contains a separate non-senior competition path that uses neutral goal rates. This is another reason V2 must have a single publication eligibility gate that blocks forecast fields for unsupported or unverified evidence states.

## Important nuance

The code also has a later team-history and competition-baseline path. It can shrink team estimates toward competition scoring baselines when history is sparse. Shrinkage can be a legitimate modelling technique only when its evidence conditions, model version and validation are explicit. V2's initial release contract deliberately withholds forecasts when minimum verified team evidence is not met; it does not silently turn a prior into a fixture-specific public forecast.

## Confirmed model responsibilities

- `app/prediction.py` converts supplied expected-goal inputs into Poisson 1X2, BTTS, totals and scoreline probabilities. It does not fetch data or estimate team strength.
- `app/advanced_models.py` contains experimental Dixon-Coles and recency-weighted calculations; the module itself says these alternatives should not be promoted without chronological backtesting.
- `app/live_predictions.py` combines fixture parsing, historical lookup preparation, Elo and Poisson paths, evidence metadata and fallback behaviour. This is too much responsibility in one function/module and makes divergent report paths easier to create.

## V2 replacement requirements derived from this inspection

1. A model may calculate research diagnostics from a prior, but a prior-only output cannot populate public forecast fields.
2. The shared eligibility service must run before market outputs can enter a public report.
3. No-history, query-failed and identity-mismatch states must remain distinct.
4. Market report generation must not call legacy `predict_fixtures` or `apply_global_prior`.
5. V2 tests must assert that prior-only candidates are rejected even when their probability vectors sum to one.
6. The website and Telegram must not calculate forecasts independently; both render one immutable report.
7. V1 remains available for historical audit, but V1 forecasts retain their original version/status and cannot be relabelled as V2.

## Not yet established

This inspection does not prove which deployed report generator produced the 2026-11-05 Telegram 1X2 message. The next tracing task is to follow each command/report entry point to its imported prediction function and report artifact. The code finding explains a known failure mechanism but is not, by itself, proof of the exact runtime call path for that message.
