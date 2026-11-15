# VELTRIX FOOTBALL 2.0 — AI Midas staging import contract

**Date:** 2026-11-15  
**Status:** EXECUTED IN ISOLATED STAGING — 14/14 FILE-LEVEL RAW EVIDENCE RECORDS AND INDEPENDENT READBACK VERIFIED; NO NORMALIZED ROW OR MODEL ADMISSION  
**Source approval:** `approval-aimidas-football-data-noncommercial-2026-11-15`  
**Source pin:** `aimidas1/aimidas1@29baca362a34ce5dcd3924b07ec9c7d5139d83fc`  
**Target:** isolated Neon staging only; never production

## 1. Import boundary

The AI Midas public CSVs are now pinned, audited and independently snapshot-verified. This contract defines how to stage them without manufacturing temporal evidence or contaminating canonical provider data.

Permitted execution target:
- Existing isolated staging branch `br-silent-violet-bc5de88s` / `veltrix-phase3-import-dry-run`, database `veltrix_football_staging`, only after a separate exact-head implementation/test review.
- No production branch, production database, Vercel deployment, prediction publication, Telegram delivery, schedule activation or PR merge.
- No source data files or raw snapshots may be uploaded to the public repository's Actions artifacts. The approved workflow retains only `manifest.json` and `verification.json`; raw files remain ephemeral on the runner until a private staging import is implemented.

The audit and snapshot workflow are read-only. The subsequent bounded importer wrote only the 14 pinned raw CSV responses, 14 file-level source observations, one source-approval record/status event, and capture-manifest evidence to the isolated staging branch. No production writes were made.

## 2. Source identity and approval

Use these constants consistently:

- Provider: `AIMidasFootballData`
- Source ID: `ai-midas-github-csv`
- Approval ID: `approval-aimidas-football-data-noncommercial-2026-11-15`
- Repository: `aimidas1/aimidas1`
- Source revision: `29baca362a34ce5dcd3924b07ec9c7d5139d83fc`
- Attribution: `AI Midas Football Data`; preserve upstream lineage `griffisben/Post_Match_App/Stat_Files` for the advanced-stats mirror.
- `commercial_use_allowed=false`
- `raw_redistribution_allowed=false`

Keep three semantic data classes separate:
1. `historical_match_statistics` — match results and match-level statistics from the six historical target-competition archives and completed season files.
2. `advanced_team_match_statistics` — Brazil Série B 2026 team-match advanced-statistics rows.
3. `historical_average_odds` — `avg_odds_*` fields only; not bookmaker quote observations.

The authorization evidence is the user-confirmed legal record in `docs/legal/aimidas-noncommercial-authorization-2026-11-15.md`. The repository and its identified upstream repository expose no SPDX licence metadata; do not invent one.

## 3. Raw response and source-observation persistence

Use the existing append-only provenance schema; do not add a new table merely to duplicate existing raw evidence.

### `provider_responses`

One immutable response row per pinned CSV file:

- `provider=AIMidasFootballData`
- `source_id=ai-midas-github-csv`
- `endpoint=github_raw/<repository-path>`
- `request_id=aimidas:<source-commit>:<path-sha256>` (deterministic)
- `request_params`: repository, exact path, pinned commit and expected Git blob SHA-1
- `http_status=200`
- `raw_body`: exact downloaded CSV bytes
- `response_sha256`: SHA-256 of exact raw bytes
- `fetched_at`: actual UTC retrieval time
- `response_headers`: allowlisted non-sensitive response metadata only

Never place GitHub tokens or authorization headers in stored request/response metadata. No API key is required for these public files.

### `source_observations`

Create a file-level immutable observation linked to the exact `provider_response_id` for each file. Use a source-specific entity identity such as `dataset_file`; do not pretend a row has a canonical fixture ID when no crosswalk exists.

Required temporal values:

- `retrieved_at=recorded_at=<actual Veltrix retrieval time>`
- `available_at=<actual Veltrix first-observed time>`
- `availability_basis=first_observed`
- `source_event_time=NULL`
- `source_published_at=NULL`
- `source_effective_at=NULL`
- `source_timestamp_raw=<source date field, if present>`
- `source_timestamp_basis=source_date_only_timezone_unverified`
- `point_in_time_certifiable=false`
- `rights_approval_id=approval-aimidas-football-data-noncommercial-2026-11-15`

The repository commit timestamp is revision metadata, not the publication timestamp of every CSV row. Never backdate `available_at` to a match date or repository commit time.

A deterministic `provider_entity_id` must include source path, pinned revision and a stable row identity. The exact raw file hash remains the parent provenance key.

## 4. Brazil Série B 2026 identity contract

Read-only reconciliation against the staging canonical registry established:

- 20/20 team names resolve after ten explicit accent/spelling aliases.
- 369 AI Midas matches map one-to-one to 369 canonical 5Dollar fixtures.
- 0 source rows are unmatched or ambiguous.
- All 369 source scores match the canonical result rows.
- Canonical universe: 371 finished fixtures with results; AI Midas coverage 369/371 (99.46%).
- Two canonical fixtures are absent from the source file.
- 333 source dates equal the canonical UTC date; 36 are one UTC date later. The source date is not a timezone-aware kickoff.

The crosswalk is a high-confidence candidate set, but it has **not** been inserted into `entity_crosswalk_versions`. That table requires an evidence observation and a reviewer for non-`EXACT_PROVIDER_ID` resolved mappings. The source has no shared provider fixture IDs. Do not mark these mappings `RESOLVED` until the crosswalk review has been recorded with a valid reviewer identity and evidence observation.

For import:
- Preserve the source's `Date` exactly as a date-only string.
- Keep the 369 exact matches as crosswalk candidates.
- Keep the two absent canonical fixtures explicitly absent; do not synthesize AI Midas observations.
- Do not convert the 36 next-day UTC cases to another date or infer a timezone.
- Store the two-team rows separately and link them to the same fixture only after the crosswalk is approved.

## 5. Historical match archives and feature policy

The six historical match CSVs contain 19,605 rows across Brazil Série A and five European target competitions. The other match files add 2,308 rows; Brazil Série B advanced stats add 738 team rows.

For the first staging import, retain raw source payloads and the field-level audit. Any normalized derived sidecar must retain:
- source path and pinned commit;
- file Git blob SHA-1 and raw response SHA-256;
- row identity and canonical row-payload SHA-256;
- actual retrieval/recording timestamp;
- original date string and timezone status;
- competition/season label and source team names;
- source-specific entity ID and any crosswalk evidence.

Feature rules:

- Final scores and results are retrospective labels, not proof of historical pre-match availability.
- Actual xG/xGA, shots, possession, PPDA, corners, cards and Brazil Série B advanced metrics are post-match. Never feed a fixture's own post-match metrics into that fixture's prediction.
- `pre_match_*` and `*_prematch` fields are not PIT-admissible: no row-level `known_at`, publication timestamp or methodology proof was found.
- `avg_odds_ft_1/x/2` and other `avg_odds_*` fields remain average odds. Do not insert them into `odds_quote_observations`; there is no bookmaker identity, timestamp or closing definition.
- No historical walk-forward backfill, CLV claim, bookmaker benchmark certification or 98% timestamped-odds credit is permitted.
- Future forecasts may use only leakage-safe aggregates built from already completed historical matches after the source data have actually been imported and recorded. This does not retroactively make old rows PIT-certifiable.

## 6. Import-run and acceptance controls

- Import is idempotent by exact pinned source revision, file path and raw content hash.
- Record one import run with an exact manifest SHA-256 and bounded 14-file request count.
- Re-read all source approvals at execution time; fail closed if status, scope or permitted uses do not match.
- Persist raw responses and file-level observations atomically in staging.
- Run the independent snapshot verifier before any import.
- Reconcile file counts, row counts, date ranges, field completeness, hash lineage, duplicate identities and source-to-canonical crosswalk counts.
- Use `ingestion_quarantine` for ambiguous identity, malformed score labels, duplicate natural keys or rows with unsupported semantics.
- Require a fresh read-after-commit audit of response IDs, observation IDs, import-run counts and exact hashes.
- Keep all AI Midas observations `point_in_time_certifiable=false` until separate row-level temporal proof is supplied.

## 7. Release boundary

This contract does not authorize or perform:
- production writes;
- model training or model admission;
- changes to probabilities, predictions or publication decisions;
- value-betting activation;
- PR merge or deployment;
- Telegram delivery or schedule activation.

**Implementation status:** importer and independent read-after-commit verifier are implemented and executed successfully in isolated staging by workflow #43753939202. The source files are stored as immutable file-level evidence only; normalized match rows, fixture crosswalks, odds quotes, model admission and production writes remain out of scope. Next task is a separate read-only reconciliation of the six historical match archives against canonical fixture identities, followed by reviewer-backed resolution of the Brazil Série B 369/371 candidate mappings.
