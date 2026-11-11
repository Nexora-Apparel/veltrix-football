# VELTRIX 2.0 certified publication contract

Date: 2026-11-11

## Purpose

`veltrix_v2/publishing/certified_report.py` defines the shared daily-report boundary for the existing website API and Telegram infrastructure. It is a schema/renderer only; it does not connect to either transport, write to Neon, deploy, or activate a schedule.

## Publication gate

A report can be constructed only from a `ReleaseCertification` whose overall `passed` flag is true. The certification ID is carried into the report payload for audit traceability. The report contains at most 25 fixtures, unique fixture IDs, chronological kickoff ordering and only fixtures whose kickoff is strictly after report generation. An empty report is valid; no fixture quota can force publication of unsupported matches.

## Time contract

The report date is a Nigeria local calendar date (`Africa/Lagos`). The delivery deadline is exactly 06:00 WAT, represented as an offset-aware UTC timestamp. Fixture kickoffs are normalized to UTC and separately rendered in WAT. Generation must complete before the deadline. Actual delivery timing remains a transport/scheduler acceptance test, not something this schema can prove.

## Website payload

The JSON-ready payload includes schema version, report date, generation time, delivery deadline, certification ID, fixture count, fixture identity/competition/teams, UTC and WAT kickoff, verdict, AI insight, value-bet verdict and market probabilities. The existing website should consume this payload only after certification; its existing dashboard/status/market routing remains the presentation layer.

## Telegram rendering

The renderer uses the required header `🔔 🆕 NEW VELTRIX UPDATE`, followed by the WAT date, qualified fixture count, verdict, 1X2, BTTS, O/U, AI insight and value-bet verdict. It deliberately omits internal system status and experimental wording. The existing Telegram sender remains responsible for message chunking, retry/idempotency, destination verification and delivery receipts.

## Release boundary

The current project is not certified, so no production report can currently be built. Do not wire this renderer into the live schedule, website route or Telegram sender until source qualification, historical evaluation, prospective certification and transport integration tests all pass.
