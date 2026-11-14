# VELTRIX FOOTBALL 2.0 — Release readiness and hard blockers

**Snapshot:** 2026-11-14  
**Release posture:** Internal engineering only. Public prediction, Telegram delivery, and the 06:00 WAT schedule remain disabled.

## Verified data position

The dedicated Neon staging database contains 2,496 imported fixtures and 2,496 linked result observations across seven competitions. The latest read-only audit found:

- 0/2,496 observations with verified recorded_at.
- 0/2,496 with verified source_published_at.
- 0/2,496 point-in-time-certifiable observations.
- 0 linked capture manifests and 0 item evidence hashes.
- 0 observations with explicit, time-evaluated rights approval evidence.

Existing historical timestamps and availability proxies must not be promoted to source publication or result-availability evidence.

Additional datasets:
- OpenFootball Nigeria 2025/26 archive: 379 accepted ordinary results, date-only kickoff precision; not PIT-certifiable.
- 5DollarFootballAPI snapshot: 100 EPL finished fixtures retrieved; 91 retained under a conservative availability proxy; not PIT-certifiable.
- GOAL API and StrikerAPI credits are exhausted until next monthly reset. No calls, tests, credit checks, retries, or top-ups before reset.
- The Odds API remains optional and locked behind its account, terms, rights, and spend evidence.

## Model and certification position

The new Poisson, Elo, team-form, challenger comparison, calibration and chronological evaluation components are software foundations. They are not evidence that any model or market is certified.

The pure publication verifier additionally requires expanding chronological walk-forward evidence, explicit PIT certification and complete revision history, prospective selection evidence, net ROI after fees/slippage, date-clustered bootstrap confidence bounds, model/feature artifact hashes, exact evidence-byte hashes, and a de-vigged bookmaker baseline evaluated on the identical 1X2 fixture set. The publication and value-bet gates remain:

- At least 1,000 chronological walk-forward matches per market.
- At least 300 prospective settled selections.
- At least 90 distinct prospective dates.
- At least 98% timestamped pre-kickoff odds coverage.
- Net ROI above zero and date-clustered 95% lower ROI confidence bound above zero.
- 1X2 must beat the de-vigged bookmaker baseline on Brier score and log loss over identical eligible fixtures.
- Value betting stays locked until its own certification passes.

The 90-date and 300-settlement requirements cannot be completed by compressing software work into a 30-minute window.

## Delivery engineering

PR #118 contains:
- Canonical report identity and hash verification.
- Website projection content-parity checks.
- Immutable canonical, scheduled, Telegram and website artifact bundle with a final commit marker binding all four surface files plus one portable bundle file; interrupted writes remain invisible to readers until the marker is committed.
- A single portable bundle file contains all four surfaces with per-surface hashes; website, scheduled-report and Telegram adapters can consume those same bytes with the authoritative verifier.
- The website fetches `public-data/v2_report_bundle.json` first, with an 8 MB cap and a repo/branch-scoped 30-second cache; an invalid present artifact blocks fallback to legacy snapshots.
- Website V2 loader rejects empty reports, duplicate fixture IDs, more than 25 fixtures, and verifier exceptions.
- Read-back bundle verifier and offline CLI.
- Authorization-gated scheduled report consumer.
- Telegram dispatch adapter that verifies the entire bundle and publication authorization before claiming a delivery.
- Durable at-most-once PostgreSQL delivery claims.
- Append-only OUTCOME_UNKNOWN reconciliation evidence, migration 0010, evidence-byte hashing, two-person review for confirmed non-delivery, and supersession.
- Legacy sender guard and V2 regression tests.
- Website loaders that fail closed without an authoritative verifier and no longer serve legacy forecast snapshots as current V2 predictions.

Latest fully validated code checkpoint at this snapshot: commit `b063979c16e6bf2f982a56cc4d06c7b3b5c1a7ee`, CI run #1379 passed Foundation, PostgreSQL 16 and PostgreSQL 18. CI run #1381 passed the follow-up portable-bundle verifier workflow integration.

## Hard release blockers

1. **Certification evidence and wiring:** a pure V2 publication verifier now checks exact report identity, attested certification-manifest bytes, per-market thresholds, exact raw evidence bytes, rights evidence bytes and injected source-rights approval. No real certification manifest currently passes the gates, and the trusted attestation/rights callbacks are not yet wired into the website or Telegram runtime.
2. **Surface wiring:** the actual scheduled workflow and Telegram runner do not yet consume the same generated V2 artifact. The legacy dashboard snapshot refresh has now been explicitly paused with an `if: false` job guard because it republishes a legacy report projection. The new bundle adapters are not a substitute for wiring the real V2 workflows.
3. **Staging schema:** migrations 0005–0010 have not been applied to Neon staging. The manual-only staging guard must be reviewed and run only against the dedicated staging database.
4. **Operator controls:** authenticated operator/reviewer identity and approved durable evidence-reader provisioning are not connected to the reconciliation writer.
5. **Prospective evidence:** the required 90 dates and 300 settled selections must accrue from real eligible forecasts and verified results.
6. **Provider rights:** the 5Dollar source's missing BENCHMARKING approval must be resolved before using it for settlement benchmarking.
7. **Operations:** Vercel quota restrictions remain; no manual deployment attempts. The 06:00 WAT schedule and Telegram delivery remain inactive.

## Required execution order

1. Finish PR #118 CI and code review; keep it draft until validated. A static regression test now asserts that the legacy daily prediction, dashboard refresh and Telegram recovery jobs remain paused until V2 wiring is complete.
2. Connect the authoritative V2 certification verifier to the website, scheduled and Telegram consumers.
3. Complete authenticated operator/reviewer identity and evidence storage.
4. Wire the real scheduler, dashboard refresh and Telegram runner to the same immutable bundle, while keeping all production triggers disabled.
5. Review migrations 0005–0010, apply only to dedicated staging under the guard, and perform read-only post-migration audits.
6. Run internal shadow capture using only genuinely eligible evidence.
7. Accrue prospective dates and settled selections; evaluate each market and competition independently.
8. Authorize restricted release only for certified markets/competitions.
9. Enable the 06:00 WAT schedule and Telegram only after separate operational sign-off.

## Prohibited shortcuts

- No synthetic or imputed timestamps, results, probabilities, odds, rights approvals or provider credits.
- No legacy prediction models, priors, feature logic, or fallback forecasts.
- No public release based on CI fixtures or exploratory backtests.
- No production database writes/migrations, Telegram sends, schedule activation, or Vercel deployment attempts while the corresponding gates remain closed.


## Latest CI update — 2026-11-14 14:44 UTC

- PR #118 branch head: `7c605fc38b9a8e4c5742878ac461a42b9d5f62b7`.
- GitHub Actions run #1318 passed Foundation, PostgreSQL 16 and PostgreSQL 18.
- Legacy daily predictions, dashboard snapshot publication and Telegram recovery remain paused and are covered by regression checks.
- The publication verifier and artifact bundle remain fail-closed; no real certification manifest is currently eligible.
- PR #118 remains draft/open/unmerged. No staging migration, production write, provider request, Telegram send, schedule activation or manual Vercel deployment was performed.


## Additional certification hardening — 2026-11-14 14:56 UTC

- Public market whitelist is limited to `1X2`, `BTTS` and `TOTALS_2_5`; value betting cannot be authorized by this verifier.
- 1X2 must beat the de-vigged bookmaker on both Brier and log loss for the full and recent holdout sets, with exact fixture-set hashes matched in each comparison.
- Timestamped odds coverage is constrained to 98%–100%.
- Publication reports are limited to 1–25 unique fixture IDs.
- Certification and rights evidence objects are byte-hashed and size-bounded.
- Telegram reconciliation evidence is size-bounded; the reconciliation path still has no send/retry capability.
- CI run #1344 passed Foundation, PostgreSQL 16 and PostgreSQL 18 for commit `01504bc0233864eb8c028e487837a41d0d3ca48e`.


## Latest cross-surface bundle validation — 2026-11-14 15:03 UTC

- Portable one-file report envelope and strict duplicate-JSON-key rejection implemented.
- Portable parser verifies exact canonical/scheduled/Telegram/website surface hashes and common report identity.
- Scheduled consumer, website adapter and Telegram dispatch adapter accept the same portable bytes only after authorization.
- Public bundle consumers independently enforce 1–25 unique fixture IDs and PUBLISHED status.
- Telegram portable dispatch preserves durable idempotency and uncertain-outcome quarantine; no automatic retry or resend.
- GitHub Actions run #1366 passed Foundation, PostgreSQL 16 and PostgreSQL 18 for code commit `cdd3c36216e595fa390f41009038b2ded5bc3d83`.
- Run #1367 passed the documentation-only follow-up.
- Production workflows remain disabled and are not yet wired to fetch the portable bundle.


## Website retrieval and offline verifier update — 2026-11-14 15:08 UTC

- Website report and dashboard loaders now prefer the portable V2 bundle over legacy snapshots.
- If the portable file exists but is malformed or unauthorized, the website returns no report/dashboard and does not fall back to legacy forecast content.
- Fetch is bounded to 8 MB, cached for 30 seconds by repository/branch, with bounded raw-content and Contents API requests.
- Added offline portable bundle verification CLI and CI coverage; structural verification does not authorize publication.
- GitHub Actions run #1381 passed Foundation, PostgreSQL 16 and PostgreSQL 18.
- API call sites still do not have a trusted runtime certification/rights verifier. Until that is configured, website V2 forecasts remain hidden by design.


## Legacy and exhausted-provider workflow containment — 2026-11-14 15:10 UTC

- Paused `paper-tracking-recovery.yml`: it consumed the legacy published report, rebuilt the legacy value screen, re-evaluated old paper predictions and republished legacy command data.
- Paused `verify-goal-api.yml` and `verify-strikerapi.yml` jobs until the next monthly credit reset. Neither provider has been probed, called, or credit-checked.
- Added regression guards for all three workflow pauses.
- Existing legacy daily prediction, dashboard refresh, Telegram recovery and daily-report watchdog jobs remain paused.
- These changes do not affect offline provider adapters, model tests, staging read-only audits or free-source qualification.


Additional legacy containment: paused `historical-model-reconstruction.yml`, which replayed archived forecasts through the excluded legacy model audit stack. CI now asserts this workflow remains disabled. Historical source archives remain preserved; only the legacy reconstruction workflow is paused.


Regression coverage also asserts that the legacy daily-report watchdog and legacy historical backtest jobs remain disabled. This prevents a workflow_dispatch or code push from reviving old report/model pipelines during the V2 rebuild.


## Latest workflow safety validation — 2026-11-14 15:13 UTC

- Paused legacy paper-tracking recovery, legacy historical model reconstruction, GOAL API probe and StrikerAPI probe jobs.
- Regression tests also assert the daily-report watchdog, historical model backtest, women's historical backtest, daily predictions, dashboard snapshot publisher and Telegram recovery remain disabled.
- GitHub Actions run #1392 passed Foundation, PostgreSQL 16 and PostgreSQL 18 at commit `edc63ee60b619306d5b7687842168ff62b6f8ef9`.
- No GOAL API, StrikerAPI, 5Dollar provider request, database migration/write, Telegram send, schedule activation or deployment was performed.


## Cross-surface adapter integration — 2026-11-14 15:15 UTC

- Added one integration test that feeds the identical portable bundle bytes into the website loader, scheduled-report adapter and Telegram dispatcher.
- Test verifies the same report ID/hash and identical projections across the three adapters, then verifies one durable claim and one stubbed Telegram message.
- GitHub Actions run #1396 passed Foundation, PostgreSQL 16 and PostgreSQL 18.
- This is adapter-level parity, not production workflow parity. Actual GitHub Actions scheduler and Telegram delivery jobs remain disabled/unwired.


## API surface safety

The FastAPI command centre exposes a server-side publication-verifier injection point and passes its configured value into report/dashboard and Telegram command loaders. No production bootstrap currently installs a verifier, so the dashboard returns `UNAVAILABLE` and no V2 predictions. A trusted attestation and rights-verification implementation still has to be provisioned and wired at startup. Legacy paper-ledger and model-validation snapshots are no longer loaded into V2 dashboard or Telegram command responses. CI covers the no-verifier fail-closed path.


## Legacy dashboard fallback removal — 2026-11-14 15:22 UTC

A final website audit found that the browser still had independent raw-GitHub/CDN fallbacks to legacy `dashboard_snapshot.json` and `paper_tracking_ledger.json`, plus legacy `EXPERIMENTAL_*` state handling. These paths could bypass the new API verifier. They have been removed. The browser now uses only `/api/dashboard-data`; if the trusted V2 verifier or portable report is unavailable, the dashboard displays an unavailable state rather than legacy forecasts or paper history. Legacy experimental labels and static fallback references are covered by regression tests.


## CI checkpoint — 2026-11-14 17:34 UTC

- Current branch head: `c69c83337a3b32c0e069b6ab72e518fbd7fe4908`.
- CI run #1445 (`43621787204`) passed Foundation, PostgreSQL 16 and PostgreSQL 18.
- The previous #1441 foundation failure was isolated to the dashboard JavaScript extraction check: its regex did not reliably identify the embedded HTML assignment. The check now parses `api/telegram.py` with Python's AST, extracts the literal `DASHBOARD_HTML`, and runs `node --check` on the embedded script.
- This is a CI-check correction, not a change to publication eligibility or launch status.


## CI checkpoint — 2026-11-14 17:35 UTC

- Code head `c69c83337a3b32c0e069b6ab72e518fbd7fe4908`: CI run #1445 passed Foundation, PostgreSQL 16 and PostgreSQL 18.
- Documentation update head is `d6c7f3161f3227c5107b27a6b694dfb2c8e78307`; CI run #1446 was queued at the time of this update.
- PR #118 remains open/draft, mergeable, and unmerged. No migrations, production writes, provider requests, Telegram sends, schedule activation or deployment occurred.


## V2 Telegram command isolation — 2026-11-14 17:43 UTC

- The Telegram webhook now imports and calls `veltrix_v2.reporting.telegram_commands.handle_v2_command`; it no longer imports or calls the legacy `app.telegram_commands.handle_command`.
- The V2 command renderer re-verifies the report through the same authoritative verifier used by the public Telegram formatter.
- `/1x2`, `/btts` and `/overunder` render only their explicitly certified V2 probability vectors. `/match` renders only certified markets. Fixture IDs must be unique and the report is limited to 25 fixtures.
- Legacy `status`, `probabilities`, `expected_goals` and `value_bet_screen` fields are ignored. Value commands return a locked verdict; expected-goals and odds diagnostics do not expose uncertified values.
- The scheduled Telegram formatter now states that value betting is locked in every message chunk.
- Latest code head: `6d83589f6e9d9b36fdde6b1619532587b53caad1`. CI run #1466 passed Foundation, PostgreSQL 16 and PostgreSQL 18.
- This closes the Telegram command-router mismatch, but does not activate the webhook, schedule, public report, or delivery runner. The authoritative runtime verifier and real workflow wiring remain blockers.


## Telegram reconciliation inspector — 2026-11-14 17:48 UTC

- Added a read-only PostgreSQL reconciliation reader and staging-only CLI at `scripts/veltrix_v2/inspect_telegram_reconciliation.py`.
- It allowlists the exact Neon staging host/database, then verifies database `veltrix_football_staging` and role `neondb_owner` from the live connection.
- The reader starts with `SET TRANSACTION READ ONLY`, fetches one claim and its append-only events, and never exposes a raw destination/chat ID. It has no write, send, retry or retry-authorization capability.
- The CLI requires migrations 0009–0010 to exist, but those migrations remain unapplied; no DB access or migration was performed by this implementation.
- Code head `942278b1fff7a91d6a7e4fbbdbcfbc8973d1934a` passed CI run #1478 across Foundation, PostgreSQL 16 and PostgreSQL 18.
- PR #118 remains open/draft/unmerged. Production workflows and public release remain disabled.


## Reconciliation actor-authentication boundary — 2026-11-14 17:52 UTC

- The append-only reconciliation writer now requires an injected `authenticate_actor(subject)` callback. Missing callbacks, failed checks and callback exceptions deny writes before evidence access or DB access.
- `CONFIRMED_NOT_SENT` requires a separately authenticated reviewer; operator and reviewer must differ.
- The read-only staging inspector remains separate and has no send or write methods.
- No production OIDC/session identity provider or reconciliation endpoint is wired. The callback must be backed by a real authenticated principal before any reconciliation writes are enabled.
- Code head `311af7e3f76ec0f8f07278f37b7d6cd63004ae93` passed CI run #1488 across Foundation, PostgreSQL 16 and PostgreSQL 18.
- PR #118 remains open/draft/unmerged; migrations 0005–0010 remain unapplied to staging.


## Verified publication artifacts still absent — 2026-11-14 17:53 UTC

- Read-only GitHub Contents API check returned 404 for `command-data/public-data/v2_report_bundle.json`. The website's V2 loader therefore has no portable report artifact to load.
- The repository also has no `reports/certification/evidence-manifest.json`. The existing manual `certification-evidence-attestation.yml` workflow is pinned to `main` and references that missing file; it cannot provide current release authorization.
- `app/certification_evidence.py` explicitly states that byte-integrity verification is not certification. `scripts/verify_certification_evidence.py` is a raw-evidence diagnostic and does not issue a release certificate.
- The existing evidence-attestation workflow is not wired into the V2 API's runtime verifier. Do not treat the presence of the workflow or verifier utilities as a signed V2 publication authorization.
- No V2 publisher was added: without point-in-time eligible data, a complete evidence manifest, source-rights verification and a trusted runtime attestation verifier, writing a public bundle would bypass the release gates.


## Legacy Telegram send path shutdown — 2026-11-14 17:55 UTC

- `scripts/send_telegram_report.py` now refuses both V2 and legacy report payloads before any GitHub delivery-state access or Telegram network call.
- V2 artifacts are reserved for the certified V2 bundle delivery runner. Legacy report payloads are categorically blocked. The `--force` flag cannot bypass this shutdown.
- Legacy formatting helpers remain available for archived tests/diagnostics, but the legacy script's `main()` has no send path.
- The old daily prediction, dashboard refresh and Telegram recovery workflows remain disabled.
- CI run #1496 passed Foundation, PostgreSQL 16 and PostgreSQL 18, including the legacy sender shutdown tests.
- This closes the accidental legacy-send route; it does not create a V2 production sender or activate Telegram.


## Legacy sender shutdown validation — 2026-11-14 17:56 UTC

- `scripts/send_telegram_report.py` now has a fail-closed `main()`: it rejects V2 reports with `V2_REPORT_REQUIRES_CERTIFIED_V2_DELIVERY_RUNNER` and rejects all legacy reports with `LEGACY_REPORT_SENDER_DISABLED`.
- The legacy `--force` option cannot bypass the shutdown. The main entrypoint performs no GitHub delivery-state access and no Telegram network request.
- Archived formatting helpers remain for regression compatibility; they are not a publication path.
- CI run #1496 passed the Foundation, PostgreSQL 16 and PostgreSQL 18 jobs, including the legacy sender shutdown test suite.
- No certified V2 publisher/production sender exists yet. The command-data V2 bundle remains absent and all release workflows remain disabled.


## Controlled V2 bundle publisher adapter — 2026-11-14 17:58 UTC

- Added `veltrix_v2.reporting.publisher.publish_v2_report_bundle` and an allowlisted GitHub Contents API client.
- The publisher is pinned to repository `Nexora-Apparel/veltrix-football`, branch `command-data`, path `public-data/v2_report_bundle.json`.
- It requires the authoritative publication verifier before any GitHub access, enforces the same 8 MB maximum as the website loader, verifies the existing raw file against its Git blob SHA, rejects corrupt existing bundles, stale reports and report-ID mutation, and uses the existing GitHub blob SHA for optimistic updates.
- It is transport-injected and tested offline. No GitHub publication call was made; the V2 bundle remains absent from command-data.
- CI run #1509 passed Foundation, PostgreSQL 16 and PostgreSQL 18, including publisher authorization, immutability, stale-report and Git blob-integrity tests.
- This supplies the publication adapter but not the missing trusted certification/rights verifier or evidence manifest. Do not invoke the publisher until those gates pass.


## Same-day publication date gate — 2026-11-14 18:04 UTC

- The V2 publisher now requires an explicit canonical `expected_as_of_date` from its caller and rejects a report whose WAT as-of date differs before any GitHub access.
- This prevents publishing stale or future-dated daily reports through the command-data publisher. The production workflow must derive this value from the current `Africa/Lagos` date; no workflow is wired yet.
- CI run #1513 passed Foundation, PostgreSQL 16 and PostgreSQL 18, including exact-date, immutable-ID, stale-publication and GitHub blob integrity tests.


## Legacy command-data publisher shutdown and archive preservation — 2026-11-14 18:08 UTC

- `scripts/publish_command_data.py` now refuses its normal live publication mode. It cannot publish `daily_predictions.json` or `dashboard_snapshot.json`; those paths are also blocked at the lower-level `publish()` function.
- The historical 31 October seed workflow now uses explicit `--archive-only`. This path preserves the exact original report bytes and writes only to a content-addressed archive path; it does not update the live daily report or dashboard pointers.
- Archive publication is idempotent: the path is based on the exact report SHA-256, and the publisher skips an existing file when its bytes match. Path traversal is rejected.
- CI run #1525 passed Foundation, PostgreSQL 16 and PostgreSQL 18, including legacy live-publication shutdown and archive-preservation tests.
- The V2 publisher remains the only permitted route for a new public report, and it still requires the authoritative certification/rights verifier.


## Content-addressed archive retry validation — 2026-11-14 18:11 UTC

- Historical archive filenames now include the SHA-256 of the exact archived report bytes, so reruns resolve to the same immutable path.
- For small GitHub Contents API files, the legacy archive publisher compares existing base64 content and skips the write when the bytes already match.
- CI run #1526 passed Foundation, PostgreSQL 16 and PostgreSQL 18 with the content-addressed path and idempotent archive tests.


## Latest execution checkpoint — 2026-11-14 22:53 UTC

**Current branch:** `integration/v2-report-bundle-wiring-20261114`  
**Current head:** `0634b6bae2ad152733850dd6407d27c9e027de64`  
**PR:** #120, open/draft/unmerged; 44 commits ahead of `main`, 0 behind.

This checkpoint supersedes earlier statements in this historical log that migrations 0005–0010 were unapplied or that 5Dollar BENCHMARKING scope remained unresolved.

### Staging and provenance
- Migrations 0005–0010 are applied on the dedicated Neon staging branch `br-silent-violet-bc5de88s`, database `veltrix_football_staging`.
- Existing 2,496 fixtures, 2,496 observations and 28 raw responses remain unchanged.
- 2,659 exact-provider-ID crosswalk records are now persisted: 2,496 fixtures, 156 teams and 7 competitions. All are resolved and linked to source observation evidence, valid from verification time forward.
- No historical timestamp has been backfilled. The 2,496 historical result rows remain labels only, not PIT-certified pre-match features.
- Capture manifests: 0; capture requests: 0; prospective paper ledger events: 0.

### Provider rights and account evidence
- 5Dollar has a new append-only approved scope version `approval-5dollar-community-fixture-result-benchmarking-2026-11-14`, including BENCHMARKING for the same seven entitled competitions. The original approval remains preserved.
- The Odds API owner authorization and Terms scope are recorded as `approval-the-odds-api-v4-owner-authorized-2026-11-14`. Account entitlement remains UNVERIFIED.
- The Odds API no-credit `/v4/sports/?all=true` probe is prepared to persist exact raw response bytes, response hash, retrieval time, safe quota headers and the five configured sport-key observations.
- The prior quota workflow's rolling-period budget inference and arbitrary 400/15-credit hard caps have been removed from the execution path. No billing period, monthly allowance or hard cap is invented.
- No 5Dollar or Odds API network request has yet been made in this checkpoint; no provider credits have been consumed.

### First-observed capture and certification
- Manual 5Dollar first-observed workflow is prepared with staging persistence enabled, 14-request maximum, 90-day results lookback, 14-day upcoming window and 25-target cap.
- Odds API account probe is prepared as a separate manual workflow and calls only the documented zero-credit sports endpoint.
- The available GitHub Actions connector does not expose workflow dispatch, so neither manual workflow has been triggered from this session.
- The prospective paper ledger is empty. No prospective selections have been settled and no market is certified. Value betting remains locked.

### CI and immediate blockers
- Historical Model Audit Tests and Certification Evidence Integrity passed on the preceding head `4baeb75d82e20bf1e18fc0c839a79ebddda7c467`.
- The Foundation suite exposed one stale 5Dollar test assertion expecting BENCHMARKING to remain absent. The test was corrected to match the newly approved scope.
- Fresh checks against head `0634b6bae2ad152733850dd6407d27c9e027de64` completed successfully: Foundation run #1584, PostgreSQL 16/18 acceptance run #149, Historical Model Audit run #77 and Certification Evidence Integrity run #209 all passed. The new no-credit Odds API probe test and corrected 5Dollar approval-scope test both passed.
- Remaining release blockers: manual provider workflow dispatch; prospective first-observed evidence; 300 settled selections and 90 distinct dates; market-level chronological certification; Odds API bookmaker-market/region and billing-period/hard-cap evidence; authoritative verifier provisioning; actual website/scheduler/Telegram runtime parity; delivery idempotency and failure-recovery acceptance.

No production deployment, public publication, Telegram broadcast, schedule activation or value-bet unlock is authorized.
