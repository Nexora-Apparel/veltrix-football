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
