# VELTRIX FOOTBALL 2.0 — 5Dollar free-first forecast pipeline v1

## Purpose

Connect the existing free 5DollarFootballAPI parser and rights contract to the new model and batch engine without creating another provider client.

## Pipeline

1. Read-only provider response is parsed by the existing strict 5Dollar page parser.
2. The approved source scope is checked against exact provider competition IDs.
3. Collection/storage/model-training uses are evaluated at the forecast cutoff.
4. Finished results become provider-scoped MatchObservation rows only after the conservative four-day availability boundary and actual retrieval timestamp.
5. Scheduled fixtures become provider-scoped PredictionTarget rows only when their snapshot was retrieved by cutoff and kickoff remains in the future.
6. The deterministic batch engine generates up to 25 forecasts in kickoff order.

## Point-in-time handling

The existing 5Dollar parser uses provider_finished_status_conservative_4d and marks rows point_in_time_certifiable=false. The live/future prediction path can use such a result only after both its conservative availability time and retrieval time. The historical walk-forward evaluator excludes it from training.

## Rights handling

The pipeline consumes the existing approved 5Dollar source approval. It does not ask the user for new manual evidence. Provider/source identity, exact competition scope, approval ID, commercial use, and permitted purposes are checked before a fixture enters the model.

## Safety

- No network calls in this orchestration function.
- No database writes or migrations.
- No raw provider response redistribution.
- No scheduler, website publisher or Telegram sender.
- No value-bet or odds functionality.
- Every generated model forecast remains unpublished until independent certification.


## Optional recency weighting

The engine accepts an exponential half-life setting. Equal weighting remains the default; any non-default half-life must be selected through chronological walk-forward comparison using the same weighting for the model and competition baseline.


## One-shot provider dry run

The manual/push-only dry-run workflow requests at most 24 provider calls, paces requests at one every six seconds, reads at most 90 days of finished results and 14 days of scheduled fixtures, and filters any extra provider rows outside those windows locally. It uploads only a derived forecast report with provider attribution; raw provider responses are never written to the repository or artifact. No scheduled trigger is configured.


## Dixon-Coles candidate

An optional Dixon-Coles low-score correction parameter is exposed with rho=0.0 as the independent-Poisson default. Non-zero rho values are challengers only; invalid/non-positive low-score correction factors are rejected. A non-zero value may be selected only through chronological walk-forward evaluation against the independent baseline. The model remains unpublished.
