# VELTRIX FOOTBALL 2.0 — StatsBomb Open Data adapter qualification
Date: 2026-11-11
Branch: `veltrix-2.0-architecture-blueprint`

## Source facts verified

The official `hudl/open-data` repository states that the public subset is intended for football research and genuine interest in analytics. It describes the data layout as:
- `competitions.json` for competition and season metadata;
- match files grouped by competition ID and season ID;
- per-match `events` and `lineups` JSON files;
- selected-match `three-sixty` files.

If analysis or insights are published, shared or distributed, the repository asks users to identify StatsBomb as the source and use its logo from the StatsBomb media pack.

The repository links a custom StatsBomb user agreement. This is not a generic open-source licence for the data. The owner must follow the current user agreement and any registration requirements; the code and the data must not be conflated. VELTRIX's use is personal and non-commercial. Raw data redistribution is not part of this project.

## Schema observations

The official StatsBomb Open Data Specification v1.1 describes:
- event UUID `id`, per-match `index`, `period`, match-clock `timestamp`, `minute`, `second`;
- event `type`, `possession`, `possession_team`, `play_pattern`, `team`, `player`, and optional `location`;
- event-specific nested attributes, including shot, pass, pressure, duel, interception and carry details;
- lineup team IDs and player IDs/names/jersey numbers;
- match-level `match_available` / `match_updated` metadata in the documented match schema.

The event timestamp is elapsed match time, not a UTC wall-clock time. It must never be used as an observation availability timestamp. Match-level `match_available` is the relevant published availability evidence when present; preserve its original timezone/precision and fail closed if it is absent or ambiguous.

The specification is v1.1 (2019). The adapter therefore preserves unknown fields instead of assuming that this document exhaustively describes every newer payload.

## Adapter added

- `veltrix_v2/ingestion/statsbomb_events.py`
- `tests/veltrix_v2/test_statsbomb_events_adapter.py`

Adapter guarantees:
- UUID event identity and exact match ID;
- positive event index and supported period validation;
- millisecond match-clock parsing, with no UTC interpretation;
- event type, possession, possession-team, play-pattern, team and player IDs/names;
- coordinate validation against StatsBomb's 120 x 80 pitch coordinate frame;
- under-pressure and counterpress boolean validation;
- all unrecognized/event-specific attributes retained as recursively immutable data;
- deterministic SHA-256 payload hash;
- duplicate event IDs/indexes and out-of-order event arrays rejected.

The adapter intentionally does not:
- calculate PPDA, xG, shot quality, possession percentages, pressing intensity or tactical labels;
- reinterpret StatsBomb xG as OpenPlay xG or any other provider's xG;
- infer player availability before kickoff from an event timestamp;
- mark data rights-approved, write to Neon, train a model or publish predictions.

## Important analytical cautions

1. StatsBomb event definitions and collection fidelity are provider-specific. A pressure event is not interchangeable with another provider's pressure count.
2. Shot location/freeze-frame fidelity can differ by match/data version. Preserve match metadata and avoid assuming uniform spatial precision.
3. The official specification defines counterpress as a subset of pressing actions within five seconds of an open-play turnover; do not substitute a generic pressure count.
4. Event sequences alone do not prove the source was available before the historical forecast cutoff. Match availability metadata must be used in the point-in-time source gate.
5. Open Data competition coverage is selective and historical. It is not a complete current-season EPL lineup or event feed.

## References

- Official repository and data layout / attribution: https://github.com/hudl/open-data
- Official event and match schema: https://raw.githubusercontent.com/statsbomb/open-data/master/doc/StatsBomb%20Open%20Data%20Specification%20v1.1.pdf
- StatsBomb public data resource centre and current agreement entry point: https://statsbomb.com/resource-centre/

## Approval state

- Technical adapter: implemented; CI result tracked in PR #51.
- Personal research: candidate subject to current agreement and registration conditions.
- Raw-data redistribution: not approved.
- Production ingestion / model training: not approved by this document.
