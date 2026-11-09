# StrikerAPI ↔ 5DollarFootballAPI Alias Candidate Review

Status: **REVIEW ONLY — no aliases approved, no matcher changes, no canonical links, no database writes.**

## Evidence source

GitHub Actions run [42650167137](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42650167137), artifact `strikerapi-5dollar-epl-reconciliation` (artifact ID `13688769132`), report schema version 1. The report contains 100 unmatched StrikerAPI rows and 100 unmatched 5Dollar rows after 18 strict-name matches.

## Diagnostic method

The 82 unmatched rows on each side were grouped by parsed UTC kickoff instant. Each provider had the same 54 kickoff groups and the same row count per group. Within each exact-kickoff group, a one-to-one assignment was ranked by the sum of home-name and away-name string similarities (SequenceMatcher over case-folded alphanumeric names). No score, status, result, or team-ID value was used to create the candidate assignment.

This diagnostic produces 82 fixture-pair candidates across the 90-day window. It is **not** a canonical identity decision: matching kickoff plus similar names is supporting evidence, not independent proof. The original strict matcher remains unchanged.

## Team alias candidates

Across the 82 candidate fixture pairs, the following 20 provider team-ID pairs recur. Counts are team-side observations across the paired fixtures, not independent external verification.

| StrikerAPI team ID | StrikerAPI name | 5Dollar team ID | 5Dollar name | Observations |
|---:|---|---:|---|---:|
| 306 | Hull City | 2133281510 | Hull | 10 |
| 331 | Brighton & Hove Albion | 1298357733 | Brighton | 10 |
| 337 | Brentford | 2493508502 | Brentford | 6 |
| 349 | AFC Bournemouth | 4091605164 | Bournemouth | 10 |
| 357 | Leeds United | 2580270069 | Leeds | 10 |
| 359 | Arsenal | 2592538664 | Arsenal | 5 |
| 360 | Manchester United | 762247077 | Man Utd | 10 |
| 361 | Newcastle United | 2064095235 | Newcastle | 10 |
| 362 | Aston Villa | 1807930046 | Aston Villa | 7 |
| 363 | Chelsea | 3399423062 | Chelsea | 5 |
| 364 | Liverpool | 94606195 | Liverpool | 6 |
| 366 | Sunderland | 2683519683 | Sunderland | 6 |
| 367 | Tottenham Hotspur | 2091670802 | Tottenham | 10 |
| 368 | Everton | 761437401 | Everton | 7 |
| 370 | Fulham | 248206832 | Fulham | 5 |
| 373 | Ipswich Town | 2014429473 | Ipswich | 10 |
| 382 | Manchester City | 3103334772 | Man City | 10 |
| 384 | Crystal Palace | 139660649 | Crystal Palace | 7 |
| 388 | Coventry City | 1193753576 | Coventry | 10 |
| 393 | Nottingham Forest | 2220360869 | Nottm Forest | 10 |

## Interpretation and restrictions

- The fixture-level candidate set is consistent across provider schedules: exact UTC kickoff groups, home/away orientation, and similar club names.
- Repeated team-ID pairings across multiple fixtures strengthen the hypothesis that these are provider-specific identifiers for the same clubs.
- This does **not** independently prove that the IDs belong to those clubs. The artifact does not contain authoritative provider team-catalogue responses or external club identity evidence.
- Several names are abbreviations (for example, `Man Utd`, `Nottm Forest`, `Hull`); these are candidates, not yet accepted aliases.
- The 20 candidate ID mappings are competition-scoped to the authenticated Premier League comparison only. Do not reuse them across competitions, seasons, women's teams, reserves, youth teams, or other providers.
- Do not add them to the production matcher until each provider team ID is verified against its own team catalogue or equivalent official provider documentation, with evidence URL, retrieval date, competition scope, and reviewer recorded.
- After independent verification, add a versioned alias registry and regression tests for ID scope, competition scope, orientation, ambiguity, and cross-team collision. Then rerun reconciliation and compare strict vs alias-assisted outcomes.

## Current gate

The live audit remains **18 strict matches + 82 unmatched per provider**. The 82 proposed pairs are a separate diagnostic candidate set and must not be added to the accepted match count. Phase 3 reconciliation sign-off remains pending.



## Live provider-catalogue verification — 2026-11-09

The corrected workflow completed successfully:
- Run: [42679026303](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42679026303)
- Commit: `17e2bb2d7d877ee28c3e6a5aab0707d19ad0f6a4`
- Workflow tests: 6 alias-verifier tests passed; 7 registry-safety tests passed.
- StrikerAPI: one `POST /v1/list_teams` request for season 2026.
- 5DollarFootballAPI: 20 `GET /v1/teams/{id}` requests.
- Result: `TEAM_ALIAS_VERIFIED: 20/20`; each requested ID was returned by its own provider with a team name.
- Artifact: [strikerapi-5dollar-team-alias-verification](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42679026303/artifacts/13701866539), SHA-256 `4c6ebc968f2d2798b6f10737b6a419bae1aed9272a49ac9f931d35a06f347ca3`.
- The artifact was downloaded and inspected. All 20 IDs exist in the respective catalogues and the returned names align with the candidate names/known short forms.
- Database writes, imports and canonical merges: zero.

**Important distinction:** this proves that each provider recognizes the individual team IDs and returns the recorded names. It does not expose a provider-issued crosswalk proving that a particular StrikerAPI ID and 5Dollar ID are the same real-world club. The proposed pairings still originate from the repeated fixture-level schedule comparison described above. Therefore, the registry remains `review_only`, all 20 rows remain `pending_independent_verification` for cross-provider identity, and the production matcher remains unchanged. Do not promote these aliases solely on the 20/20 catalogue lookup result.

The workflow initialization defect in the first attempt was fixed in commit `17e2bb2`. Both offline test suites then passed (13 total tests), and the live catalogue verifier plus artifact upload completed successfully.

## Registry and provider-catalogue verification implementation

The qualification branch now contains `data/provider_team_aliases.json`, a versioned registry with all 20 pairs marked `pending_independent_verification`, scoped to `england_premier_league` / `2026-27`. It is review-only and is not connected to the reconciliation matcher.

`app/provider_team_aliases.py` validates scope, duplicate/colliding IDs and evidence requirements. An alias can only be used when the entire registry is explicitly promoted to `approved`, every non-rejected row has been resolved, and each approved row carries an evidence URL, timezone-aware retrieval timestamp and reviewer. A pending registry never authorizes a match.

The manual/push-triggered workflow `.github/workflows/verify-strikerapi-team-aliases.yml` performs:
- one StrikerAPI `POST /v1/list_teams` request with only the documented `season: 2026` parameter (1 credit);
- 20 5DollarFootballAPI `GET /v1/teams/{id}` lookups;
- offline verifier and registry safety tests;
- sanitized JSON artifact upload, seven-day retention.

The initial draft was corrected to remove an undocumented `league` parameter from StrikerAPI `list_teams`. Official references: https://strikerapi.com/docs/list-teams and https://5dollarfootballapi.com/docs.

The live workflow result and catalogue artifact have now been inspected (run 42679026303). All 20 provider IDs exist in their respective catalogues, but cross-provider club identity still requires independent review. All 20 registry entries remain pending and the strict reconciliation remains 18 matched / 82 unmatched per provider.
