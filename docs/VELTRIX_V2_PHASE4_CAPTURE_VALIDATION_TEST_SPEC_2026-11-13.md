# VELTRIX FOOTBALL 2.0 — Capture Validation & Leakage Test Specification

**Assessment date:** 2026-11-13  
**Branch:** `phase4/provider-qualification-20261113`  
**Status:** Test design only — no executable pipeline, migration or production ingestion is authorized  
**Depends on:** `VELTRIX_V2_PHASE4_POINT_IN_TIME_CAPTURE_CONTRACT_2026-11-13.md`

## 1. Purpose and acceptance boundary

This specification defines the test evidence required before a provider capture implementation can be accepted as a trustworthy source of pre-match features.

The tests must establish:
- byte-level provenance from provider response to selected feature;
- strict separation of source publication time, event time, retrieval time and prediction cutoff;
- immutable handling of corrections and deletions;
- deterministic, auditable entity resolution;
- rights enforcement at collection and downstream-use time;
- no post-cutoff information leakage;
- explicit accounting for missingness and odds coverage;
- reproducible feature snapshots.

Passing these tests validates pipeline integrity only. It does not validate predictive performance, provider completeness, commercial rights beyond the documented scope, or value-bet profitability.

## 2. Test layers

| Layer | Test target | Required evidence |
|---|---|---|
| Unit | Timestamp parsing, canonicalization, hash calculation, eligibility rules, reason codes | Deterministic test results and edge-case coverage |
| Contract | Provider endpoint adapters and schema versions | Recorded fixtures from redacted raw responses; unexpected fields/nulls handled safely |
| Integration | Request → raw archive → parsed observations → crosswalk → eligibility | End-to-end trace IDs and referential-integrity report |
| Database | Append-only constraints, uniqueness, transaction boundaries, rights revocation | Constraint tests and rollback/replay evidence |
| Temporal | As-of selection, revisions, cutoff boundaries, chronological folds | Adversarial synthetic timelines and zero-leakage assertions |
| Security | Secret redaction, rights scope, endpoint allowlists, quota limits | Redacted logs, policy-denial tests and bounded-request report |
| Reproducibility | Re-run same evidence and feature spec | Identical selected observation IDs and feature-set hash |

## 3. Deterministic temporal test fixtures

Use a fixed synthetic fixture kickoff at `2026-11-20T18:00:00Z` and a frozen prediction cutoff at `2026-11-20T12:00:00Z`. These are test-only timestamps, not real fixtures.

| Case | Observation timeline | Expected result |
|---|---|---|
| T01 — published before cutoff | Published 10:00Z, retrieved 10:02Z | Eligible if rights, identity and raw evidence pass |
| T02 — exactly at cutoff | Published exactly 12:00:00Z | Eligible only if cutoff semantics explicitly use inclusive `<=`; contract uses inclusive |
| T03 — one unit after cutoff | Published 12:00:00.001Z | Reject: `PUBLISHED_AFTER_CUTOFF` |
| T04 — published after cutoff, retrieved before kickoff | Published 12:05Z, retrieved 12:06Z | Reject; being pre-kickoff is not enough |
| T05 — retrieved after cutoff, no archive timestamp | Published NULL, retrieved 12:10Z | Reject: `SOURCE_TIMESTAMP_MISSING` |
| T06 — historical archive retrieved later | Archive snapshot explicitly timestamped 11:00Z, retrieved next day, immutable archive proof exists | Eligible only if archive timestamp semantics and rights are independently verified |
| T07 — event time before cutoff, publication after | Injury event 09:00Z, provider publishes 13:00Z | Reject; event time does not prove availability |
| T08 — source effective time before cutoff, publication unknown | Effective 08:00Z, published NULL | Reject: `SOURCE_TIMESTAMP_MISSING` |
| T09 — future event timestamp | Source says value effective 13:00Z, cutoff 12:00Z | Reject unless field semantics explicitly define a forecast legitimately published before cutoff; preserve forecast type |
| T10 — date-only timestamp | Source gives `2026-11-20` only | Reject for cutoff eligibility; do not assume midnight |
| T11 — timezone offset | `2026-11-20T13:00:00+01:00` | Normalize to 12:00Z while preserving original string; inclusive cutoff boundary |
| T12 — invalid/ambiguous timezone | Naive local timestamp without zone | Reject as untrusted for cutoff comparison |
| T13 — later correction | v1 published 10:00Z; v2 correction published 14:00Z | Cutoff 12:00Z selects v1; later cutoff may select v2 |
| T14 — correction before cutoff | v1 published 10:00Z; v2 published 11:30Z and supersedes v1 | Cutoff 12:00Z selects v2 |
| T15 — missing revision lineage | New version arrives but does not identify revision/supersession and provider semantics unclear | Quarantine: `REVISION_HISTORY_INCOMPLETE` |
| T16 — post-match statistic | Shots/xG event aggregate calculated at 20:00Z after kickoff | Not eligible for 12:00Z pre-match features |
| T17 — source timestamp differs from retrieval | Published 10:00Z, retrieved 11:00Z | Retain both values; eligibility uses proven source availability, not retrieval as substitute |
| T18 — cutoff changed after prediction | Original cutoff 12:00Z later edited to 13:00Z | Database rejects mutation; create a new prediction snapshot if a new cutoff is intended |

All tests must also run across daylight-saving transitions in source timezone examples, leap days, fractional-second precision, and dates around UTC midnight. WAT is UTC+1 and does not observe daylight-saving time; store resolved UTC cutoffs and retain the original WAT schedule metadata.

## 4. Raw provenance and integrity tests

| ID | Test | Pass condition |
|---|---|---|
| P01 | Hash original response bytes | SHA-256 matches independently recomputed digest |
| P02 | Whitespace/key-order variation | Different raw bytes produce different raw hashes even if parsed JSON is semantically equivalent |
| P03 | Parsed payload linkage | Every observation resolves to exactly one request and raw payload |
| P04 | Missing raw bytes/object | Observation fails closed with `RAW_EVIDENCE_MISSING` |
| P05 | Truncated or corrupt response | Parser rejects/quarantines; no partial feature silently accepted |
| P06 | Duplicate fetch | Each request is retained; content-addressed identical bytes may share blob without collapsing request records |
| P07 | Secret scan | No API key, bearer token, password, signed query or authorization header in logs/artifacts |
| P08 | Request fingerprint | Same canonical redacted request yields same fingerprint; secret changes do not enter persisted fingerprint |
| P09 | Manifest tamper | Any changed response hash, observation list or rights evidence invalidates manifest verification |
| P10 | Response content type | Unexpected content type is rejected or quarantined, not parsed as trusted JSON by assumption |

Test byte hashes over the exact HTTP response entity bytes at the defined capture boundary. Document whether transport decompression occurs before storage; the boundary must remain consistent and explicit.

## 5. Entity-resolution tests

- Exact provider ID with an approved crosswalk resolves to one canonical entity.
- Same display name but different provider IDs does not automatically merge entities.
- Men's, women's, youth, reserve and senior teams remain distinct unless an evidence-backed mapping explicitly links them.
- Renamed club preserves historical mapping versions; old IDs are not overwritten.
- Merged, dissolved or reactivated clubs require a reviewed crosswalk event.
- Duplicate fixture candidates with conflicting kickoff, competition or participants are quarantined.
- Home/away order reversal is detected and never silently normalized without provider-specific semantics.
- Provider ID reuse across seasons or competitions is detected.
- Crosswalk updates do not rewrite the mapping used by an already frozen prediction.
- Every accepted mapping has provenance, mapping method, reviewer/status and recorded timestamp.

Required metric: deterministic fixture join rate and team join rate, each with numerator, denominator and quarantined/ambiguous counts. Never hide unresolved rows by dropping them before computing coverage.

## 6. Rights and access-control tests

- No request is issued for a provider/endpoint outside the active allowlist.
- No collection begins without active collection rights.
- No retention write occurs without retention rights.
- No feature selection for training occurs without model-training rights.
- No public display path uses a source without display/attribution rights.
- Revoking/suspending approval blocks subsequent requests and downstream selection.
- A revoked approval does not erase historical audit evidence; it changes permitted future use.
- Expired terms/approval blocks new ingestion until renewed evidence is recorded.
- Rights scoped to one competition/season cannot authorize another.
- Provider documentation alone cannot satisfy a contract/terms approval requirement.
- Test logs must show a reason code without disclosing confidential contract text or secrets.

A rights denial must be a hard failure, not a warning or fallback to another unapproved source.

## 7. Odds-specific integrity and coverage tests

Test every odds row as an event × bookmaker × market × selection × line × snapshot observation.

- Quote time, provider update time, VELTRIX retrieval time and kickoff time remain distinct.
- Suspended/unavailable market is represented explicitly, not as a missing price or zero.
- Decimal odds must be finite and greater than 1.0 for active conventional selections; malformed values are quarantined.
- Handicap/total line and market period are part of the market identity.
- Home/draw/away selection mapping is verified against canonical fixture participants.
- Bookmaker identity and jurisdiction/region are retained.
- Duplicate identical quote snapshots are idempotent; changed price creates a new version.
- Closing odds cannot be used in a prediction snapshot whose cutoff precedes closing.
- Snapshot cadence is not treated as proof that a quote existed continuously between snapshots.
- Missing quote, missing timestamp, unsupported market and provider outage are separately counted.

Coverage report must publish:
- eligible fixture count;
- expected bookmaker × market observations;
- quote observations received;
- observations with trustworthy timestamps;
- missing quote count;
- missing timestamp count;
- unsupported-market count;
- event/bookmaker mapping failures;
- numerator and denominator for timestamp coverage.

The certification denominator is frozen before evaluating provider response completeness. Provider outages and missing markets remain in the denominator unless the evaluation protocol explicitly excludes them before the period begins.

## 8. As-of selector reference behavior

The production selector must be implemented as deterministic application/database logic and tested against a simple independent reference implementation.

For a given canonical entity, field and cutoff:
1. Restrict to active rights scope.
2. Restrict to exact approved provider/product/endpoint/competition/season.
3. Require valid entity mapping and complete raw provenance.
4. Require trusted source availability timestamp `<= cutoff`.
5. Exclude observations superseded by another version that was itself available by cutoff.
6. Apply field-specific semantic constraints.
7. Select the latest eligible source version under a documented deterministic tie-break rule.
8. Return selected observation ID, value, source timestamp, retrieval timestamp, revision ID, raw hash and eligibility explanation.
9. If no eligible observation remains, return missing with explicit reason; never substitute an unverified fallback.

Tie-break rules must be stable across database query plans and replay. Do not use insertion order or random IDs as implicit recency.

Property-based temporal invariants:
- Adding an observation published after cutoff cannot change the selected value for that cutoff.
- Adding a correction published after cutoff cannot change the selected value for that cutoff.
- Adding an eligible correction before cutoff may change the selected value only for cutoffs at or after its publication time.
- Moving the cutoff earlier cannot introduce a later-published observation.
- Replaying identical raw evidence cannot change selected observation IDs or feature-set hash.
- Revoking rights makes the affected observation ineligible for new downstream use.
- A missing source timestamp never becomes eligible because retrieval occurred before kickoff.

## 9. Walk-forward leakage audit

For each chronological fold:
- Freeze training, validation and test date boundaries before querying features.
- Define a prediction cutoff for each test fixture.
- Build every feature row using only observations available by that fixture's cutoff.
- Ensure training labels settle before the training cutoff specified by the protocol.
- Keep all versions of one fixture in the same fold.
- Prevent duplicate fixtures or rescheduled versions crossing folds.
- Fit scalers, imputers, feature selectors and calibration only on the training portion of each fold.
- Do not use random train/test splitting.
- Re-run the fold from raw evidence and compare feature-set hashes.

Leakage audit output must include:
- fold ID and time boundaries;
- fixture IDs and prediction cutoffs;
- selected observation IDs;
- maximum selected source publication timestamp per fixture;
- post-cutoff selected count (must be zero);
- unknown-timestamp selected count (must be zero);
- missingness and quarantine rates;
- feature-set manifest hash;
- code commit, dependency lock hash and schema version.

A single post-cutoff or unknown-timestamp selected feature fails the entire fold. No average leakage tolerance is allowed.

## 10. CI gates and required artifacts

A future implementation PR must attach:
1. Unit/contract/integration/database test summary.
2. Synthetic temporal adversarial test output.
3. Raw-response provenance audit.
4. Secret-scan report.
5. Rights-scope denial test output.
6. Entity mapping coverage and quarantine report.
7. Odds timestamp coverage report, with fixed denominator.
8. As-of selector property-test summary.
9. Chronological fold leakage audit.
10. Reproducibility report with repeated-run hashes.

Suggested CI gates:
- All deterministic tests pass.
- No unresolved critical/high security findings.
- Zero post-cutoff feature selections.
- Zero unknown-publication-time feature selections.
- Zero raw-evidence linkage failures.
- Zero rights-scope bypasses.
- No unresolved entity ambiguity in selected features.
- No secrets in logs or artifacts.
- Coverage metrics are reported honestly; low coverage blocks the feature family rather than being concealed.

## 11. Failure handling

- Provider timeout/rate-limit: record failed request and retry metadata; bounded retries only.
- Schema drift: quarantine unknown/changed fields and stop the affected adapter; do not silently coerce.
- Missing timestamp: retain evidence but mark ineligible.
- Identity conflict: quarantine and require reviewed mapping.
- Rights expiry/revocation: stop affected collection/use immediately.
- Hash mismatch: stop pipeline and preserve forensic evidence.
- Database transaction failure: roll back the affected unit; never mark checkpoint complete.
- Partial capture: publish a manifest with explicit incompleteness; do not advance a complete watermark.
- Any leakage-test failure: block merge/release of the capture implementation.

## 12. Explicit non-goals

This specification does not approve a provider, endpoint, competition or commercial use. It does not implement the pipeline, create database migrations, request paid credits, train a model, change production data, publish predictions, enable Telegram, resume scheduling or unlock value betting.

Implementation is a separate task after Phase 4 provider qualification identifies exact approved endpoints and rights. Before implementation, inspect the existing Phase 3 staging schema and design additive migrations only; do not alter or rerun the clean-database-only staging importer.
