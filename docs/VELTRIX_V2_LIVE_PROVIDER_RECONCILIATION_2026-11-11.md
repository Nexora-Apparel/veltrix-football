# VELTRIX FOOTBALL 2.0 — Live OpenFootball / 5Dollar / FPL Evidence

**Acquisition run:** [GitHub Actions #43006165384](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43006165384)  
**Repository commit:** `e5c77000a3c343718d46e23eecb545be4992bf61`  
**Retrieved:** 2026-11-11 UTC  
**Artifact:** [Download evidence](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43006165384/artifacts/13849170307)  
**Artifact SHA-256:** `61d20d5f0a18890c3a0d4462824fdc5f24fdc17f11fb63eadb2ff11e99bf3120`

## Acquisition outcome

The workflow completed successfully, including five offline reconciliation safeguard tests, snapshot acquisition, row-level reconciliation and artifact upload. This means the acquisition and audit process ran; it does **not** mean OpenFootball passed source acceptance.

The initial workflow failure was a league catalogue identity assumption. The authenticated 5Dollar catalogue uses the exact name `England Premier League` and previously qualified league ID `4160026622`, not only the docs-example name `Premier League`. The lookup now checks documented country/search/popular filters and recognizes the exact previously qualified alias without guessing an ID.

## Pinned source evidence

### OpenFootball EPL
- Repository: `openfootball/football.json`
- File: `2026-27/en.1.json`
- Pinned source commit: `e6744429ee395bc86f247348c6184bb08d4eb361`
- Payload SHA-256: `bb91f0ab3e8359df163bb9ec98549bfed85e200dd4c32f3bd606b5890d932dd2`
- Rows in the requested 90-day comparison window: 100
- Rows carrying a full-time score in that window: 45

### 5DollarFootballAPI EPL
- Exact catalogue identity: `England Premier League`
- Qualified league ID: `4160026622`
- Finished fixture rows in the same 90-day UTC window: 100
- Payload SHA-256: `d22dcd13d2cc53d713ef661d52778755680919948be192055ee95ebfe0fb51fa`
- All 100 reference rows had final score values and unique fixture IDs in this snapshot.

### FPL public snapshot
- Bootstrap response: HTTP 200
- Player records: 672
- EPL teams: 20
- Fixture records: 380
- Player rows with non-null season totals for minutes, goals, assists, xG, xA and xGC: 672 each.
- Player rows with a non-null status field: 672.
- `chance_of_playing_next_round`: 374 non-null; 298 null.
- Bootstrap SHA-256: `f4a3c27f6e71641c98b09775ec951469a49760c581adbe7881fd521039b6d6f1`
- Fixture SHA-256: `ce30fce58d110a21c446420455f37f8b67c1c82c03ee2d8366cb990e0d78d0b5`

FPL data is season-level fantasy/player aggregation, not a full per-match player-stat feed. Its public API is undocumented and remains an optional research source pending terms, retention and stability review.

## Exact row-level reconciliation

The explicit 20-team crosswalk resolved all team names. We compared ordered home/away identity and calendar date. OpenFootball date/time values have no timezone; they were not converted to UTC or silently shifted.

| Check | Result |
|---|---:|
| OpenFootball rows in window | 100 |
| 5Dollar finished reference rows | 100 |
| Exact date + ordered team matches | 94 |
| Score agreements | 45 |
| Score conflicts | 0 |
| OpenFootball missing scores on exact matches | 49 |
| One-day date conflicts for same ordered teams | 6 |
| Unmatched reference fixtures | 0 |
| Unmatched OpenFootball fixtures | 0 |
| Duplicate OpenFootball keys | 0 |
| Duplicate 5Dollar fixture IDs | 0 |
| Duplicate 5Dollar match keys | 0 |
| Invalid 5Dollar rows | 0 |

Score agreement among comparable scores was 45/45 (100%). However, only 45/100 reference fixtures had a comparable OpenFootball score: score coverage was 45%. Six additional same-team fixtures had a one-day date disagreement. The exact date/time mismatch is preserved as a conflict because OpenFootball does not provide a timezone.

## Decision

**OpenFootball is NOT accepted as the current-season EPL results source.** The score coverage is inadequate and the six date conflicts prevent source acceptance. Keep it as a supplemental historical/results candidate only; do not use this snapshot to train or update production predictions.

**5Dollar remains the bounded EPL fixture/results reference** within its already qualified plan and time window. Do not expand this acceptance to other competitions or other data domains automatically.

**FPL is a promising optional EPL player-season-statistics source**, but not yet production-approved. It does not fill the full player-match history, lineup confirmation, injury provenance or cross-competition requirements.

No Neon writes occurred. No prediction model, feature, calibration, publication, Telegram report or schedule was changed or activated.

## Next steps

1. Investigate the six OpenFootball date conflicts and 49 missing scores upstream; do not normalize them away.
2. Qualify OpenPlay's historical event/player/lineup/xG dataset, with its CC BY 4.0 attribution and source/model provenance.
3. Keep FPL optional while checking terms, API stability, player-season field definitions and player-summary match-history availability.
4. Investigate PitchAPI's data lineage and model-training/storage rights before any persistent ingestion.
5. Continue with accepted 5Dollar EPL records and only the separately qualified player/event sources.
