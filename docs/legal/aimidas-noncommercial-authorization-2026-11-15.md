# VELTRIX FOOTBALL 2.0 — AI Midas source authorization

**Recorded:** 2026-11-15  
**Approval ID:** `approval-aimidas-football-data-noncommercial-2026-11-15`  
**Status:** USER-CONFIRMED AUTHORIZATION — NON-COMMERCIAL PROJECT USE  
**Provider/source:** AI Midas Football Data  
**Repository:** https://github.com/aimidas1/aimidas1

## Authorization basis

The project owner confirmed on 2026-11-15 that VELTRIX has authorization to use the newly identified AI Midas source for project work as permitted by the source authorization. This record formalizes that confirmation for the Stage 2 source register.

The project-wide non-commercial restriction remains controlling:

- No monetisation of source data, data-derived services or VELTRIX outputs.
- No resale, sublicensing, paid access, advertising-funded data exploitation or commercial licensing.
- No raw-feed redistribution.
- Preserve source attribution, upstream lineage, retrieval date, immutable source revision and content hashes.
- Internal collection, caching, storage, archival, parsing, normalization, research, feature engineering, model training, validation and non-commercial evaluation are within the user-confirmed VELTRIX project scope, subject to the source authorization and the technical controls below.

## Scope recorded

The AI Midas repository is pinned for the initial audit to commit:

`29baca362a34ce5dcd3924b07ec9c7d5139d83fc`

The source's public CSV/Excel files can be retrieved from GitHub without an API key. Veltrix must use pinned commit URLs for reproducible snapshots rather than an unpinned moving `main` URL.

The repository's `sync_stats.py` identifies `griffisben/Post_Match_App/Stat_Files` as the upstream source for the AI Midas `advanced stats` mirror. Preserve this lineage in provenance. The repository metadata for both repositories reports no declared SPDX licence; the user-confirmed source authorization is therefore recorded separately from repository licence metadata. This record does not claim that an upstream repository has independently issued a licence.

## Technical admission limits

- Repository permission does not create source publication timestamps. Store actual Veltrix retrieval/recording time separately.
- Historical match date strings have no verified timezone in the inspected files. Do not manufacture UTC kickoff timestamps.
- Fields named `pre_match_*` or `*_prematch` have no row-level availability timestamp or independent temporal proof in the inspected release. They are not PIT-certified.
- Actual xG/xGA, shots, possession, PPDA, scores and other match-stat fields are post-match observations. Do not use a match's own post-match statistics to predict that match.
- `avg_odds_ft_1/x/2` are average odds fields. No bookmaker identity, quote timestamp, closing definition or per-bookmaker price history was found. They are not timestamped bookmaker closing odds and cannot satisfy CLV, the 98% timestamped-odds gate or bookmaker benchmark certification.
- Brazil Série B is represented in the inspected release by 2026 advanced team-match statistics only; no 2016–2025 Brazil Série B historical match archive or Brazil Série B average-odds match file was found.
- Keep the data retrospective/non-PIT until a separate source-version publication-time proof exists. It may be used for internal historical research and future model development only under explicit leakage controls and with actual Veltrix import time preserved.

## Operational boundary

This authorization record does not itself insert data into Neon, create a database approval event, admit features to a model, alter predictions, or authorize production writes, publication, Telegram delivery, schedule activation, PR merge or deployment.

**Decision:** AI Midas is an authorized non-commercial VELTRIX source. Dataset inventory and temporal qualification are documented separately in `docs/VELTRIX_V2_AIMIDAS_DATASET_AUDIT_2026-11-15.md`.
