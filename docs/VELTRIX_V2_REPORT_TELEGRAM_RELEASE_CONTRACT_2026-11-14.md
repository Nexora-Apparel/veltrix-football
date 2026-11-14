# VELTRIX V2 report and Telegram delivery contract — 2026-11-14

## Objective

The website, scheduled report and Telegram must consume the same immutable daily report. A successful model run, a successful artifact upload and a successful Telegram API call are separate events; none implies the others.

## Canonical report identity

Every V2 daily report uses schema `VELTRIX_V2_DAILY_REPORT_V1` and carries:
- `report_id`: stable identifier for the daily report revision.
- `as_of_date`: ISO calendar date in the report's declared timezone.
- `report_sha256`: SHA-256 of canonical UTF-8 JSON (sorted keys, compact separators, no NaN/Infinity), excluding the hash field itself.

Every consumer verifies the embedded hash. The website projection, scheduled report and Telegram formatter must reference the same report ID and hash. A same-day correction is a new report revision with a new ID/hash; the old report remains attributable.

## Telegram formatting boundary

The V2 formatter is separate from the legacy formatter and requires:
1. A valid V2 report identity.
2. `release_mode` of `RESTRICTED_PUBLIC` or `FULL_PUBLIC`.
3. An injected authoritative publication verifier to approve the exact report identity.
4. Per-fixture `publication_status=PUBLISHED`.
5. Explicit `certified_markets` for every probability market rendered.

Shadow, research, draft and uncertified forecasts are never rendered as public predictions. The V2 formatter does not render value-bet candidates; value-bet publication requires a separate certification and authorization path. Missing probabilities remain unavailable, never zero. A single fixture block that exceeds Telegram's limit is rejected rather than silently truncated.

## Website publication boundary

The V2 website loaders in `app/report_artifacts.py` require an injected authoritative publication verifier for V2 reports and dashboard projections. Without that verifier, V2 website data is rejected. A pure V2 certification gate now exists in `veltrix_v2/evaluation/publication_certification.py`; it binds the exact report ID/hash to an attested manifest, verifies the exact raw certification and rights evidence bytes, and checks per-market walk-forward, prospective sample, date coverage, odds coverage, ROI confidence bounds, 1X2 bookmaker baselines and injected rights verification. The verifier also requires explicit PIT certification, complete revision history, expanding chronological evaluation, prospective selections, net ROI after fees/slippage, date-clustered bootstrap confidence bounds, and a de-vigged 1X2 bookmaker baseline on the identical fixture set. No real manifest currently passes the gates, and the trusted attestation/rights/evidence callbacks are not wired into the website or Telegram runtime. Legacy report snapshots containing forecasts are no longer served as current website predictions; they remain archived. Legacy dashboard snapshots with no forecast rows may still provide non-prediction status information.

The local artifact builder writes separate canonical, scheduled, Telegram and website projection files. The persisted bundle reader and `scripts/veltrix_v2/verify_report_surface_bundle.py` verify the four surfaces against one report identity and reject missing or tampered files. `load_authorized_scheduled_report` returns the scheduled copy only after full bundle verification and publication authorization. `dispatch_public_telegram_bundle` verifies the complete bundle before formatting or claiming a delivery. The actual scheduled workflow still needs to consume the scheduled adapter, and the Telegram workflow still needs a certified verifier and authenticated durable store wired into its runner.

## Delivery idempotency and crash semantics

The idempotency key binds report ID, report hash and destination. A durable store must atomically claim that key before any Telegram network request.

The dispatch adapter is deliberately at-most-once:
- A previously claimed key is skipped.
- A successful send must persist Telegram message IDs.
- A timeout, transport exception, destination mismatch or receipt-persistence failure becomes `OUTCOME_UNKNOWN`.
- An unknown outcome is never automatically retried. It requires reconciliation against Telegram delivery evidence before a new attempt is considered.

Exactly-once delivery cannot be guaranteed across Telegram and our database because they do not share a transaction coordinator. A durable PostgreSQL implementation exists in `veltrix_v2/reporting/postgres_delivery_store.py`, backed by migration 0009 and concurrent-claim integration tests. Append-only operator reconciliation is implemented in migration 0010 and `veltrix_v2/reporting/reconciliation.py`; it verifies evidence bytes and binds events to the exact unknown claim. The latest tested reconciliation commit passed PostgreSQL 16/18 and foundation CI. Staging application, trusted operator/reviewer authentication, and evidence-reader provisioning remain required before live dispatch.

## Historical result and duplicate reconciliation

Prediction and settlement records remain append-only. A settlement must match the exact prediction fixture, canonical competition, home/away team identities and kickoff. The result source must supply source identity, result payload hash, retrieval/recording timestamps and independently verified rights for COLLECTION, STORAGE and BENCHMARKING.

Duplicate fixture IDs, duplicate settlements, conflicting scores, ambiguous fixture matches, or changed source payloads are quarantined/rejected; they must not overwrite prior evidence. A corrected result is represented as a new source observation/version and requires explicit reconciliation. No historical timestamp or result may be inferred to make a row eligible.

## Release phases

### Internal shadow
- Eligible real fixtures only.
- Forecasts remain non-publishable.
- No public Telegram messages, public website predictions or scheduled public report.

### Restricted prediction release
- Only certified markets and competitions.
- Every surface consumes the same report ID/hash.
- Value betting remains locked unless separately certified.
- Telegram delivery uses the durable idempotency store and verified publication authorization.

### Full launch
- Full certification gates passed.
- Website, scheduled report and Telegram parity verified.
- 06:00 WAT schedule enabled only after an explicit operational release review.
- Delivery monitoring and duplicate/reconciliation controls active.

## Validation matrix

| Area | Automated coverage | Still required |
|---|---|---|
| Report identity | Canonical hash, tamper rejection, exact website projection checks, immutable four-surface bundle, persisted bundle reader and verifier CLI | Connect scheduled workflow and Telegram runner to the bundle; wire the real certification verifier; schedule remains disabled |
| Telegram formatting | Release-mode gate, market allowlist, chunking, no truncation, legacy-sender block | End-to-end test against actual certified V2 report |
| Delivery | Atomic PostgreSQL claim, concurrent duplicate skip, terminal unknown outcome, append-only reconciliation and supersession | Apply migrations to staging; authenticate operators/reviewers and provision approved evidence reader |
| Results | Existing admission/settlement identity, rights and duplicate tests | Full prospective result reconciliation over captured real fixtures |
| Release | Shadow/public gate separation | Certification, operational sign-off and schedule activation |

No live Telegram delivery, schedule activation, staging migration, production migration or public prediction is authorized by this contract.


## Immutable bundle commit marker

The report bundle writer persists four immutable artifacts (canonical, scheduled, Telegram and website projection) and writes a final commit marker only after all four artifact files have been durably written. The marker binds the report ID/hash to the SHA-256 of each exact artifact byte stream.

Bundle readers require the marker, exact four-artifact inventory, matching artifact hashes and matching report identity before parsing/returning a bundle. Missing markers, missing artifacts, replaced artifacts, hash mismatch or report-identity mismatch fail closed. A crash before the final marker leaves the bundle unavailable to consumers; an identical retry can finish the missing artifacts and commit marker without overwriting existing content.

This is an atomic-visibility/commit protocol, not a claim that four separate filesystem paths are renamed as one filesystem transaction.


## Publication verifier market scope and recent-holdout gate

The public verifier permits only the supported report markets: `1X2`, `BTTS` and `TOTALS_2_5`. Value-bet certification is not accepted through this report-publication path and remains separately locked.

For 1X2, the certification manifest must beat the de-vigged bookmaker baseline on both Brier score and log loss on the full evaluation fixture set **and** the recent holdout fixture set. Each model/bookmaker comparison must carry the exact same fixture-set hash. Timestamped odds coverage must be within [0.98, 1.00], not merely greater than the minimum. Evidence objects are read through the injected evidence reader, byte-hashed and size-bounded; missing readers, missing evidence or mismatched hashes deny publication.


## Single-file cross-surface handoff

The bundle now also emits `bundles/{report_id}.bundle.json`: one portable envelope containing the canonical report, scheduled copy, Telegram copy and website projection, plus per-surface SHA-256 values and the common report identity. Its parser rejects missing surfaces, unknown schema, tampered surface bytes and report identity drift.

The final commit marker binds this portable artifact together with the four separate surface files. Consumers can transfer one portable file for cross-surface processing while the local bundle reader verifies the complete five-artifact set before returning a bundle. This does not itself publish the artifact or wire the production workflows.


## Portable bundle consumer adapters

- The scheduled-report adapter can return its scheduled projection from the single portable bundle only after the same injected authoritative verifier succeeds.
- The Telegram adapter can dispatch the Telegram projection from the single portable bundle only after bundle identity, all four surface hashes, public fixture status, unique fixture IDs and authoritative certification have passed.
- The Telegram adapter still claims durable idempotency before sending and has no automatic resend path for uncertain outcomes.
- These adapters are offline-testable and do not activate any production workflow.


## Website portable-bundle adapter

The website now exposes `load_v2_portable_report_bundle(bytes, verifier)`. It consumes the same portable bytes as the scheduled and Telegram adapters, returns all four projections plus report identity, and returns no data if bytes are malformed, the verifier is missing/denies, or bundle checks fail. The function is an integration adapter only; the production website fetch path and trusted verifier injection remain unwired pending release evidence and deployment authorization.


## Website portable artifact retrieval

The website report loader now checks `public-data/v2_report_bundle.json` on the configured command-data branch first, using one bounded raw GitHub fetch, an 8 MB response cap, a short cache and a bounded Contents API fallback. If a portable artifact is present but malformed or unauthorized, the loader returns no report and does not fall back to a legacy snapshot. If no portable artifact exists, the prior V2 report/dashboard pair remains subject to exact identity parity and the same verifier. The new fetch path is not live until a valid portable artifact is committed and the website deployment is authorized.


The website dashboard loader now checks the portable V2 artifact before any archived dashboard snapshot. When the portable artifact exists, an invalid or unauthorized bundle returns no dashboard and does not fall back to legacy content. This prevents an older legacy dashboard snapshot from masking or replacing the canonical V2 projection.
