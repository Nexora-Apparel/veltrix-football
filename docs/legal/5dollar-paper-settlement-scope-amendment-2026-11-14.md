# VELTRIX 2.0 — 5DollarFootballAPI paper-settlement scope amendment

**Effective review date:** 2026-11-14  
**Provider:** 5DollarFootballAPI  
**Account plan:** Community  
**Existing approval:** `approval-5dollar-community-fixture-result-2026-11`

## Purpose

This amendment records the VELTRIX project owner's explicit confirmation on 2026-11-14 that the project has full authorization to use the 5DollarFootballAPI account for the approved VELTRIX Football 2.0 work, including prospective paper prediction evaluation and settlement.

The provider's October 2026 Terms review already records permission to use the provider's fixture/result data in proprietary models and for model evaluation, internal storage/cache, commercial application display, and end-user display. This amendment maps the internal VELTRIX `BENCHMARKING` purpose to the prospective settlement and model-evaluation use described in that existing Terms review. It does not claim that the provider's Terms use the exact internal enum name `BENCHMARKING`.

## Approved scope

The approval remains limited to the seven Community-entitled competition IDs:

- Brazil Serie A: `3118717965`
- Brazil Serie B: `522514093`
- England Premier League: `4160026622`
- France Ligue 1: `3614399544`
- Germany Bundesliga I: `686337048`
- Italy Serie A: `3405541143`
- Spain La Liga: `4212821298`

Approved uses:

- COLLECTION
- CACHE
- HISTORICAL_IMPORT
- MODEL_TRAINING
- BENCHMARKING (prospective paper-result settlement and model evaluation)
- PUBLIC_DISPLAY
- STORAGE

## Controls that remain mandatory

- Community attribution remains required: **Football data by 5DollarFootballAPI** — https://5dollarfootballapi.com
- Raw provider response/feed redistribution remains prohibited.
- No competition outside the observed account entitlement is approved.
- Provider result records without source-publication timestamps remain non-PIT historical labels; this amendment does not backdate them or make them historical pre-match features.
- New prospective result observations use the collector's actual first-observed/retrieval timestamp, with source publication time left unknown.
- The 5Dollar account's live request limits and current quota must be refreshed from provider responses before each bounded capture run.
- Settlement must bind to the exact first-observed response, manifest, item evidence hash, fixture identity and prediction event.

## Evidence and review basis

1. Official Terms: https://5dollarfootballapi.com/terms (October 2026 version).
2. Existing detailed review: `docs/legal/5dollar-terms-review-2026-11-12.md`.
3. Project-owner authorization confirmation: VELTRIX FOOTBALL 2.0 conversation dated 2026-11-14.
4. Existing account qualification artifact: GitHub Actions run 43280026573, artifact `veltrix-phase1-provider-qualification`, file `fivedollar-account.json`.

This is a scoped VELTRIX use approval based on the reviewed Terms and project-owner authorization. It is not a claim of a new provider-issued letter, a change to provider Terms, or permission to redistribute raw data.
