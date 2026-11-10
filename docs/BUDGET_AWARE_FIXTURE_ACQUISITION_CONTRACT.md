# Budget-Aware Fixture Acquisition Contract

Status: DESIGN BASELINE — read-only acquisition only. This document does not authorize production imports, model training, prediction publication, or provider-credit-consuming runs.

## 1. Objectives

Build a deterministic fixture acquisition layer that discovers real upcoming fixtures and retrieves historical results without exhausting provider quotas.

The layer must:
- Prefer verified 5DollarFootballAPI coverage for EPL, Ligue 1, Bundesliga, Serie A, and La Liga.
- Use StrikerAPI for additional competitions only when a request budget has been explicitly supplied and preflight-approved.
- Preserve provider provenance and retrieval-time evidence.
- Return fewer than 25 fixtures when fewer than 25 valid fixtures exist. Never fabricate or duplicate fixtures to reach a target.
- Keep provider retrieval separate from canonical database import.
- Fail closed on malformed, ambiguous, stale, or conflicting records.

## 2. Provider qualification boundaries

### 5DollarFootballAPI

Verified read-only coverage is limited to EPL, Ligue 1, Bundesliga, Serie A, and La Liga. The bounded historical dry run verified 488 finished results across those competitions for 2026-08-10 through 2026-11-08, with zero duplicate IDs and no missing team IDs. This is not a guarantee of future endpoint availability or complete season coverage.

### StrikerAPI

The provider catalogue documents 17 competitions, but live qualification is not complete. A four-competition bounded probe and the EPL cross-provider reconciliation passed. The 17-competition verifier tests pass, but its live run stopped with HTTP 402 before completing the checks.

Therefore:
- Do not mark all 17 competitions as live-qualified.
- Do not automatically run the 17-competition verifier.
- Do not infer available credits from HTTP 402.
- Require an operator-supplied remaining-credit figure and reset date before any credit-consuming run.
- Keep the full-coverage workflow manual-dispatch only.

## 3. Request-budget preflight

Every provider run must declare a budget before making a request.

Required fields: provider, documented account allowance, observed remaining credits/requests, reset timestamp and timezone if known, maximum calls, documented cost per call, retry reserve, permitted competition keys, and permitted date windows.

Preflight rules:
1. Reject the run if remaining credits are unknown for a credit-limited provider.
2. Reject if calculated maximum cost exceeds the operator-approved spend ceiling.
3. Reserve retry capacity before the first request.
4. Stop before the next request when the remaining budget cannot cover its documented cost.
5. Treat HTTP 402 as insufficient credits/billing restriction; do not retry automatically.
6. Treat HTTP 429 as rate limiting; use bounded backoff and count every retry against the call budget.
7. Treat HTTP 401 as an authentication failure; never print credentials.
8. Record planned and actual calls/credits in the run report.

The current StrikerAPI 17-competition verifier has a theoretical ceiling of 102 calls / 204 documented credits. This is a hard technical ceiling, not an approved spend target.

## 4. Acquisition stages

1. **Discover** — retrieve candidate fixtures from an allowed provider, competition, and window.
2. **Normalize** — convert provider rows into the provider-neutral record shape.
3. **Validate** — validate source ID, teams, competition, kickoff timezone, status, scores, and pagination.
4. **Deduplicate** — deduplicate within a provider using provider + competition + source ID.
5. **Reconcile** — optionally compare independent providers using exact competition mapping, approved team aliases, home/away orientation, and kickoff tolerance.
6. **Quarantine** — isolate conflicts and invalid records; never silently repair identity.
7. **Export** — emit a sanitized, immutable run artifact with provenance and quality counts.
8. **Import** — a separate future operation requiring explicit authorization. It is out of scope for this read-only stage.

No stage may write to Neon or mutate canonical fixture records.

## 5. Provider-neutral record contract

| Field | Requirement |
|---|---|
| provider | Stable provider identifier |
| source_id | Original provider fixture/game ID as a string |
| competition_key | Provider competition key |
| season | Season identifier when supplied; otherwise null |
| home_team_source_id / away_team_source_id | Provider team IDs as strings |
| home_team_name / away_team_name | Original provider display names |
| kickoff_at | ISO-8601 timestamp with explicit timezone |
| status | Original provider status plus normalized status |
| home_score / away_score | Integers for settled results; null otherwise |
| endpoint | Endpoint/tool name used |
| retrieved_at | UTC timestamp for this retrieval |
| payload_sha256 | SHA-256 of canonicalized source row |
| run_id | Stable ID shared by observations in one acquisition run |

Preserve original provider rows in run artifacts only to the extent permitted by current provider terms. Do not redistribute raw or bulk feeds. Keep normalized fields and hashes separate from raw payload storage.

## 6. Identity and quality rules

- Provider source identity is (provider, competition_key, source_id).
- Team identity is provider-scoped; names alone are not canonical team IDs.
- Cross-provider matching requires a verified competition mapping.
- Team aliases must be approved, season-scoped, competition-scoped, and evidence-backed.
- Home and away orientation must match.
- Kickoff timestamps must be timezone-aware and normalized to UTC.
- Kickoff tolerance may generate a candidate, but cannot override team or orientation conflicts.
- Duplicate source IDs, ambiguous candidate graphs, reversed orientation, status disagreement, and settled-score disagreement must be quarantined.
- Empty scheduled windows are valid observations and must be reported as empty, not filled with synthetic fixtures.
- Pagination truncation prevents a coverage claim for that check.
- Provider xG, odds, lineups, events, and Elo availability must each have independent coverage flags. Fixture availability does not imply metric availability.

## 7. Daily fixture discovery policy

The daily target is up to 25 eligible fixtures, not exactly 25.

Candidate selection must:
- use only competitions whose fixture endpoint has passed bounded qualification;
- include all eligible teams without favourite-only filtering;
- exclude duplicate canonical fixtures;
- retain fixtures with incomplete research as records, but mark missing research fields explicitly;
- never manufacture statistics, odds, lineups, xG, or fixtures;
- record why each candidate was included, excluded, or quarantined.

Acquisition success is not forecast approval. A separate publication gate must establish sufficient point-in-time evidence for every forecast.

## 8. Run report and audit fields

Every run report must include schema version and run ID; provider and competition scope; requested windows and actual retrieval timestamp; planned calls, actual calls, documented credit cost, and remaining approved budget; row counts by status and competition; valid, invalid, duplicate, unmatched, ambiguous, and quarantined counts; pagination completeness; payload-hash algorithm and normalized-record schema version; and explicit zero counts for database writes, imports, checkpoints, and canonical merges.

Reports must not contain API keys, authorization headers, or other secrets.

## 9. Required tests before implementation acceptance

- Budget preflight rejects unknown remaining StrikerAPI credits.
- Budget preflight rejects a run whose maximum cost exceeds its approved ceiling.
- Retries are included in actual call accounting.
- HTTP 402 stops immediately without retry.
- HTTP 429 retries are bounded and budgeted.
- HTTP 401 fails without leaking secrets.
- Provider + competition + source ID deduplicates deterministically.
- The same source ID in different competitions does not collide.
- Timezone normalization handles equivalent UTC offsets.
- Naive kickoff timestamps are rejected.
- Reversed home/away orientation is quarantined.
- Unapproved or out-of-scope aliases cannot match.
- Pagination continuation must advance; empty pages cannot claim continuation.
- Empty scheduled windows are reported without fabrication.
- Conflicting final scores are quarantined.
- The run report proves zero database writes and imports.

## 10. Current operational gates

- 5DollarFootballAPI: bounded read-only qualification PASS for five competitions.
- StrikerAPI four-competition verifier: bounded PASS.
- EPL cross-provider reconciliation: 100/100 unique matches in the inspected 90-day sample.
- StrikerAPI 17-competition live qualification: BLOCKED by HTTP 402; do not repeat before balance/reset confirmation.
- GOAL API: blocked at Cloudflare edge with HTTP 403; do not classify the key as invalid.
- Neon persistent foundation: migrated and reconciled; tables remain empty.
- Production imports: NOT AUTHORIZED.
- Prediction delivery: PAUSED.
- PR #42: remains open, draft, and unmerged.


## 11. Adapter implementation boundary

The adapter layer is implemented in `app/provider_acquisition_adapters.py`.

### 5DollarFootballAPI

- Uses the existing authenticated `FiveDollarFootballClient` transport through its `_get` method.
- Retrieves one explicit Africa/Lagos calendar day using UTC epoch boundaries.
- Reads original `data` rows and normalizes them immediately; raw provider rows are not copied into the emitted report.
- Requires complete pagination within the configured page cap. A page cap hit with `has_more=true` fails the run rather than presenting partial coverage as complete.
- Reports page fetches and the provider's remaining-request header when supplied. It does not mislabel page fetches as exact HTTP attempts.
- The existing client transport retains its bounded retry behavior internally; exact retry-attempt accounting is not exposed by that legacy transport and is explicitly marked as delegated in the report.

### StrikerAPI

- The adapter accepts the existing `list_games` transport as an injected callable.
- A validated `RequestBudgetLedger` is mandatory. Each page request is charged before the transport is invoked.
- The adapter does not retry. Any future retry must reserve and charge a separate attempt before transport.
- Pagination must advance and must finish within the configured page cap; incomplete scans fail closed.
- The 17-competition workflow remains manual-dispatch only. This adapter does not authorize or initiate it.

### Artifact and side-effect boundary

Both adapters feed the same normalization, batch validation, quarantine, and audit-report pipeline. Emitted reports contain normalized observations and payload hashes, not raw source payloads or credentials. Invalid-row quarantine entries retain only provider/source/competition/team identity hints and a payload hash; they do not retain the raw provider row. A genuinely empty competition window is a valid report with zero accepted and zero quarantined records. The adapters perform no database writes, imports, checkpoints, canonical merges, or prediction publications. Unit tests use injected fake transports and do not consume provider requests or credits.


## 12. Artifact integrity gate

- `app/provider_acquisition_artifact.py` independently validates the report schema, canonical SHA-256 report hash, accepted/quarantined/input counts, normalized-record field allowlist, payload-hash format, sanitized quarantine field allowlist, and zero-side-effect declarations.
- Duplicate quarantine entries contain only provider/source/competition/team identity hints and the source payload hash; they do not retain complete normalized rows.
- `scripts/verify_acquisition_artifact.py` provides an offline verifier suitable for CI or pre-import review.
- The manual 5Dollar workflow verifies the emitted JSON artifact before upload.
- Artifact integrity passing proves structural integrity and consistency only. It does not certify provider completeness, source correctness, model quality, betting value, or permission to import into production.


## 12. Daily fixture selection gate

The deterministic selector is implemented in `app/daily_fixture_selection.py`.

- Hard maximum: 25 selected fixtures per Africa/Lagos calendar date.
- Selection requires an explicit provider/competition allowlist supplied from verified qualification evidence. Provider catalogue documentation alone is not sufficient.
- Only normalized `scheduled` fixtures with timezone-aware future kickoffs on the requested Lagos date are eligible.
- Source identity must be present; duplicates within a provider/competition/source-ID scope are selected once.
- Results are ordered deterministically by kickoff, provider, competition, and source ID.
- No favourite-only filter is applied.
- No cross-provider fuzzy matching is attempted. Independent provider observations must pass the separate reconciliation stage before they can be treated as one canonical fixture.
- Empty eligible sets remain empty; no fixtures are fabricated to meet the 25-fixture maximum.
- Selection output is an in-memory read-only result and is not connected to production import or prediction publication.


## 13. Qualification evidence registry

Daily selection artifacts are built by `app/daily_fixture_selection_artifact.py`. A plain provider/competition allowlist is not sufficient for the production path. The registry must contain, for every qualified provider/competition pair:

- provider identifier and provider-scoped competition key;
- `qualification_status=qualified`;
- qualification run ID and evidence reference;
- SHA-256 of the qualification artifact;
- explicit pagination completeness;
- zero invalid rows and zero duplicate rows.

Duplicate registry entries, incomplete pagination, nonzero invalid/duplicate counts, missing evidence references, or malformed hashes fail closed. The selection artifact binds the source acquisition report hash and qualification registry hash to its own SHA-256. No default qualification entries are manufactured; the registry must be populated from actual inspected qualification evidence before a daily selection can run.


The repository includes `data/provider_qualification_registry.template.json` as an intentionally empty starter. It is explicitly marked as non-evidence and contains no qualified competitions. Until inspected provider artifacts are added as qualification entries, the daily selector returns zero eligible fixtures rather than assuming coverage.


## 6. Qualified 5Dollar historical batches

The signed qualification registry currently admits exactly five numeric competition IDs:
- Italy Serie A: `3405541143`
- France Ligue 1: `3614399544`
- England Premier League: `4160026622`
- Spain La Liga: `4212821298`
- Germany Bundesliga I: `686337048`

The historical batch adapter and CLI enforce this exact allowlist in addition to validating the HMAC-signed registry. A provider response containing a row from another competition fails the entire batch rather than being silently accepted.

### Batch contract
- One run covers one to seven inclusive Africa/Lagos calendar dates.
- The end date must be before the current Lagos date.
- The start date must fall within the documented 90-day results window.
- Only finished fixtures are requested.
- Maximum 20 HTTP attempts per run; default 15; minimum five calls to cover one page for each of the five competitions.
- Maximum three pages per competition; a `has_more` response at the page ceiling fails closed.
- Automatic HTTP retries are disabled for this adapter. Each HTTP attempt is reserved before dispatch and counted exactly.
- Requests are spaced at least 3.1 seconds apart to remain below the documented 20-request/minute burst ceiling; the offline artifact validator enforces a minimum 3.0-second interval.
- The manual workflow serializes dispatches and uses a persistent GitHub-branch ledger to reserve the requested ceiling before any provider call. Pending reservations count at their full ceiling; after the sanitized report passes integrity validation, the ledger settles to the actual request count and releases unused capacity. Failed/cancelled runs retain the full reservation until it ages out of the rolling 60-minute window. The ledger branch is `ops/fivedollar-request-hourly-ledger`; no production database is involved.
- Pagination must complete for all five competitions before an artifact is emitted.
- Rows are normalized, source-hashed, deduplicated by provider/competition/source ID, and quarantined when invalid.
- No raw provider payloads, credentials, database writes, imports, checkpoints, canonical merges or prediction publications are emitted.

### Execution
Use the manual workflow `.github/workflows/acquire-fivedollar-history-batch.yml` after its dispatch entrypoint is available on the default branch. Each run produces one sanitized `fivedollar-historical-batch` artifact with a SHA-256-protected report. Run adjacent, non-overlapping seven-day batches to cover the available 90-day window; do not assume an empty historical response proves coverage.

This workflow is manual-only. No provider request is made by CI tests or by pushing code. Historical artifacts must be reviewed and reconciled before any separate import authorization is considered.


## 7. Offline historical archive assembly

The CLI `scripts/assemble_fivedollar_history_archive.py` combines previously downloaded, individually validated batch reports. It performs no provider requests. It requires contiguous, non-overlapping inclusive date windows that exactly cover the requested one-to-90-day target period. Gaps, overlaps, duplicate provider/competition/source identities, invalid batch hashes, out-of-scope records, non-finished rows, and request/page accounting mismatches fail closed. The resulting archive records each source batch report hash, per-competition counts, aggregate request totals, and a canonical archive SHA-256. It remains an offline artifact; no Neon import is performed.


## 8. Historical coverage profiling (offline)

After individually validated batches have been assembled, run `scripts/profile_fivedollar_historical_coverage.py` against the archive. The profiler reports accepted finished matches by competition and month, active local calendar days, unique provider team IDs, team-name variants, duplicate match slots, score summaries, and unavailable research fields. It validates the archive hash and emits its own deterministic SHA-256 report.

Important distinction: complete pagination for the requested windows means all pages exposed by the provider were fetched. It does **not** prove that the provider's historical catalogue is complete, that all real-world matches are present, or that the sample is sufficient for model training. The report explicitly sets `ready_for_model_training=false`. Model work still requires independent source-completeness review, team/season continuity checks, point-in-time feature provenance, chronological partitions, and leakage audits.


## 9. Point-in-time pre-match feature contract

`app/point_in_time_feature_contract.py` defines an explicit pre-match feature catalogue and builds immutable feature snapshots bound to a fixture and `prediction_as_of` timestamp. Every feature must include its source, source ID, payload SHA-256, observation time, provider availability time, and retrieval time. All three times must be timezone-aware and no later than the prediction cutoff; availability cannot precede observation, retrieval cannot precede availability, and each feature must satisfy its maximum age. Odds are limited to a 15-minute age at the cutoff; lineup strength to six hours; historical team-strength features have longer bounded ages.

Target/result fields (scores, match result, BTTS/Over 2.5 outcomes and post-match metrics) are explicitly forbidden from the predictor catalogue. Feature snapshots keep target labels separate, enforce exact schemas, and are hashed. The validator repeats the temporal and provenance checks even if an attacker recomputes the hash. This is a leakage-prevention contract only: it does not certify model training or forecast quality.


## 10. Persistent rolling-hour quota ledger

`app/provider_hourly_quota_ledger.py` and `scripts/manage_fivedollar_hourly_quota.py` enforce the provider's 60-request rolling-hour allowance across workflow runs. The workflow reserves its maximum request ceiling and commits the reservation to a dedicated operational branch before making API calls. The workflow's concurrency group prevents simultaneous runs from racing the ledger. Once the report passes the historical artifact validator, the workflow settles the reservation to the report's actual request count. If a run fails after reservation or cannot safely settle, the full ceiling remains charged for one hour. The workflow must have `contents:write` solely to update this ledger branch; it does not write to Neon or canonical football data. A corrupted, missing, future-dated, duplicate, or policy-mismatched ledger fails closed.


## 11. Chronological labelled-dataset assembly

`app/chronological_training_dataset.py` joins one validated point-in-time feature snapshot to one separately sourced settled result using exact fixture IDs. It rejects duplicate or unmatched joins, invalid score labels, result retrieval before settlement, and any prediction cutoff at or after kickoff. It derives separate 1X2, BTTS, and Over 2.5 targets from settled scores.

The dataset partition policy is date-based in Africa/Lagos time, with strictly chronological train, validation and test windows and an explicit embargo gap between each. Rows in embargo/out-of-window dates are excluded. The output binds feature snapshot hashes and label provenance, reports class counts per market and split, and hashes the dataset manifest. The validator independently checks the date windows, chronology, target scope, counts, and zero-side-effect boundary. It always leaves `ready_for_model_training=false`; actual training requires the source and sample-size certification gates to pass.


## 12. Value-bet hard certification gate

`app/value_bet_certification.py` evaluates only settled out-of-sample walk-forward records and separately identified prospective selections. It hard-codes the release thresholds: at least 1,000 walk-forward matches per market; at least 300 prospective settled selections per market; at least 90 distinct Africa/Lagos kickoff dates among the prospective settled selections (backtest-only dates do not count); at least 98% timestamped pre-cutoff odds coverage; positive net ROI; and a positive lower 95% ROI confidence bound. ROI uncertainty uses a deterministic date-clustered percentile bootstrap (5,000 replicates), not an independent-bet bootstrap. For 1X2, model Brier score and log loss must both beat a de-vigged bookmaker baseline computed from timestamped decimal odds.

A certification summary binds the source evaluation-record digest and rechecks thresholds, counts, metrics and side-effect boundaries. A report claiming certification cannot be validated for enablement without the original source evaluation records being supplied for full recomputation. The gate itself performs no betting, database writes or publication. Value betting remains locked until real prospective evidence passes every market's checks.


## 13. New pre-match inference engine (not publication)

`app/pre_match_prediction_engine.py` implements a new Dixon-Coles-corrected independent-Poisson score model. It requires a validated point-in-time snapshot containing both teams' Elo ratings and rolling xG-for/xG-against features. Expected goal rates combine the geometric mean of attack and opponent concession xG with explicit fitted home-advantage and Elo coefficients. The low-score Dixon-Coles correction is applied to the 0-0, 0-1, 1-0 and 1-1 cells; the joint score matrix is normalized before deriving 1X2, BTTS and Over 2.5 probabilities.

The engine requires a digest-bound parameter set with a training dataset hash, data cutoff, latest training match, model training timestamp, calibration ID and bounded fitted parameters. Model training/data cutoffs later than the fixture's prediction cutoff are rejected. Missing required features, implausible xG/Elo values, excessive Poisson tail mass, or invalid Dixon-Coles corrections withhold the forecast. No global prior, home-default probability, favourite-only filter or fabricated statistic is used. Every inference output is marked `publication_allowed=false` and `value_betting_enabled=false`; actual parameter fitting, walk-forward calibration and publication certification remain separate unfinished stages.


## 14. Restricted source-evidence sidecars and mapping verification

The acquisition batch now retains a `source_evidence` sidecar on every accepted normalized fixture record. This sidecar is restricted to private/internal acquisition artifacts and must not be published, exposed through the public website, or redistributed as a raw/bulk provider feed.

Each sidecar binds:
- evidence schema version and provider-specific normalization mapping version;
- provider, endpoint, source ID, acquisition run ID and retrieval timestamp;
- the original raw provider row and its canonical SHA-256;
- the complete normalized record projection and its canonical SHA-256.

The offline artifact validator recomputes the raw digest, normalized projection digest, and provider-specific normalization output. It rejects unknown mapping versions, altered raw payloads, changed normalized fields, mismatched metadata, or a record not exactly bound to its sidecar. Current mapping IDs are `strikerapi.list_games.normalization.v1` and `fivedollar.fixtures.normalization.v1`.

The evidence sidecar proves integrity and repeatability of the current versioned mapping implementation; it is not a cryptographic signature from the provider and does not independently prove that the provider's original data is true. Any mapping change requires a new version identifier and regression tests. Raw payload retention is subject to the provider's storage and licensing terms; the sidecar must remain in access-restricted, non-public artifacts only.

The pipeline remains read-only: no production imports, Neon writes, canonical merges, prediction publications, Telegram deliveries or schedule changes are introduced by evidence retention.


## 15. Provider settlement-time evidence and dataset admission

The provider payload schemas were inspected against the current official endpoint documentation:

- StrikerAPI `list_games` documents `game_id`, `date`, `starts_at`, `status`, `status_detail`, and score/team fields. Its documented match-event records expose sequence, minute, added minute, period and event type; they do not document a wall-clock full-time timestamp.
- 5Dollar fixture records document `status`, `status_code`, `kickoff_utc`, `kickoff_ts` and goals. The API explains that `status=finished` / `status_code=full` means the feed has sent the full-time mark. Its event timeline exposes event type and match minute/period score, not a wall-clock full-time timestamp. Odds tick `recorded_at` is a quote timestamp, not a settlement timestamp and must never be repurposed.

Reference schemas:
- https://strikerapi.com/docs/list-games
- https://strikerapi.com/docs/get-events
- https://5dollarfootballapi.com/docs
- https://5dollarfootballapi.com/docs/fixture

Versioned extractors:
- `strikerapi.list_games.settlement-time.v1`
- `fivedollar.fixtures.settlement-time.v1`

The extractors preserve terminal-status evidence separately from settlement time. Current documented schemas confirm terminal state but do not supply a settlement wall-clock time; therefore `settled_at` remains null and `settlement_time_available=false`. Retrieval time, kickoff plus assumed duration, event minute, odds tick time and processing time are explicitly prohibited as substitutes.

The evidence sidecar binds the settlement extraction result to the exact raw payload and normalized record. Tampering or a mapping mismatch fails validation. The acquisition-to-dataset bridge independently validates raw payload evidence and settlement evidence, then rejects records without a verified settlement timestamp using `settlement_timestamp_unavailable`. It does not create feature-history rows or labels from terminal status alone.

The chronological dataset bridge is implemented, including a source-evidence manifest and digest. It is intentionally unable to admit the currently documented provider records until a provider supplies an explicit settlement timestamp or a separately qualified timestamp source is added with its own provenance, mapping version and point-in-time validation. This is a data-availability blocker, not a reason to weaken the temporal contract.
