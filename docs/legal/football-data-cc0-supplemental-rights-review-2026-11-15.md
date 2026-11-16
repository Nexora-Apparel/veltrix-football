# VELTRIX FOOTBALL 2.0 — FootballData CC0 supplemental rights review

Review date: 2026-11-15.

Repository: https://github.com/FerrerasRP/FootballData

GitHub repository metadata and the repository LICENSE identify CC0-1.0. The selected text-only Brazil Serie B source files are:

- database/brasil-serie-b/brasil-serie-b 2025.json
- database/brasil-serie-b/brasil-serie-b 2026.json

Rights approval ID: approval-ferrerasrp-footballdata-cc0-2026-11-15.

## Permitted internal scope

The selected match date, team labels and final-score facts are approved for COLLECTION, STORAGE, HISTORICAL_IMPORT, MODEL_TRAINING and BENCHMARKING under CC0-1.0, subject to applicable law. This does not cover logos, photographs, video, commentary, player biographies, odds, xG or lineup data.

## Provenance and temporal limits

- Retrieve each file by immutable Git commit SHA and retain raw bytes plus SHA-256.
- Preserve every available commit revision for the exact path; do not invent intermediate versions.
- Preserve the commit timestamp separately from actual retrieval/recording time.
- Enforce the two-calendar-day UTC safety boundary for date-only result availability.
- The 2025 file has two repository snapshots; the 2026 file has one snapshot dated 2026-07-08. The 2026 data is partial and stale; it is not current-season coverage through November.
- match_date contains a reported local clock string, but no timezone is documented. Preserve it as source_reported_local_time; keep kickoff_at null and source_timezone UNKNOWN.
- Trailing newline-plus-integer team-name artifacts may be normalized only when the clean base name appears in the same immutable snapshot. Retain original names and normalization evidence.
- Team and competition IDs are source-scoped. No joins to OpenFootball or 5Dollar are permitted until evidence-backed crosswalks are built.

This supplemental source is not promoted into the production feature path by this review. Its archive proof, coverage, freshness, team identity and cross-provider consistency must pass independent gates first. Historical archive-proof integration must not falsify recorded_at or bypass the chronological evaluator's cutoff checks.
