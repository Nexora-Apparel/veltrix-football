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


## Anchored crosswalk audit — 2026-11-09

A second deterministic audit was implemented and run against the sanitized baseline reconciliation artifact from run `42650167137`:

- Workflow run: https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42680085808
- Artifact: https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42680085808/artifacts/13701329212
- Artifact SHA-256: `ebfea11b44d82ac4597f7f1a0da9f588899b93ecd9e5f0ce24d641e629a1973a`
- Six anchored-crosswalk unit tests passed.
- Nine distinct team mappings were seeded from the 18 strict unique fixture matches.
- The audit paired remaining fixtures only where UTC kickoff was identical and at least one already-established team ID pair appeared on the same home/away side.
- No scores, statuses, fuzzy names or team-name similarity were used to infer a mapping.
- Result: 20 team mappings, all 82 previously unmatched fixture pairs accounted for, zero remaining unmatched rows, zero conflicts.
- Each inferred team mapping has at least five distinct anchored fixture-pair observations; the audit's configured minimum was three.
- Database writes, imports and canonical merges: zero.

This is materially stronger than catalogue existence alone: it is a repeated fixture-graph crosswalk anchored by exact team-name fixture matches. It remains limited to the exact Premier League 2026-27 sample and must not be extrapolated to other competitions or seasons.

## Scoped alias registry promotion

Based on the 20/20 provider catalogue result plus the anchored crosswalk audit, all 20 mappings were promoted in `data/provider_team_aliases.json` to `approved`, but only under `england_premier_league` / `2026-27`. The registry records both artifact URLs, retrieval timestamps, strict-seed status and anchored fixture support counts. The matcher requires an explicit competition key and season; registry approval alone does not enable aliases outside that exact scope.

The read-only reconciliation engine now has optional alias-registry support and records whether each side matched by strict name or approved alias. The live Premier League runner loads the scoped registry and passes the explicit competition/season. This remains a diagnostic reconciliation path, not production prediction code and not a canonical merge.


## Fresh alias-assisted live reconciliation — PASS

A fresh 90-day live comparison was run after scoped aliases were approved and integrated into the read-only reconciliation engine:

- Workflow run: [42680798028](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42680798028)
- Commit: `b28f88d91337c85281b19734c8a5b3370211671a`
- Artifact: [strikerapi-5dollar-epl-reconciliation](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42680798028/artifacts/13701808156)
- Artifact SHA-256: `252c2656805cea95595d55c86b6f275c175b587b75689ab4a409e2ead9534e10`
- Window: `2026-08-11T19:11:02Z` to `2026-11-09T19:11:02Z`.
- StrikerAPI: 100 finished fixtures, 3 calls / 6 credits.
- 5DollarFootballAPI: 100 finished fixtures, 1 call.
- Result: 100/100 `MATCHED_UNIQUE`; zero unmatched, ambiguous, quarantined, duplicate or conflict rows.
- All 100 kickoff deltas were exactly zero seconds.
- All 100 status pairs agreed (`final` / `finished`) and all 100 final scores agreed.
- Identity methods: 18 strict-name matches, 54 one-side approved-alias matches, 28 two-side approved-alias matches.
- The 11 non-seed alias pairs were each used in 10 distinct fixture matches.
- Alias scope recorded in report: `england_premier_league` / `2026-27`; registry status `approved`.
- Database writes, imports, checkpoints and canonical merges: zero.

The artifact was downloaded and inspected, not just inferred from the workflow's exit code. The full source accounting balances on both providers (100 total = 100 matched + 0 unmatched + 0 quarantined). This establishes a clean bounded cross-provider reconciliation for this exact 90-day Premier League sample. It does not establish broader competition coverage or authorize historical imports.

## Current gate

The baseline strict-name audit remains **18 strict matches + 82 unmatched per provider**. The separate anchored crosswalk audit now supports all 20 team-ID mappings across those 82 fixtures, without fuzzy names or score/status evidence. The fresh live 90-day alias-assisted reconciliation passed 100/100 with zero conflicts. Phase 3 sign-off remains pending for broader provider coverage, data-rights review and import qualification.



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
