# VELTRIX V2 Prospective Paper Settlement Operations — 2026-11-15

## Purpose

Define the controlled, staging-only settlement procedure for V2 shadow predictions. This process appends immutable settlement events to the existing prospective paper ledger. It never edits prediction events and never publishes forecasts.

## Current ledger baseline

At the 2026-11-15 audit:
- Ledger: `veltrix-v2-prospective-observed`
- Database: `veltrix_football_staging`
- Neon project: `withered-sky-75161174`
- Staging branch: `br-silent-violet-bc5de88s`
- Shadow predictions: 25 across 25 distinct fixtures
- Settlements: 0
- The 25 target kickoffs fall between 2026-11-18 22:30 UTC and 2026-11-21 15:00 UTC.

No target is eligible for settlement before its kickoff and a provider-observed FINISHED result. A future fixture is not to be marked as settled based on a scheduled status, estimated finish time, external score page, or inferred score.

## Required settlement identity

A settlement must match exactly one prediction by:
- Canonical ledger fixture ID `5dollarfootballapi:<provider_fixture_id>`
- Model version, where more than one prediction exists for a fixture
- Provider and source identity
- Exact provider fixture ID
- Competition ID
- Home and away team IDs
- Exact kickoff timestamp

Ambiguous or missing matches are quarantined for manual reconciliation. Never guess a fixture crosswalk from team names alone.

## Source evidence requirements

For each candidate result:
1. Retrieve the finished fixture from the approved 5DollarFootballAPI endpoint, within the seven entitled competitions.
2. Preserve the exact raw response bytes, response SHA-256, request ID, request parameters, retrieval timestamp, recording timestamp and relevant response headers.
3. Parse the item and require provider status `FINISHED` with non-negative integer home and away scores.
4. Recompute the item payload hash from the canonical JSON representation and compare it to the parsed fixture hash.
5. Verify the provider fixture ID, competition, both teams and kickoff against the immutable prediction target metadata and the reviewed provider-to-canonical crosswalk.
6. Resolve the current append-only source-approval status at the time of use. Require collection, storage and benchmarking permission within the exact competition scope. This project is personal-use; commercial-use permission is not a prerequisite.
7. Reject a missing or invalid source approval, missing raw response, malformed score, untrusted identity, ambiguous crosswalk, or mismatched payload hash.

The 5Dollar feed does not expose a reliable historical publication clock or complete revision history. For these prospective shadow predictions only, use the collector's exact first-observed retrieval time as the conservative result-availability time:
- `result_available_at = retrieved_at`
- `result_retrieved_at = retrieved_at`
- `result_availability_basis = collector_first_observed_v1`

The first-observed clock must be at or after kickoff and no later than the database recording time. Do not substitute the legacy four-day availability proxy for the actual first-observed clock. Do not backdate the result or promote it to PIT-certified training data.

## Append-only settlement rules

- Load and verify the entire existing hash chain before processing.
- Settle one exact prediction/model-version pair at most once.
- Append a new `SETTLEMENT` event linked to the exact prediction event hash.
- Preserve result payload hash, source identity, rights approval ID and rights evidence hash.
- Recheck the ledger under the PostgreSQL transaction/advisory lock before insert.
- If a settlement already exists, report it as a duplicate and do not overwrite it.
- If a provider later corrects a score, retain the original settlement and create a separate correction/review workflow; never mutate or silently replace the original event.
- Verify the complete chain after each committed batch.
- A failed batch must roll back atomically.

## Metrics and certification

After settlements exist, compute market metrics only from eligible prediction/settlement pairs:
- 1X2: multiclass Brier score and log loss
- BTTS and totals: market-specific Brier score and log loss
- ROI only when the matching market selection has a verified, timestamped, pre-kickoff quote and a documented settlement rule
- CLV only when opening/closing or accepted quote timestamps are independently retained

Keep prospective results separate from any historical archive. Report the number of predictions, settled predictions, distinct settlement dates, odds-covered selections and exclusions for every market. A score result without a timestamped price is not an ROI sample.

No model is certified until all existing market-specific walk-forward and prospective thresholds pass. The current 25 shadow predictions and zero settlements do not qualify any market. Value betting remains locked.

## Safety boundaries

This procedure is staging-only. It must not:
- write to production databases;
- invoke the daily prediction workflow;
- enable the 06:00 WAT schedule;
- create a public report bundle;
- send Telegram messages;
- unlock value betting;
- alter historical prediction or settlement events.

## Implementation status

The in-memory settlement validator and PostgreSQL append-only store adapter exist. The personal-use rights check is corrected to evaluate approved collection, storage and benchmarking permissions with `commercial=False`. Regression coverage verifies that a personal-use-only approval can settle a paper result.

The first implementation of the operational collector/reconciler now exists in `scripts/phase5_settle_5dollar_shadow.py` and `veltrix_v2/ledger/settlement_reconciliation.py`. It defaults to a no-I/O dry run; `--execute` is required for bounded provider requests and staging-only writes. It queries only competitions represented by eligible unsettled targets, caps provider pages at 14, preserves each exact finished-response page and manifest in staging, links the response and manifest SHA-256 values into each immutable settlement event, re-resolves rights immediately before settlement, performs exact source fixture/competition/team/kickoff matching (including each eligible model version), and appends settlement events under the PostgreSQL ledger lock. It quarantines mismatches and duplicates, verifies the ledger hash chain after append, and has no production/publication/Telegram/schedule/value-bet path. At the 2026-11-15 audit all 25 target kickoffs are still in the future, so the collector returns `NO_ELIGIBLE_FINISHED_TARGETS` without making provider requests or writing settlements. The exact-head CI regression passed 158 provider/model/settlement tests, 165 publication/bundle/delivery boundary tests and 36 PostgreSQL integration tests (including paper-ledger settlement response/manifest persistence); foundation, PostgreSQL 16/18 acceptance, certification-evidence and audit checks also passed. The daily prediction workflow was skipped intentionally.


## Operator invocation

Dry run (no database connection, no provider request, no write):

```bash
python scripts/phase5_settle_5dollar_shadow.py
```

Execution is staging-only and requires the existing environment variables `FIVEDOLLARFOOTBALL_API_KEY` and `VELTRIX_STAGING_DATABASE_URL`:

```bash
python scripts/phase5_settle_5dollar_shadow.py --execute
```

Do not run `--execute` until target fixtures have actually kicked off. The collector itself checks eligibility and returns without provider requests when no unsettled target has kicked off. Provider calls are bounded to 14 pages maximum and paced; no retry loop is enabled.


## Prospective scorecard

`veltrix_v2/evaluation/prospective_settlement_metrics.py` scores only immutable prospective settlements linked to their exact prediction event hash. It rejects duplicate prediction/settlement keys and non-prospective settlement links. It reports market-specific sample counts, distinct UTC kickoff dates, Brier score and log loss for 1X2, BTTS and totals where those probabilities were actually recorded. Missing market probabilities are omitted rather than inferred. The settlement CLI includes this scorecard in `settlement_summary.json`, including the zero-eligible-target dry outcome, so the operator receives an auditable baseline even before the first result settles.

ROI and CLV remain explicitly unavailable: the current prediction/settlement ledger does not contain a verified pre-kickoff selection plus timestamped odds evidence. The scorecard returns null ROI/CLV and a locked reason rather than deriving stake, price or expected value. Its certification status is always `NOT_CERTIFIED`; it is a measurement layer, not a release gate override.

## Manual GitHub Actions runner

The staging-only collector is available through the manual workflow:
`https://github.com/Nexora-Apparel/veltrix-football/actions/workflows/phase5-5dollar-shadow-settlement.yml`

The workflow performs a no-I/O dry-run first, then executes the existing bounded collector with the approved 5Dollar key and staging DSN. It has no schedule trigger, production database target, publication path or Telegram delivery path. It uploads only `settlement_public_summary.json`; row-level fixture identifiers and quarantine details remain only in the ephemeral runner workspace and are not uploaded as artifacts.

The collector now checks quota headroom on every provider page and verifies the full ledger plus exact settlement event hashes from a fresh PostgreSQL connection after the write transaction commits. A missing post-commit event or hash mismatch fails the workflow. The current 25 targets are not due until their kickoffs (18–21 November 2026); running before then returns `NO_ELIGIBLE_FINISHED_TARGETS` without provider requests or settlement writes.


## Settlement runner engineering update — 2026-11-15

- Added the manual workflow `.github/workflows/phase5-5dollar-shadow-settlement.yml`. It runs a verified no-I/O dry-run before execution, has only `workflow_dispatch`, uses the approved 5Dollar key and staging DSN, and uploads only the aggregate scorecard.
- The collector now enforces quota headroom after each provider page, then verifies the full ledger and each appended settlement event hash from a fresh PostgreSQL connection after the write transaction commits.
- The public scorecard omits row-level fixture IDs and quarantine details. It records the settled count, quarantined count, ledger chain status, post-commit status and prospective metrics. Value betting remains locked.
- The current target window is 18–21 November 2026. Before a target kickoff, the workflow exits as `NO_ELIGIBLE_FINISHED_TARGETS` without provider calls or settlement writes.
