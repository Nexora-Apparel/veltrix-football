# VELTRIX FOOTBALL 2.0 — Integration audit continuation
**Audit date:** 2026-11-15  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Pull request:** #120 — draft, open, unmerged  
**Integration branch:** `integration/v2-report-bundle-wiring-20261114`

## Exact checkpoint

- Audited branch head: `11deec9a10d31a70a56ca185eedd131a639704cf`.
- PR head: `11deec9a10d31a70a56ca185eedd131a639704cf`.
- PR base: `main` at `0ac4fe22d72b899bf873c470408bd7dbf44ce800`.
- Git comparison at audit time: 278 commits ahead, 0 behind; mergeable=true.
- PR remains draft and must not be merged as a shortcut to expose manual workflows.

## CI evidence

The exact PR head had 11 completed check runs: shadow-regression, PostgreSQL 16/18 integration, PostgreSQL 16/18 acceptance, foundation, reservation PostgreSQL 16/18, certification-evidence and audit-tests all succeeded. Daily predictions was skipped by design. This is software contract validation, not model certification or live delivery acceptance.

Latest run references:
- Shadow regression/integration: `43701730573`.
- PostgreSQL acceptance: `43701730564`.
- Foundation: `43701730576`.
- Certification evidence: `43701730529`.
- Audit tests: `43701730553`.

## Semantic review completed in this continuation

- Confirmed PR #120's current head and merge-base against GitHub, not the stale prior checkpoint.
- Confirmed the 5Dollar capture workflow requires `--persist-staging` for execution; the CLI rejects execution without it and remains dry-run/no-I/O without `--execute`.
- Confirmed the Odds API workflow is a no-credit account probe and persists its evidence to staging; no event-odds endpoint is called by that workflow.
- Reviewed the capture ledger write path: it now verifies the append-only chain inside the transaction and reads the ledger back through a fresh connection after commit, checking expected fixture/model keys, event count and appended event hashes.
- Reviewed duplicate-only status semantics: a replay with zero new ledger events is distinguished from a new persisted capture; post-commit verification is required before reporting completion.
- Reviewed settlement runner boundaries: exact provider fixture/competition/team/kickoff identity, use-time rights checks, raw response/manifest persistence, quota headroom, append-only settlement and post-commit hash verification are enforced. It returns without provider calls when no target has kicked off.
- Confirmed the settlement workflow exists only on the integration branch. GitHub requires a `workflow_dispatch` workflow to exist on the default branch before it can be dispatched; do not merge PR #120 solely to expose it.
- Confirmed legacy prediction, legacy publication, Telegram delivery and scheduled workflows remain disabled. The V2 production path remains fail-closed without real attested certification evidence and a canonical report bundle.

## Reconciliation of the supplied manual capture run

Run `43699365581` completed successfully on the earlier main-branch workflow and checked out integration commit `7edc28d72376d109f006e6596a96108bdd1d5b2c`. It used 14 provider requests, captured 660 first-observed rows, mapped 25 upcoming targets and admitted 25 shadow candidates.

That run predates the fresh-connection post-commit ledger readback fix. Its `SHADOW_CAPTURE_COMPLETE` label is therefore not evidence that new ledger events committed. Later read-only reconciliation found all 25 candidates were duplicates of existing ledger keys, with zero appended events. A fresh manual capture using the current integration head is still required to exercise the corrected read-after-commit path. The current workflow itself always passes `--persist-staging` on execution.

## Remaining blockers — no bypass

1. **Fresh capture acceptance:** re-run the manual 5Dollar capture from the default-branch workflow, which checks out the current integration branch. Confirm the public summary reports post-commit verification, appended events and duplicate skips accurately. Do not infer a write from provider rows alone.
2. **Prospective settlements:** the 25 shadow targets were scheduled for 18–21 November 2026. Settlement must wait for actual kickoff and provider-observed FINISHED results. No synthetic settlement or early provider call.
3. **Odds market evidence:** The Odds API sports-catalogue response does not prove bookmaker/region market access. A one-event probe remains blocked pending fresh no-credit quota preflight, approved market/region rights, and the one-request/3-credit guard. No probe is authorized by this audit.
4. **Certification:** historical imported rows remain non-PIT-certifiable; prospective settlement and timestamped odds samples are insufficient. No market is certified; value betting remains locked.
5. **Trusted publication:** production Vercel configuration, report-bound certification manifest, matching Sigstore attestation, rights evidence and canonical report bundle are not all present. Website and Telegram must remain fail-closed.
6. **Live delivery:** actual website/report/Telegram parity, durable delivery claim and recovery against production infrastructure remain unaccepted. No Telegram send or schedule activation.
7. **Operational staging confirmation:** the current audit record identifies the operational staging branch and migration state, but any future write must revalidate exact host, database, role and migration checksums immediately before execution.

## Action boundary

The connected GitHub integration exposes repository reads and file/PR operations but no workflow-dispatch action. The fresh capture and any later settlement therefore require an operator-triggered GitHub Actions run. This limitation does not authorize merging, production writes, deployment, Telegram delivery, or schedule activation.

## Decision

**Integration code checks: PASS at the audited head. Production launch: NO-GO.** Keep PR #120 draft and unmerged; retain the existing branch and evidence. Continue with the fresh post-commit capture acceptance and the dated prospective settlement process without reopening completed provider discovery or changing the legacy stack.
