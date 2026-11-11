# StatsBomb match-intelligence aggregation qualification — 2026-11-11

## Scope
Added `veltrix_v2/ingestion/statsbomb_match_intelligence.py` as a deterministic, source-specific aggregation layer over the lossless StatsBomb event adapter.

## Metrics
- Shot counts, on-target counts and goal outcomes from explicit StatsBomb shot outcomes.
- Sum of StatsBomb's native `shot.statsbomb_xg`, retained under model identity `statsbomb-open-data:shot.statsbomb_xg`; missing xG remains null.
- Possession count and possession-team attribution from possession IDs and possession-team IDs.
- Play-pattern counts.
- Under-pressure and counterpress event counts.
- Counts for explicitly named defensive event types: Ball Recovery, Block, Clearance, Interception and Tackle.

## Guardrails
- No PPDA, pressing-intensity, possession percentage, progressive-pass/carry, tactical classification, or lineup inference.
- Pressure-event counts are not PPDA.
- StatsBomb xG is not mixed with OpenPlay xG or another provider's xG.
- Event match clock is not UTC or a point-in-time availability timestamp.
- Caller must establish match/event coverage completeness from match metadata before using aggregates.
- No model training, calibration, database writes, provider ingestion, deployment or Telegram publication.
- The adapter and aggregator remain research-only until user-agreement, registration, attribution and source-rights review passes.

## Validation
Tests cover core counts, native xG identity, missing-xG semantics, mixed-match rejection, duplicate-event rejection, possession-owner conflicts and invalid xG values. CI result is pending for the current PR revision.
