# Point-in-Time Feature Source Gaps

Status: evidence register; no provider or model is promoted by this document.

## Current evidence boundary

The qualified 5Dollar historical acquisition path currently normalizes fixture identity, competition and season, team IDs/names, kickoff, status, final score, endpoint, retrieval timestamp and source-payload SHA-256. It does not retain raw provider payloads in the sanitized archive.

The historical coverage profiler explicitly reports these metrics as unavailable in the acquired archive:

- expected goals (xG)
- shots
- lineups and player minutes
- odds
- point-in-time Elo
- PPDA
- travel and fatigue

This is a statement about the acquired/normalized evidence, not a claim that every 5Dollar API endpoint is incapable of returning those fields. Each additional endpoint and data type requires separate read-only qualification and a schema/provenance review.

## Model compatibility rule

The current Dixon-Coles inference engine requires all six of the following point-in-time features:

- `home_team_elo`
- `away_team_elo`
- `home_rolling_xg_for`
- `home_rolling_xg_against`
- `away_rolling_xg_for`
- `away_rolling_xg_against`

Final scores are outcome labels. They must not be relabelled as xG, and post-match xG must not be treated as pre-match xG for the same fixture. A goals-only feature family, if developed, must have distinct names, a distinct model version and independent chronological calibration; it cannot silently satisfy the xG feature contract.

Until the six required features have admissible point-in-time provenance, inference must withhold the forecast. No synthetic, global-prior or home-default fallback is permitted.

## Point-in-time admission requirements

Every candidate feature source must provide or support evidence for:

1. Stable source and record identifiers.
2. Competition-specific and season-specific coverage.
3. A documented observation timestamp.
4. A documented availability timestamp showing when the value became knowable.
5. A retrieval timestamp no later than the fixture's prediction cutoff for historical backtests, or an independently verified archival snapshot that proves the value existed by that cutoff.
6. A canonical payload digest and source endpoint.
7. Missingness, revision and provider overwrite behaviour.
8. Rights to retain the required historical data and derived features for research and intended product use.

A timestamp assigned at current download time does not establish historical point-in-time availability. A match's kickoff timestamp alone does not establish when its final score or post-match statistics became available.

## Source qualification matrix

| Data family | Current evidence | Admission status |
|---|---|---|
| Fixtures and final scores | 5Dollar qualified for five competition IDs in the measured 90-day window | Qualified for this bounded data type/window only |
| xG / shot locations | Not present in the acquired normalized archive | Not admitted |
| Lineups / player minutes | Not present in the acquired normalized archive | Not admitted |
| Odds with historical timestamps | Not present in the acquired normalized archive | Not admitted |
| Point-in-time Elo | Not present in the acquired normalized archive | Not admitted |
| PPDA / pressing | Not present in the acquired normalized archive | Not admitted |
| Travel / fatigue | Not present in the acquired normalized archive | Not admitted |

StrikerAPI's partial statistics and xG/shot coverage remain competition-dependent. Retrospectively available or refittable provider xG is not automatically point-in-time safe. It requires its own timestamp, revision and coverage audit before admission.

## Next qualification work

1. Inspect the exact 5Dollar endpoint schemas for xG, shots, lineups and odds without spending additional requests unless the endpoint access is already covered by an approved budget.
2. Identify an independent source with competition-level historical coverage and point-in-time timestamps for any missing feature family.
3. Preserve a dated, hashed evidence sample per source and competition.
4. Run the point-in-time feature contract against real samples, including late-arriving and revised-record rejection tests.
5. Only then construct chronological training datasets and fit model parameters.

## Release boundary

This register does not certify training readiness, model accuracy, value betting, publication or provider rights. It authorizes no production imports, database writes, prediction publication, Telegram delivery, scheduling or paid provider spend.
