# OpenPlay match coverage and known-issue adapter — 2026-11-11

## Added
- `veltrix_v2/ingestion/openplay_match_coverage.py`
- `tests/veltrix_v2/test_openplay_match_coverage.py`

## Contract
- Joins each match to its exact competition-season coverage record.
- Preserves match ID, competition, season, source date, home/away team IDs, score, source scrape timestamp, and native `xg_model` identifier.
- Joins match-level known gaps and data issue codes. Known gaps and issues quarantine the match; missing/out-of-scope coverage is also quarantined.
- Duplicate competition-season coverage rows fail closed.
- Source date and scrape timestamp remain strings; no timezone or point-in-time availability is invented.
- The match-level xG model identity is intended to be passed unchanged to OpenPlay player/shot feature adapters. It must not be conflated with StatsBomb xG.

## Limits
- Historical release only; no live/current-season feed.
- This is a source-quality and provenance contract, not an assertion that all event/player tables are complete.
- Rights/upstream provenance remains under review. No production ingestion, Neon writes, training, calibration, deployment or Telegram publication.
