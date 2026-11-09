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
