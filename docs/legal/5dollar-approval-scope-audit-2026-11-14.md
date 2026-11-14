# VELTRIX 2.0 — 5DollarFootballAPI approval-scope audit

Date: 2026-11-14
Target: dedicated Neon staging branch only
Method: read-only SQL inspection and repository legal-review inspection

## Finding

The current 5DollarFootballAPI approval record is APPROVED for the following stored purposes:

- COLLECTION
- CACHE
- HISTORICAL_IMPORT
- MODEL_TRAINING
- PUBLIC_DISPLAY
- STORAGE

It does **not** contain the explicit `BENCHMARKING` purpose.

The source approval record is:
- Approval ID: `approval-5dollar-community-fixture-result-2026-11`
- Provider: `5DollarFootballAPI`
- Source ID: `5dollarfootballapi`
- Data type: `fixture_result`
- Competition scope: provider IDs `3118717965,3405541143,3614399544,4160026622,4212821298,522514093,686337048`
- Terms URL: https://5dollarfootballapi.com/terms
- Terms version: October 2026
- Rights evidence: `docs/legal/5dollar-terms-review-2026-11-12.md`
- Evidence SHA-256: `e818940f894b924ec3e25fbf36e3a43e3969b17d509b21b7a476ddf14a10d879`
- Attribution required: `Football data by 5DollarFootballAPI` — https://5dollarfootballapi.com
- Raw redistribution: not allowed

The append-only approval event history contains one APPROVED event:
- effective at 2026-11-12T00:00:00Z
- recorded at 2026-11-12T22:51:49.463Z
- reason: `APPROVAL_CREATED`

No approval event or status change was written during this audit.

## Why the missing purpose matters

The rights model distinguishes `MODEL_TRAINING` from `BENCHMARKING`. The paper settlement adapter explicitly requires COLLECTION, STORAGE and BENCHMARKING rights when a provider result is used to settle and evaluate a prospective paper prediction.

The legal review text says the provider terms allow historical model training and evaluation. However, the persisted approval record does not encode BENCHMARKING. The system must not infer that one enum implies the other.

Therefore:
- Existing 5Dollar approval supports the currently recorded training and display uses within its seven-competition scope.
- The existing paper settlement path must continue to reject 5Dollar settlements until BENCHMARKING is explicitly approved in the rights record.
- Do not weaken settlement rights checks or silently map MODEL_TRAINING to BENCHMARKING.
- No public raw feed redistribution is permitted.

## Temporal limitation remains separate

The legal approval does not solve timestamp quality. The provider does not supply the historical source-publication timestamp required by the strict Phase 4 capture contract. Existing imported rows remain non-PIT-certifiable. The conservative four-day availability proxy must not be re-labelled as provider publication or availability time.

A future collector may preserve a first-observed timestamp for prospective-only use, but it must remain explicitly distinct from provider publication time and must not be backdated into historical walk-forward evidence.

## Read-only audit evidence

The staging SQL inspection returned:
- One matching source approval row.
- One append-only APPROVED status event.
- Seven competition IDs in the stored scope.
- No BENCHMARKING value in `permitted_uses`.

Only SELECT queries were executed. No database rows, approval records, rights events, production data or provider APIs were changed or contacted.

## Required resolution

Before 5Dollar results can settle prospective paper selections:
1. Re-review the October 2026 provider terms specifically for forecast evaluation/benchmarking use.
2. If the terms support it, record a separate evidence-backed approval update that explicitly adds BENCHMARKING, with the correct effective and recorded timestamps.
3. Keep raw redistribution disabled and retain required public attribution.
4. Re-run rights resolution at the actual settlement time.

Until then, paper settlements sourced from 5Dollar remain blocked by design.
