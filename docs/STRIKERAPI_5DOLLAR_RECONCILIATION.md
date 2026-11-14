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

The authenticated 5DollarFootballAPI Free-tier catalogue returned exactly five competitions in the qualification run: England Premier League, France Ligue 1, Germany Bundesliga I, Italy Serie A and Spain La Liga. The only confirmed overlap with the current StrikerAPI qualification set is the English Premier League:
- StrikerAPI `soccer` ↔ 5Dollar competition ID `4160026622`, verified from the authenticated catalogue and historical preflight log.

The following mappings are **not available on the verified Free-tier account** and must not be fabricated:
- StrikerAPI `brazil` has no Brazil Serie A counterpart in the returned 5Dollar catalogue.
- StrikerAPI `argentina` has no Argentina Liga Profesional counterpart in the returned 5Dollar catalogue.
- StrikerAPI `nwsl` has no NWSL counterpart in the returned 5Dollar catalogue.

The reconciliation run must therefore compare the Premier League only. Argentina, Brazil and NWSL remain StrikerAPI-only until another source or a separately verified 5Dollar entitlement supplies a real counterpart. Never match by country or loose competition-name substring. Women's, reserve, youth, cup and men's senior competitions must remain distinct.

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

## Verified account coverage correction

The 5Dollar qualification run `42504992170` recorded these exact Free-tier catalogue entries:
- England Premier League — ID `4160026622`
- France Ligue 1 — ID `3614399544`
- Germany Bundesliga I — ID `686337048`
- Italy Serie A — ID `3405541143`
- Spain La Liga — ID `4212821298`

The same run returned 99 Premier League finished fixtures in the 90-day preflight. No Argentina or Brazil competition was returned. Therefore, the only currently valid cross-provider mapping is StrikerAPI `soccer` to 5Dollar ID `4160026622`. The live reconciliation sample must be Premier League-only; do not fabricate missing competition IDs or use the 5Dollar public documentation's illustrative IDs in place of the authenticated account catalogue.


## Executable offline reconciliation

`scripts/reconcile_provider_fixtures.py` implements the contract as a deterministic, offline JSON-to-JSON audit. It has no API client, database connection or persistence code. It accepts:
- a StrikerAPI envelope containing `league_key`, retrieval metadata and `data.games`;
- a 5DollarFootballAPI envelope containing retrieval metadata and a `data` fixture array;
- an explicit JSON mapping from StrikerAPI competition key to the independently verified 5Dollar league ID.

Example:

```bash
python scripts/reconcile_provider_fixtures.py \
  --striker striker-export.json \
  --fivedollar fivedollar-export.json \
  --competition-map verified-competition-map.json \
  --output reconciliation-report.json
```

The implementation preserves both source IDs and hashes each original row, applies conservative Unicode-aware team-name normalization, requires same home/away orientation and a kickoff delta of at most 300 seconds, and checks result/status conflicts only after identity matching. Ambiguous, reversed, conflicting and invalid records are quarantined. It reports per-provider accounting balances and blocks acceptance when source IDs are duplicated. It never creates a canonical fixture or writes to a database.

Unit coverage is in `tests/test_strikerapi_reconciliation.py`. This is implementation readiness only: no live provider exports have yet been compared, and the reconciliation gate remains pending until real, independently mapped samples are processed.


## Reconciliation safety hardening

The offline implementation quarantines every row whose source ID is duplicated, rejects non-string or timezone-naive kickoff values as invalid, and keeps duplicate/invalid rows out of candidate matching. Ambiguous candidate graphs, reversed home/away orientation, status disagreements and score disagreements are quarantined rather than accepted.

The report's `acceptance_pass` is deliberately stricter than accounting balance: it requires at least one unique matched pair, balanced accounting for both sources, zero quarantined rows and zero duplicate source IDs. Unmatched rows may remain when a provider has additional fixtures, but they are never treated as matched. A report can be fully balanced while acceptance remains false.

Regression coverage includes duplicate-ID quarantine, non-string kickoff rejection, status and result conflicts, reversed orientation, ambiguity, five-minute tolerance and a positive unique-match case. The latest tests must pass in CI before the implementation is considered validated.


## Live Premier League reconciliation workflow

The only current cross-provider overlap is StrikerAPI `soccer` ↔ authenticated 5Dollar Premier League ID `4160026622`. The workflow uses a fixed 90-day UTC window and read-only calls:
- StrikerAPI `POST /v1/list_games`, `league=soccer`, `status=final`, paginated with `next_offset`;
- 5DollarFootballAPI `GET /v1/leagues/4160026622/fixtures`, `status=finished`, fixed `start_time/end_time`, paginated with `page/per_page`.

The new `scripts/run_readonly_epl_reconciliation.py` validates both provider exports, applies the deterministic matcher, and writes `strikerapi_5dollar_epl_reconciliation.json`. The report retains provider-specific source IDs, normalized identity fields and SHA-256 hashes of original payloads; it does not embed raw provider payloads or credentials. It records exact query windows, page counts, request/credit usage and the database-write invariant.

The manual StrikerAPI workflow now also requires the existing GitHub Actions secret `FIVEDOLLARFOOTBALL_API_KEY`, runs the live reconciliation after the bounded provider probe, and uploads the sanitized report as a seven-day Actions artifact named `strikerapi-5dollar-epl-reconciliation`. It remains read-only: no Neon connection, SQL, imports, checkpoints, canonical merges or production writes. A completed audit with conflicts still produces an artifact and reports `FAIL_REVIEW_REQUIRED`; the report is diagnostic evidence, not automatic source approval.

The updated workflow version is on the qualification branch. A manual dispatch must select `phase-3/strikerapi-readonly-qualification` so it runs the new cross-provider step. Until that run is completed and the report is inspected, the live reconciliation gate remains pending.


## Alias-assisted live reconciliation result (2026-11-09)

The approved, scope-limited alias registry was integrated into the read-only matcher and the live Premier League workflow. The latest 90-day run is [42680798028](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42680798028), with sanitized artifact [13701808156](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42680798028/artifacts/13701808156).

- 100 StrikerAPI rows and 100 5DollarFootballAPI rows.
- 100 unique matches; zero unmatched rows, quarantines, duplicates, ambiguity or conflicts.
- All kickoff deltas: 0 seconds.
- All statuses and final scores agreed.
- Identity evidence: 18 strict-name, 54 one-side alias, 28 two-side alias matches.
- Alias scope: Premier League 2026-27 only.
- 3 StrikerAPI calls (6 credits), 1 5Dollar call.
- No database writes, imports, checkpoints or canonical merges.

The report was downloaded and inspected. It is a successful bounded reconciliation, not a production import authorization or general provider-quality certification. The 5Dollar Free-tier competition limitation remains unchanged: Argentina, Brazil and NWSL still have no verified 5Dollar counterpart.
