# StrikerAPI ↔ 5DollarFootballAPI Read-Only Reconciliation Contract

Status: specification only. No provider records have been cross-linked, no production data has been written, and no import is authorized.

## 1. Purpose

Compare overlapping fixture samples from StrikerAPI and the verified 5DollarFootballAPI account to assess whether the two providers can be reconciled safely. The report is an audit artifact, not an instruction to merge provider records.

Official schema references:
- StrikerAPI `list_games`: https://strikerapi.com/docs/list-games
- StrikerAPI data atlas: https://strikerapi.com/docs/atlas
- 5DollarFootballAPI fixture list: https://5dollarfootballapi.com/docs/fixtures
- 5DollarFootballAPI league fixtures: https://5dollarfootballapi.com/docs/league-fixtures

## 2. Provider identity is never interchangeable

Keep the original source identity exactly as issued by each provider.

| Attribute | StrikerAPI | 5DollarFootballAPI |
|---|---|---|
| Fixture ID | `game_id` | `id` |
| Competition identity | Explicit `league` request key | `league.id` |
| Home team identity | `home.team_id` | `teams.home.id` |
| Away team identity | `away.team_id` | `teams.away.id` |
| Kickoff | `starts_at` (UTC timestamp) | `kickoff_utc` (UTC timestamp) |
| Status | `scheduled` / `final` | `scheduled` / `finished` |
| Final score | `home.score`, `away.score` | `goals.home`, `goals.away` |

Never copy a StrikerAPI identifier into a 5Dollar identity field or vice versa. Preserve both IDs and each original payload hash/retrieval timestamp in source provenance.

## 3. Competition mapping gate

A comparison is permitted only after the 5Dollar league ID has been read from the authenticated provider catalogue and mapped to an explicit canonical competition:
- StrikerAPI `soccer` ↔ 5Dollar league whose verified catalogue record is Premier League.
- StrikerAPI `brazil` ↔ verified 5Dollar Brazil Serie A league record.
- StrikerAPI `argentina` ↔ verified 5Dollar Argentina Liga Profesional league record.

Do not match by a loose substring or country alone. Women's, reserve, youth, cup and men's senior competitions must remain distinct. The NWSL has no assumed 5Dollar counterpart; do not compare it unless a matching competition is independently established.

## 4. Candidate matching

Generate a candidate only when all conditions hold:
1. Both source rows are valid and represent the same explicit canonical competition.
2. Both have non-empty home and away team names and valid UTC kickoff timestamps.
3. Home and away orientation is identical; do not silently reverse teams.
4. Team names match after conservative normalization: Unicode NFKC, case-folding, whitespace collapse and punctuation normalization. Do not strip meaningful suffixes such as Women, U21, U23, Reserves, II or B.
5. Absolute kickoff difference is no more than five minutes.

An alias may be used only when supported by an independently verified team identity mapping. Every alias must be versioned and evidence-backed. Do not infer aliases from scorelines or a single fuzzy-name match.

Final scores and statuses are validation signals only; they must not be used to create a candidate match. A score agreement cannot repair a failed identity match.

## 5. Outcomes

Each candidate pair receives exactly one outcome:
- `MATCHED_UNIQUE`: one and only one candidate pair, all identity conditions pass.
- `UNMATCHED_STRIKER_ONLY` / `UNMATCHED_5DOLLAR_ONLY`: no candidate on the other provider.
- `AMBIGUOUS_MULTIPLE_CANDIDATES`: more than one candidate; quarantine.
- `IDENTITY_CONFLICT`: team orientation, competition or kickoff evidence conflicts; quarantine.
- `STATUS_CONFLICT`: same identity candidate but provider statuses disagree; retain both observations and quarantine.
- `RESULT_CONFLICT`: same identity candidate but final scores disagree; retain both observations and quarantine.

No ambiguous or conflicting pair is auto-resolved. The reconciliation report must include source IDs, competition keys/IDs, team IDs, kickoff timestamps and deltas, statuses, scores, decision reason and source payload hashes.

## 6. Report invariants

For every bounded comparison window:
- Record both providers' exact query windows, request counts and documented credit/quota cost.
- Record rows fetched, valid rows, unique source IDs, duplicate source IDs, matched pairs, unmatched rows, ambiguous candidates and conflicts.
- Prove the accounting identity: fetched valid rows = uniquely matched source rows + unmatched source rows + quarantined source rows, with each source row counted once.
- Never count a candidate pair as a canonical fixture merge.
- Never overwrite one provider's observation with another provider's values.
- Do not infer missing provider records or fabricate scores, team IDs, competition IDs or timestamps.

## 7. Persistence boundary

The current foundation schema uniquely identifies fixtures by `(provider, provider_fixture_id)`; it does not define a cross-provider fixture-link table. Therefore:
- keep this reconciliation read-only and export a report;
- do not merge two providers' fixture rows into one canonical row;
- if approved later, design a separate migration for a reviewed cross-provider link entity with uniqueness, provenance and conflict state;
- do not change or rewrite the already-applied foundation migration.

## 8. Acceptance

This reconciliation gate passes only when:
- competition mappings are independently verified;
- all matched pairs are unique under the deterministic rules;
- all duplicates, ambiguous cases and conflicts are enumerated;
- provider-specific IDs and payload provenance remain intact;
- no database writes or production imports occurred.

A reconciliation pass establishes identity confidence only. It does not certify statistical completeness, xG quality, odds coverage, model quality or value-betting performance.
