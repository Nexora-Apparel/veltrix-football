# StatsBomb match metadata and coverage qualification — 2026-11-11

## Added
- `veltrix_v2/ingestion/statsbomb_match_metadata.py`
- `tests/veltrix_v2/test_statsbomb_match_metadata.py`

## Contract
- Preserves competition, season, match, home/away team identities, match date, kickoff string, status, scores, match week and unknown metadata.
- Preserves `match_available` and `match_updated` source strings. Converts to UTC only if the source value carries an explicit timezone offset.
- Does not interpret match date/kickoff as UTC. Does not use the event match clock as wall-clock time.
- Coverage manifest hashes ordered event payload hashes and records event count. Event presence is explicitly `events_present_completeness_unverified`; it does not prove complete event capture.
- Availability cutoff classification uses only explicit timezone-aware `match_available`. Unzoned timestamps remain unverified; later availability is excluded from earlier cutoffs.

## Research gate
StatsBomb event features must remain quarantined from pre-match model training unless the source's actual availability timestamp is known to precede the prediction cutoff. Match/event coverage completeness, user-agreement, registration, attribution and upstream rights remain separate gates.

## Exclusions
No Neon writes, model fitting, calibration, production ingestion, deployment or Telegram publication.
