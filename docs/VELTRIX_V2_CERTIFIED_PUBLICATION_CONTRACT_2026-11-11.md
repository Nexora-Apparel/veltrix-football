# VELTRIX 2.0 certified publication contract

Date: 2026-11-11

## Purpose

`veltrix_v2/publishing/certified_report.py` defines the shared daily-report boundary for the existing website API and Telegram infrastructure. It is a schema/renderer only; it does not connect to either transport, write to Neon, deploy, or activate a schedule.

## Publication gate

A forecast report can be constructed only from a `PredictionReleaseCertification` whose overall `passed` flag is true. That gate requires, independently for 1X2, BTTS and totals: at least 1,000 chronological walk-forward matches, explicit source approval, point-in-time validation, passing leakage tests and passing calibration checks. It does not require prospective betting volume, positive ROI, odds coverage or bookmaker superiority; those are value-bet certification requirements. The prediction certification ID is carried into the report payload for audit traceability.

Value betting is a separate gate. The builder accepts an optional `ReleaseCertification`; value bets are enabled only when that full certification exists and passes. If it is absent or fails, every fixture's value-bet verdict is forcibly set to `LOCKED — NOT CERTIFIED`, even if a caller supplied a value verdict. The report exposes `value_bets_enabled` to both website and Telegram consumers.

The report contains at most 25 fixtures, unique fixture IDs, chronological kickoff ordering and only fixtures whose kickoff is strictly after report generation. An empty report is valid; no fixture quota can force publication of unsupported matches.

## Time contract

The report date is a Nigeria local calendar date (`Africa/Lagos`). The delivery deadline is exactly 06:00 WAT, represented as an offset-aware UTC timestamp. Fixture kickoffs are normalized to UTC and separately rendered in WAT. Generation must complete before the deadline. Actual delivery timing remains a transport/scheduler acceptance test, not something this schema can prove.

## Website payload

The JSON-ready payload includes schema version, report date, generation time, delivery deadline, prediction certification ID, value-bet enabled flag, source-attribution lines, fixture count, fixture identity/competition/teams, UTC and WAT kickoff, verdict, AI insight, value-bet verdict and market probabilities. Each fixture carries explicit source-provider IDs. The report builder rejects any provider ID without an attribution rule and rejects missing required credits. 5Dollar Free data requires the linked credit “Football data by 5DollarFootballAPI”; OpenLigaDB data requires ODbL attribution. Attribution lines are preserved in the website payload and appended to Telegram output. The existing website should consume this payload only after the prediction publication gate passes; its existing dashboard/status/market routing remains the presentation layer.

## Telegram rendering

The renderer uses the required header `🔔 🆕 NEW VELTRIX UPDATE`, followed by the WAT date, qualified fixture count, verdict, 1X2, BTTS, O/U, AI insight and value-bet verdict. It deliberately omits internal system status and experimental wording. The existing Telegram sender remains responsible for message chunking, retry/idempotency, destination verification and delivery receipts.

## Release boundary

The prediction publication gate and the value-bet certification gate are independent. A controlled predictions-only release is allowed after the prediction gate and data-quality requirements pass; value betting must remain locked until the full prospective certification contract passes. Do not wire this renderer into the live schedule, website route or Telegram sender until source qualification, historical evaluation, the appropriate release gate and transport integration tests pass.


## Record-derived certification API

The public `certify_prediction_publication` entry point now accepts only the
multi-competition walk-forward report, immutable source-observation records
and source-approval records. It derives each market's sample size from the
aggregate evaluator report, rechecks training and held-out result provenance,
validates every fold cutoff/window and fixture identity, and recomputes
calibration diagnostics from the report's actual held-out forecasts/outcomes.
Caller-supplied counts and approval, point-in-time, leakage or calibration
booleans are not accepted by this public API.

Source audit requires collection, storage and model-training rights for
training observations; held-out result observations require collection,
storage and benchmarking rights and must become available after kickoff.
The calibration thresholds are ECE <= 0.05, maximum reliability-bin gap <=
0.15 and at least 1,000 held-out forecasts per market (all three 1X2 classes
are checked independently).


Certification result objects are sealed against direct construction. Only the
record-derived certification factories can create a `PredictionReleaseCertification`
or `ReleaseCertification` accepted by the report boundary. Internal test
factories remain private to the evaluation module; synthetic flags are not a
production certification route.
