# VELTRIX 2.0 — point-in-time player-form feature contract — 2026-11-11

## Added
- `veltrix_v2/features/player_form.py`
- `tests/veltrix_v2/test_player_form.py`

## Feature contract
- Uses a bounded last-N player-match window (1–20; default 5).
- Requires timezone-aware UTC kickoff and actual source-availability timestamps for every observation.
- Excludes matches at/after the prediction cutoff and observations not yet available at the cutoff.
- Excludes rows explicitly quarantined by the source quality layer.
- Computes minutes average, start rate, goals/90, shots/90, xG/90, npxG/90 and xA/90.
- xG/npxG/xA model identity is retained; mixed xG model IDs in one feature window fail closed.
- Duplicate match evidence, naive timestamps, invalid metrics and missing model IDs fail closed.
- Insufficient evidence is explicitly marked `low_sample`; zero minutes yields null per-90 rates, not infinity or fabricated values.

## Critical source constraint
OpenPlay's current adapter preserves raw unzoned match dates and scrape strings. Those strings do not automatically populate this point-in-time feature contract. OpenPlay rows remain ineligible for pre-match feature use until a defensible, timezone-aware availability timestamp is independently established. This module is a safe feature contract, not approval to train on the historical snapshot.

## Release state
No model fitting, calibration, Neon writes, production ingestion, deployment or Telegram publication.
